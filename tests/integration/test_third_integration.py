"""第三次联调集成测试：mock parse_goal 与 Adapter fetch，跑通完整 LangGraph 工作流。

覆盖 5 个端到端目标（参数化）：
1. "Franka Panda grasps YCB banana in MuJoCo"
2. "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉"
3. "Kinova Gen3 picks up EGAD mug in Isaac Sim"
4. "UR5 with Robotiq 2F-85 grasps YCB apple"
5. "Franka Panda stacks YCB blocks in PyBullet"

mock 策略（避免网络）：
- ``parse_goal`` 的 LLM client → 固定返回四类 DataReq（ROBOT_URDF / MESH / GRASP / SIM_CONFIG）
- ``retrieve_data`` 的 ``select_adapter`` → 按 req_type 返回 mock Adapter，
  ``fetch`` 返回真实感 bytes（真实 URDF/STL/npz/XML，均来自 ``sample_data``）
- ``retrieve_data`` 的 HermesEngine → Mock（跳过 ChromaDB）
- ``assemble`` 的 ``settings.output_dir`` → tmp_path

断言（每个目标）：
- 数据包含四类文件（robots/ objects/ grasps/ sim_config/ 各至少一个）
- ``validation_issues`` 无 ERROR 级
- grasp 与 sim_config 中至少一个文件 ``data_source_quality == "real"``
- manifest ``files[].path`` 与磁盘一致
- sim_config 的 MuJoCo ``runtime_check`` 已写入 PackageManifest

说明：Isaac / PyBullet 目标的 sim_config 由 SimConfigSkill 降级为最小 MJCF
（``data_source_quality="fallback"``，受限于非 MJCF 输入），此时由真实 grasp
（npz → ``data_source_quality="real"``）满足断言；MuJoCo 目标 sim_config 直通
真实 XML（``data_source_quality="real"``）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from rdi.adapters.base import BaseAdapter
from rdi.graph.builder import build_graph
from rdi.graph.nodes import parse_goal
from rdi.models import (
    DataReq,
    DataReqType,
    DataSource,
    GoalSpec,
    Priority,
    Severity,
)
from rdi.models.retrieval import RawData, SearchResult

_SAMPLE_DIR = Path(__file__).parent.parent / "unit" / "skills" / "sample_data"

# ─── 真实感样本字节（避免网络，同时可被各 Skill 真实解析） ───
_URDF_BYTES = (_SAMPLE_DIR / "urdf" / "allegro_hand_r.urdf").read_bytes()
_MESH_BYTES = (_SAMPLE_DIR / "mesh" / "hand.stl").read_bytes()
_GRASP_NPZ_BYTES = (_SAMPLE_DIR / "grasp" / "sample_labels.npz").read_bytes()
_SIM_MJCF_BYTES = (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes()
_SIM_ISAAC_BYTES = (_SAMPLE_DIR / "sim" / "isaac_scene.yaml").read_bytes()
_SIM_PYBULLET_BYTES = (
    b"scene = {\n"
    b"    'robot': 'franka_panda',\n"
    b"    'objects': ['block_01', 'block_02'],\n"
    b"    'timestep': 0.01,\n"
    b"}\n"
)


# ─── 5 个端到端目标（参数化） ───
_CASES: list[dict[str, Any]] = [
    {
        "case_id": "franka_ycb_banana_mujoco",
        "goal": "Franka Panda grasps YCB banana in MuJoCo",
        "robot": "franka panda",
        "object": "banana",
        "sim_name": "mujoco",
        "sim_fmt": "xml",
        "sim_bytes": _SIM_MJCF_BYTES,
        "expect_sim_real": True,
    },
    {
        "case_id": "franka_ycb_banana_mujoco_zh",
        "goal": "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉",
        "robot": "franka panda",
        "object": "banana",
        "sim_name": "mujoco",
        "sim_fmt": "xml",
        "sim_bytes": _SIM_MJCF_BYTES,
        "expect_sim_real": True,
    },
    {
        "case_id": "kinova_egad_mug_isaac",
        "goal": "Kinova Gen3 picks up EGAD mug in Isaac Sim",
        "robot": "kinova gen3",
        "object": "mug",
        "sim_name": "isaac",
        "sim_fmt": "yaml",
        "sim_bytes": _SIM_ISAAC_BYTES,
        # Isaac 配置（YAML）非 MJCF，SimConfigSkill 降级为最小 MJCF → fallback；
        # 该目标由真实 grasp（npz → real）满足「grasp/sim_config 至少一个 real」。
        "expect_sim_real": False,
    },
    {
        "case_id": "ur5_robotiq_ycb_apple_mujoco",
        "goal": "UR5 with Robotiq 2F-85 grasps YCB apple",
        "robot": "ur5 robotiq 2f-85",
        "object": "apple",
        "sim_name": "mujoco",
        "sim_fmt": "xml",
        "sim_bytes": _SIM_MJCF_BYTES,
        "expect_sim_real": True,
    },
    {
        "case_id": "franka_ycb_blocks_pybullet",
        "goal": "Franka Panda stacks YCB blocks in PyBullet",
        "robot": "franka panda",
        "object": "blocks",
        "sim_name": "pybullet",
        "sim_fmt": "python",
        "sim_bytes": _SIM_PYBULLET_BYTES,
        # PyBullet 无真实 MJCF 资产，SimConfigSkill 降级为最小 MJCF → fallback，
        # 由真实 grasp（npz → real）满足「grasp/sim_config 至少一个 real」。
        "expect_sim_real": False,
    },
]


class _FakeLLMClient:
    """parse_goal 的 LLM mock：固定返回四类 DataReq。"""

    def __init__(self, result: parse_goal._GoalParsingResult) -> None:
        self._result = result

    def call_structured(self, prompt, schema, system=None):  # type: ignore[no-untyped-def]
        return self._result


def _make_requirements(case: dict[str, Any]) -> list[DataReq]:
    """按目标配置构造四类 DataReq（ROBOT_URDF / MESH / GRASP / SIM_CONFIG）。"""
    return [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.ROBOT_URDF,
            description=f"{case['robot']} URDF",
            priority=Priority.REQUIRED,
            keywords=[case["robot"]],
        ),
        DataReq(
            req_id="req_001",
            req_type=DataReqType.MESH,
            description=f"YCB {case['object']} mesh",
            priority=Priority.REQUIRED,
            keywords=[case["object"]],
        ),
        DataReq(
            req_id="req_002",
            req_type=DataReqType.GRASP,
            description="GraspNet grasp poses",
            priority=Priority.RECOMMENDED,
            keywords=["grasp", case["object"]],
            fallback_sources=[DataSource.GRASPNET, DataSource.DEXGRASP, DataSource.YCB],
        ),
        DataReq(
            req_id="req_003",
            req_type=DataReqType.SIM_CONFIG,
            description=f"{case['sim_name']} simulation scene",
            priority=Priority.REQUIRED,
            keywords=[case["sim_name"]],
        ),
    ]


def _make_adapter_cls(source: DataSource, raw: RawData) -> type[BaseAdapter]:
    """构造返回固定 RawData 的 mock Adapter 类（带 search/fetch）。"""

    class _FakeAdapter(BaseAdapter):
        source: DataSource = DataSource.FRANKA  # 占位，下方按源覆盖

        def __init__(self) -> None:  # 与真实 Adapter 一致：无参构造
            self.base_url = "https://example.com"  # type: ignore[assignment]

        async def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    item_id=raw.item_id,
                    title="fake result",
                    source=_FakeAdapter.source,
                    url=raw.url,
                )
            ]

        async def fetch(self, item_id: str, req_type=None, **kwargs: Any) -> RawData:  # type: ignore[no-untyped-def]
            return raw

    _FakeAdapter.source = source  # 类体无法捕获闭包变量，创建后赋值
    return _FakeAdapter


def _mock_retrieval_pipeline(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any]) -> None:
    """替换 retrieve_data 的 select_adapter：按 req_type 返回真实感 RawData。"""
    raw_by_type: dict[DataReqType, RawData] = {
        DataReqType.ROBOT_URDF: RawData(
            source=DataSource.FRANKA,
            item_id=case["robot"].replace(" ", "_"),
            format="urdf",
            data=_URDF_BYTES,
            url="https://example.com/robot.urdf",
            size_bytes=len(_URDF_BYTES),
        ),
        DataReqType.MESH: RawData(
            source=DataSource.YCB,
            item_id=case["object"],
            format="stl",
            data=_MESH_BYTES,
            url="https://example.com/object.stl",
            size_bytes=len(_MESH_BYTES),
        ),
        DataReqType.GRASP: RawData(
            source=DataSource.GRASPNET,
            item_id=f"011_{case['object']}" if case["object"] == "banana" else case["object"],
            format="npz",
            data=_GRASP_NPZ_BYTES,
            url="https://example.com/grasp_labels.npz",
            size_bytes=len(_GRASP_NPZ_BYTES),
        ),
        DataReqType.SIM_CONFIG: RawData(
            source=DataSource.MUJOCO,
            item_id=case["sim_name"],
            format=case["sim_fmt"],
            data=case["sim_bytes"],
            url=f"https://example.com/{case['sim_name']}.{case['sim_fmt']}",
            size_bytes=len(case["sim_bytes"]),
        ),
    }

    def _select(req_type: DataReqType) -> list[type[BaseAdapter]]:
        raw = raw_by_type[req_type]
        return [_make_adapter_cls(raw.source, raw)]

    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", _select)

    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.record_experience = Mock()
    hermes.get_source_priority.return_value = []
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)


def _patch_workflow(monkeypatch: pytest.MonkeyPatch, case: dict[str, Any], tmp_path: Path) -> None:
    """替换 parse_goal 的 LLM client，并 mock 检索与输出目录。"""
    requirements = _make_requirements(case)
    fake_llm = _FakeLLMClient(
        parse_goal._GoalParsingResult(
            goal=GoalSpec(
                research_topic=case["goal"],
                robot_type=case["robot"],
                simulator=case["sim_name"],
                experiment_type="grasping",
            ),
            requirements=requirements,
        )
    )
    monkeypatch.setattr("rdi.graph.nodes.parse_goal._get_llm_client", lambda: fake_llm)
    _mock_retrieval_pipeline(monkeypatch, case)
    monkeypatch.setattr("rdi.graph.nodes.assemble.settings.output_dir", str(tmp_path))


@pytest.mark.parametrize("case", _CASES, ids=[c["case_id"] for c in _CASES])
async def test_third_integration_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    case: dict[str, Any],
) -> None:
    """完整工作流（builder 构建的 LangGraph 图）端到端断言。"""
    _patch_workflow(monkeypatch, case, tmp_path)
    graph = build_graph()

    state = {
        "user_goal": case["goal"],
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
    }
    result = await graph.ainvoke(state)

    pkg = result["experiment_package"]
    package_dir = Path(pkg.output_dir)

    # 1) 四类数据文件各至少一个
    subdirs = {"robots", "objects", "grasps", "sim_config"}
    paths = [f.path for f in pkg.files]
    for sub in subdirs:
        assert any(p.startswith(f"{sub}/") for p in paths), f"缺少 {sub}/ 文件: {paths}"

    # 2) validation_issues 无 ERROR 级
    errors = [i for i in result["validation_issues"] if i.severity == Severity.ERROR]
    assert errors == [], f"存在 ERROR 级校验问题: {errors}"

    # 3) grasp 与 sim_config 中至少一个文件 data_source_quality == "real"
    grasp_sim_files = [f for f in pkg.files if f.path.startswith(("grasps/", "sim_config/"))]
    assert grasp_sim_files, "数据包缺少 grasp 或 sim_config 文件"
    assert any(f.data_source_quality == "real" for f in grasp_sim_files), (
        f"grasp/sim_config 无 real 来源: {[(f.path, f.data_source_quality) for f in grasp_sim_files]}"
    )

    # sim_config 的来源真实度符合预期（MuJoCo 直通 real；Isaac/PyBullet fallback）
    sim_files = [f for f in pkg.files if f.path.startswith("sim_config/")]
    assert sim_files, "数据包缺少 sim_config 文件"
    if case["expect_sim_real"]:
        assert sim_files[0].data_source_quality == "real"
    else:
        assert sim_files[0].data_source_quality == "fallback"

    # 4) manifest files[].path 与磁盘一致
    assert (package_dir / "manifest.json").is_file()
    for f in pkg.files:
        assert (package_dir / f.path).is_file(), f"manifest path 与磁盘不一致: {f.path}"

    # 5) 数据包写入 PackageManifest 的 runtime_check（sim_config 的 MuJoCo 验证）
    assert pkg.runtime_check, "PackageManifest.runtime_check 为空"
    assert all(
        check.get("status") in ("passed", "skipped") for check in pkg.runtime_check.values()
    ), f"runtime_check 含失败状态: {pkg.runtime_check}"
