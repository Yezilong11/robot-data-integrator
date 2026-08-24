# tests/unit/test_parse_goal.py
"""parse_goal 节点单元测试。

通过 monkeypatch 替换 ``_get_llm_client`` 注入 fake client，
覆盖成功路径（含/无 PDF）、LLM 不可用降级、JSON 解析失败降级、
req_id 规范化、PDF 文本抽取的边界情况。
"""

from __future__ import annotations

import fitz
import pytest

from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.graph.nodes import parse_goal
from rdi.graph.nodes.parse_goal import (
    _extract_paper_text,
    _GoalParsingResult,
    node_parse_goal,
)
from rdi.models import DataReq, DataReqType, GoalSpec, Priority


class _FakeLLMClient:
    """记录 prompt / system 并按构造参数返回结果或抛异常的假 client。"""

    def __init__(self, result: _GoalParsingResult | None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def call_structured(self, prompt, schema, system=None):  # type: ignore[no-untyped-def]
        self.last_prompt = prompt
        self.last_system = system
        if self._exc is not None:
            raise self._exc
        return self._result


@pytest.fixture(autouse=True)
def _reset_llm_singleton() -> None:
    """每个测试前重置模块级 _llm_client 单例，保证测试隔离。"""
    parse_goal._llm_client = None


def _make_result(
    req_ids: list[str], req_types: list[DataReqType] | None = None
) -> _GoalParsingResult:
    """构造测试用 _GoalParsingResult，req_id 由调用方指定。

    req_types 缺省时全部为 ROBOT_URDF；传入不同类型可避免被
    ``_dedupe_requirements`` 按 (req_type, object_name) 合并（占位描述无关键词）。
    """
    types = req_types or [DataReqType.ROBOT_URDF] * len(req_ids)
    reqs = [
        DataReq(
            req_id=rid,
            req_type=types[i],
            description=f"需求 {i}",
            priority=Priority.REQUIRED,
        )
        for i, rid in enumerate(req_ids)
    ]
    return _GoalParsingResult(
        goal=GoalSpec(research_topic="抓取实验", experiment_type="grasping"),
        requirements=reqs,
    )


def _install_fake(
    monkeypatch: pytest.MonkeyPatch,
    result: _GoalParsingResult | None = None,
    exc: Exception | None = None,
) -> _FakeLLMClient:
    """注入 fake LLMClient 并返回实例供断言。"""
    fake = _FakeLLMClient(result=result, exc=exc)
    monkeypatch.setattr(parse_goal, "_get_llm_client", lambda: fake)
    return fake


def test_parse_goal_success_without_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """无 PDF 时，LLM 成功返回，断言结构与 provenance。"""
    fake = _install_fake(monkeypatch, result=_make_result(["req_000"]))

    out = node_parse_goal({"user_goal": "复现 Franka Panda 抓取"})

    assert isinstance(out["parsed_goal"], GoalSpec)
    assert out["parsed_goal"].research_topic == "抓取实验"
    assert isinstance(out["data_requirements"], list)
    assert all(isinstance(r, DataReq) for r in out["data_requirements"])
    assert out["data_requirements"][0].req_id == "req_000"
    assert any("LLM 解析成功" in line for line in out["provenance"])
    assert fake.last_prompt is not None
    assert "复现 Franka Panda 抓取" in fake.last_prompt


def test_parse_goal_success_with_pdf(monkeypatch: pytest.MonkeyPatch) -> None:
    """提供合法 PDF 时，paper_text 被注入到 user prompt。"""
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((50, 50), "test paper from fitz")
    pdf_bytes = doc.tobytes()
    doc.close()

    fake = _install_fake(monkeypatch, result=_make_result(["req_000"]))

    out = node_parse_goal({"user_goal": "抓取", "paper_pdf": pdf_bytes})

    assert isinstance(out["parsed_goal"], GoalSpec)
    assert fake.last_prompt is not None
    assert "test paper from fitz" in fake.last_prompt
    assert "未提供论文" not in fake.last_prompt
    assert any("LLM 解析成功" in line for line in out["provenance"])


def test_parse_goal_llm_unavailable_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMUnavailableError 触发降级：不抛异常、errors 非空、requirements 为空。"""
    _install_fake(
        monkeypatch,
        exc=LLMUnavailableError("service down", model="test-model", retry_count=3),
    )

    out = node_parse_goal({"user_goal": "抓取实验"})

    assert "errors" in out
    assert len(out["errors"]) == 1
    assert "降级" in out["errors"][0]
    assert "LLMUnavailableError" in out["errors"][0]
    assert out["data_requirements"] == []
    assert isinstance(out["parsed_goal"], GoalSpec)
    assert out["parsed_goal"].research_topic == "抓取实验"
    assert any("降级" in line for line in out["provenance"])


def test_parse_goal_llm_parse_error_degradation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLMParseError 同样触发降级路径。"""
    _install_fake(
        monkeypatch,
        exc=LLMParseError("bad json", model="test-model", retry_count=0),
    )

    out = node_parse_goal({"user_goal": "抓取实验"})

    assert "errors" in out
    assert len(out["errors"]) == 1
    assert "降级" in out["errors"][0]
    assert "LLMParseError" in out["errors"][0]
    assert out["data_requirements"] == []
    assert any("降级" in line for line in out["provenance"])


def test_parse_goal_normalizes_req_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """LLM 返回的不规范 req_id 被统一重编号为 req_XXX（不同类型需求不被去重合并）。"""
    _install_fake(
        monkeypatch,
        result=_make_result(
            ["abc", "1", "req-001"],
            req_types=[
                DataReqType.ROBOT_URDF,
                DataReqType.MESH,
                DataReqType.SIM_CONFIG,
            ],
        ),
    )

    out = node_parse_goal({"user_goal": "抓取"})

    reqs = out["data_requirements"]
    assert [r.req_id for r in reqs] == ["req_000", "req_001", "req_002"]


def test_extract_paper_text_handles_empty() -> None:
    """空输入与非合法 PDF 都返回 None，不抛异常。"""
    assert _extract_paper_text(None) is None
    assert _extract_paper_text(b"") is None
    assert _extract_paper_text(b"not a pdf") is None


@pytest.mark.parametrize(
    ("initial_type", "description", "expected_format", "expected_type"),
    [
        (DataReqType.CODE, "Franka Panda URDF 模型", "urdf/xacro", DataReqType.ROBOT_URDF),
        (DataReqType.DATASET, "YCB banana 3D model", "obj", DataReqType.MESH),
        (DataReqType.CODE, "grasp pose data for mug", "npz", DataReqType.GRASP),
        (DataReqType.DATASET, "MuJoCo simulation scene config", "xml", DataReqType.SIM_CONFIG),
    ],
)
def test_parse_goal_corrects_misclassified_req_type(
    monkeypatch: pytest.MonkeyPatch,
    initial_type: DataReqType,
    description: str,
    expected_format: str,
    expected_type: DataReqType,
) -> None:
    """LLM 把真实数据误标为 code/dataset 时，按格式或描述关键词修正。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=initial_type,
            description=description,
            priority=Priority.REQUIRED,
            expected_format=expected_format,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "test"})

    assert out["data_requirements"][0].req_type == expected_type


@pytest.mark.parametrize(
    ("initial_type", "description", "expected_format", "expected_type"),
    [
        # Day2 回归：检索类目标描述含"抓取/grasp"，但核心是仓库/数据集，
        # 不应被 GRASP 弱关键词兜底误改为 grasp。
        (DataReqType.CODE, "检索 Franka 抓取相关的开源代码仓库", None, DataReqType.CODE),
        (DataReqType.DATASET, "retrieve robot grasp dataset", None, DataReqType.DATASET),
        # 真实复现：LLM 判为 GRASP 且配 npz 格式（GRASP 强词 npz 会抢先命中），
        # 描述含 "dataset" 容器词时仍应优先判 DATASET。
        (DataReqType.GRASP, "retrieve robot grasp dataset", "npz", DataReqType.DATASET),
    ],
)
def test_parse_goal_keeps_code_dataset_for_repo_dataset_targets(
    monkeypatch: pytest.MonkeyPatch,
    initial_type: DataReqType,
    description: str,
    expected_format: str | None,
    expected_type: DataReqType,
) -> None:
    """Day2 回归：code/dataset 需求描述含"抓取/grasp"时保持原类型。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=initial_type,
            description=description,
            priority=Priority.REQUIRED,
            expected_format=expected_format,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "test"})

    assert out["data_requirements"][0].req_type == expected_type


@pytest.mark.parametrize(
    ("req_type", "description", "expected_format", "expected_object_name"),
    [
        (DataReqType.GRASP, "banana 的抓取标注", "npz", "banana"),
        (DataReqType.MESH, "011_banana 的 mesh", None, "011_banana"),
    ],
)
def test_parse_goal_fills_object_name(
    monkeypatch: pytest.MonkeyPatch,
    req_type: DataReqType,
    description: str,
    expected_format: str | None,
    expected_object_name: str,
) -> None:
    """C1：GRASP/MESH 需求经 node_parse_goal 后处理按描述文本填充 object_name。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=req_type,
            description=description,
            priority=Priority.REQUIRED,
            expected_format=expected_format,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "test"})

    assert out["data_requirements"][0].object_name == expected_object_name


def test_parse_goal_keeps_llm_filled_object_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """C1：LLM 已填的 object_name 不被后处理覆盖。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.GRASP,
            description="banana 的抓取标注",
            priority=Priority.REQUIRED,
            expected_format="npz",
            object_name="011_banana",
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "test"})

    assert out["data_requirements"][0].object_name == "011_banana"


def test_parse_goal_does_not_fill_object_name_for_other_types(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """C1：非 GRASP/MESH 需求不填充 object_name（保持空串）。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.PAPER,
            description="banana 的抓取标注相关论文",
            priority=Priority.REQUIRED,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "test"})

    assert out["data_requirements"][0].object_name == ""


# ─── D2: 新类型可识别（CAMERA_CALIB / TEACHING_TRAJECTORY / ROBOT_CONFIG / BENCHMARK_TASK） ───


@pytest.mark.parametrize(
    ("description", "expected_type"),
    [
        ("标定相机参数", DataReqType.CAMERA_CALIB),
        ("采集机械臂示教轨迹", DataReqType.TEACHING_TRAJECTORY),
        ("机器人配置 robot config", DataReqType.ROBOT_CONFIG),
        ("benchmark 基准测试任务", DataReqType.BENCHMARK_TASK),
    ],
)
def test_parse_goal_recognizes_new_types(
    monkeypatch: pytest.MonkeyPatch,
    description: str,
    expected_type: DataReqType,
) -> None:
    """D2：LLM 输出 unknown、描述含新类型中文关键词时，后处理映射为对应新类型。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.UNKNOWN,
            description=description,
            priority=Priority.REQUIRED,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": description})

    assert out["data_requirements"][0].req_type == expected_type


def test_parse_goal_keeps_llm_new_type_and_zh_description(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """D2：LLM 直接输出新类型时保持不被改走，且枚举成员带中文描述（zh）。"""
    reqs = [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.CAMERA_CALIB,
            description="相机标定参数",
            priority=Priority.REQUIRED,
        )
    ]
    _install_fake(
        monkeypatch,
        result=_GoalParsingResult(
            goal=GoalSpec(research_topic="test"),
            requirements=reqs,
        ),
    )

    out = node_parse_goal({"user_goal": "标定相机参数"})

    req = out["data_requirements"][0]
    assert req.req_type == DataReqType.CAMERA_CALIB
    # 中文描述映射：枚举成员 zh 属性非空且语义正确
    assert DataReqType.CAMERA_CALIB.zh == "相机标定参数"
    assert DataReqType.TEACHING_TRAJECTORY.zh == "示教轨迹"
    assert DataReqType.ROBOT_CONFIG.zh == "机器人配置"
    assert DataReqType.BENCHMARK_TASK.zh == "基准测试任务"
