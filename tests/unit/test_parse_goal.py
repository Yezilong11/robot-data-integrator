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


def _make_result(req_ids: list[str]) -> _GoalParsingResult:
    """构造测试用 _GoalParsingResult，req_id 由调用方指定。"""
    reqs = [
        DataReq(
            req_id=rid,
            req_type=DataReqType.ROBOT_URDF,
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
    """LLM 返回的不规范 req_id 被统一重编号为 req_XXX。"""
    _install_fake(monkeypatch, result=_make_result(["abc", "1", "req-001"]))

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
