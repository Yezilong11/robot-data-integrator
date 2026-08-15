# tests/unit/graph/nodes/test_parse_goal.py
"""parse_goal 规则后处理 `_normalize_datareq` 单元测试。

直接调用模块级 ``_normalize_datareq`` 覆盖：
- 全部强制映射关键词分支（强关键词 + 弱关键词兜底）；
- 强关键词对任意 req_type 的覆盖（对任何类型都生效）；
- 正常场景不误伤（grasp 描述里的 robot / Robotiq 不被误映射）；
- UNKNOWN 分支（保持 UNKNOWN + 记录 warning）。
"""

from __future__ import annotations

import logging

import pytest

from rdi.graph.nodes.parse_goal import (
    _dedupe_requirements,
    _extract_object_name_from_text,
    _normalize_datareq,
)
from rdi.models import DataReq, DataReqType, Priority


def _req(
    description: str,
    expected_format: str | None = None,
    req_type: DataReqType = DataReqType.CODE,
) -> DataReq:
    """构造最小 DataReq 用于规则测试。"""
    return DataReq(
        req_id="req_000",
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
        expected_format=expected_format,
    )


@pytest.mark.parametrize(
    ("description", "expected_format", "expected"),
    [
        # ── ROBOT_URDF ──
        ("Franka Panda URDF 描述文件", None, DataReqType.ROBOT_URDF),
        ("机器人 xacro 模型", None, DataReqType.ROBOT_URDF),
        ("UR5 robot model", None, DataReqType.ROBOT_URDF),
        ("下载机器人描述文件", None, DataReqType.ROBOT_URDF),
        ("robot 模型", None, DataReqType.ROBOT_URDF),
        # ── MESH ──
        ("YCB banana 的 mesh 文件", None, DataReqType.MESH),
        ("下载香蕉的 3D model", None, DataReqType.MESH),
        ("物体模型 obj 文件", None, DataReqType.MESH),
        ("stl 网格模型", None, DataReqType.MESH),
        ("ply 场景物体", None, DataReqType.MESH),
        ("dae 文件", None, DataReqType.MESH),
        ("glb 模型", None, DataReqType.MESH),
        ("下载物体的 3D 网格模型", None, DataReqType.MESH),
        # ── GRASP ──
        ("grasp pose 数据", None, DataReqType.GRASP),
        ("grasping pose 数据", None, DataReqType.GRASP),
        ("grasp data 文件", None, DataReqType.GRASP),
        ("grasp_label 数据", None, DataReqType.GRASP),
        ("抓取姿态数据", None, DataReqType.GRASP),
        ("抓取数据", None, DataReqType.GRASP),
        ("grasp 任务", None, DataReqType.GRASP),
        ("grasping 任务", None, DataReqType.GRASP),
        # ── SIM_CONFIG ──
        ("mujoco 仿真场景", None, DataReqType.SIM_CONFIG),
        ("isaac 场景配置", None, DataReqType.SIM_CONFIG),
        ("mjcf 文件", None, DataReqType.SIM_CONFIG),
        ("仿真场景配置", None, DataReqType.SIM_CONFIG),
        ("仿真配置", None, DataReqType.SIM_CONFIG),
        ("simulation scene", None, DataReqType.SIM_CONFIG),
        ("sim config 文件", None, DataReqType.SIM_CONFIG),
        ("仿真实验", None, DataReqType.SIM_CONFIG),
        ("simulation 数据", None, DataReqType.SIM_CONFIG),
        # ── expected_format 兜底 ──
        ("物体模型", "stl", DataReqType.MESH),
        ("姿态数据", "npz", DataReqType.GRASP),
        ("场景配置", "xml", DataReqType.SIM_CONFIG),
        ("机器人文件", "urdf", DataReqType.ROBOT_URDF),
        ("数据文件", "pkl", DataReqType.GRASP),
    ],
)
def test_normalize_force_mapping(
    description: str,
    expected_format: str | None,
    expected: DataReqType,
) -> None:
    """LLM 把需求误标为 code/dataset 时，按描述/格式关键词强制映射。"""
    out = _normalize_datareq(_req(description, expected_format, DataReqType.CODE))
    assert out.req_type == expected


@pytest.mark.parametrize(
    ("initial", "description", "expected_format", "expected"),
    [
        (DataReqType.POLICY_MODEL, "grasp pose npz 数据", None, DataReqType.GRASP),
        (DataReqType.MESH, "Franka Panda URDF", None, DataReqType.ROBOT_URDF),
        (DataReqType.ROBOT_URDF, "MuJoCo 仿真场景 XML", None, DataReqType.SIM_CONFIG),
        (DataReqType.SENSOR_DATA, "YCB mug 的 STL mesh", None, DataReqType.MESH),
        (DataReqType.DATASET, "UR5 robot 描述", None, DataReqType.ROBOT_URDF),
    ],
)
def test_normalize_strong_overrides_any_type(
    initial: DataReqType,
    description: str,
    expected_format: str | None,
    expected: DataReqType,
) -> None:
    """强关键词命中时对任何 req_type 都生效（不再限于 code/dataset）。"""
    out = _normalize_datareq(_req(description, expected_format, initial))
    assert out.req_type == expected


def test_normalize_keeps_correct_concrete_types() -> None:
    """正常场景不误伤：已正确分类的具体需求保持原类型。"""
    # grasp 需求描述含 robot / Robotiq 不应被映射为 ROBOT_URDF
    g = _req("用 Franka Panda robot 生成 grasp pose 数据", None, DataReqType.GRASP)
    assert _normalize_datareq(g).req_type == DataReqType.GRASP
    g2 = _req("UR5 with Robotiq 2F-85 grasps YCB apple", None, DataReqType.GRASP)
    assert _normalize_datareq(g2).req_type == DataReqType.GRASP
    # robot_urdf 描述里的"模型"不应被映射为 MESH
    r = _req("Franka Panda URDF 模型", "urdf", DataReqType.ROBOT_URDF)
    assert _normalize_datareq(r).req_type == DataReqType.ROBOT_URDF
    # sim_config 保持
    s = _req("MuJoCo 仿真场景", None, DataReqType.SIM_CONFIG)
    assert _normalize_datareq(s).req_type == DataReqType.SIM_CONFIG
    # 具体类型不受弱关键词影响
    p = _req("机器人抓取领域的论文", None, DataReqType.PAPER)
    assert _normalize_datareq(p).req_type == DataReqType.PAPER
    pm = _req("抓取策略模型", None, DataReqType.POLICY_MODEL)
    assert _normalize_datareq(pm).req_type == DataReqType.POLICY_MODEL
    sd = _req("机器人传感器数据", None, DataReqType.SENSOR_DATA)
    assert _normalize_datareq(sd).req_type == DataReqType.SENSOR_DATA


def test_normalize_unknown_rescued_by_keywords() -> None:
    """req_type=UNKNOWN 但描述含关键词时，强制映射为具体类型。"""
    out = _normalize_datareq(_req("Franka Panda robot URDF", None, DataReqType.UNKNOWN))
    assert out.req_type == DataReqType.ROBOT_URDF
    out2 = _normalize_datareq(_req("MuJoCo 仿真配置", None, DataReqType.UNKNOWN))
    assert out2.req_type == DataReqType.SIM_CONFIG


def test_normalize_unknown_logs_warning(caplog: pytest.LogCaptureFixture) -> None:
    """无法识别的需求保持 UNKNOWN 并记录 warning。"""
    with caplog.at_level(logging.WARNING, logger="rdi.graph.nodes.parse_goal"):
        out = _normalize_datareq(_req("一些无法分类的内容", None, DataReqType.UNKNOWN))
    assert out.req_type == DataReqType.UNKNOWN
    assert any("UNKNOWN" in r.message for r in caplog.records)


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        # 对应 5.1 各示例输出中的每条需求描述
        ("Franka Panda 机器人 URDF 描述文件", DataReqType.ROBOT_URDF),
        ("YCB banana 的 3D 网格模型", DataReqType.MESH),
        ("YCB banana 的抓取姿态数据", DataReqType.GRASP),
        ("MuJoCo 仿真场景配置", DataReqType.SIM_CONFIG),
        ("Kinova Gen3 机器人 URDF 描述文件", DataReqType.ROBOT_URDF),
        ("EGAD mug 的 3D 网格模型", DataReqType.MESH),
        ("EGAD mug 的抓取姿态数据", DataReqType.GRASP),
        ("Isaac Sim 仿真场景配置", DataReqType.SIM_CONFIG),
        ("UR5 与 Robotiq 2F-85 夹爪的 URDF 描述文件", DataReqType.ROBOT_URDF),
        ("YCB apple 的 3D 网格模型", DataReqType.MESH),
        ("YCB apple 的抓取姿态数据", DataReqType.GRASP),
        ("YCB blocks 的 3D 网格模型", DataReqType.MESH),
        ("PyBullet 仿真场景配置", DataReqType.SIM_CONFIG),
        ("UR5 机器人 URDF 模型", DataReqType.ROBOT_URDF),
        ("香蕉的 3D 网格模型", DataReqType.MESH),
        ("YCB 物体的抓取姿态数据", DataReqType.GRASP),
        ("抓取姿态规划数据", DataReqType.GRASP),
        ("ModelNet bottle 的 3D 网格模型", DataReqType.MESH),
        ("ModelNet bottle 的抓取姿态数据", DataReqType.GRASP),
        ("YCB 物体的 3D 网格模型", DataReqType.MESH),
    ],
)
def test_example_corpus_maps_to_four_types(
    description: str,
    expected: DataReqType,
) -> None:
    """5.1 示例清单中的各条需求描述经规则后处理正确产出四类 DataReq。"""
    out = _normalize_datareq(_req(description, None, DataReqType.CODE))
    assert out.req_type == expected


# ─── C1: _extract_object_name_from_text 物体名提取规则 ───


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        # 规则 1：YCB 风格 id
        ("011_banana 的 mesh", "011_banana"),
        ("YCB 003_cracker_box 的抓取标注", "003_cracker_box"),
        # 规则 2：中文抓取语境（两种语序）
        ("banana 的抓取标注", "banana"),
        ("抓取标注：banana", "banana"),
        ("YCB apple 的抓取姿态数据", "apple"),
        ("EGAD mug 的抓取姿态数据", "mug"),
        # 规则 3：英文 grasp 语境
        ("grasp pose of banana", "banana"),
        ("grasping pose of mug", "mug"),
        # 规则 4：YCB 常见物体英文名
        ("YCB banana 的 3D 网格模型", "banana"),
        ("ModelNet bottle 的 3D 网格模型", ""),
        # 无物体名 / 泛化词不误报
        ("抓取姿态数据", ""),
        ("抓取数据", ""),
        ("一些无关描述", ""),
    ],
)
def test_extract_object_name_from_text(text: str, expected: str) -> None:
    """C1：按优先级从描述文本提取目标物体名。"""
    assert _extract_object_name_from_text(text) == expected


# ─── D2: 新类型（CAMERA_CALIB / TEACHING_TRAJECTORY / ROBOT_CONFIG / BENCHMARK_TASK） ───


@pytest.mark.parametrize(
    ("description", "expected"),
    [
        # ── CAMERA_CALIB ──
        ("标定相机参数", DataReqType.CAMERA_CALIB),
        ("相机标定", DataReqType.CAMERA_CALIB),
        ("camera calibration 内参外参", DataReqType.CAMERA_CALIB),
        ("标定", DataReqType.CAMERA_CALIB),
        # ── TEACHING_TRAJECTORY ──
        ("机械臂示教轨迹数据", DataReqType.TEACHING_TRAJECTORY),
        ("采集示教轨迹", DataReqType.TEACHING_TRAJECTORY),
        ("teaching trajectory 数据", DataReqType.TEACHING_TRAJECTORY),
        ("demonstration 数据", DataReqType.TEACHING_TRAJECTORY),
        # ── ROBOT_CONFIG ──
        ("获取 robot config", DataReqType.ROBOT_CONFIG),
        ("robot_config 文件", DataReqType.ROBOT_CONFIG),
        ("config.yaml 机器人参数", DataReqType.ROBOT_CONFIG),
        # ── BENCHMARK_TASK ──
        ("benchmark 评测任务", DataReqType.BENCHMARK_TASK),
        ("基准测试任务", DataReqType.BENCHMARK_TASK),
        ("基准任务定义", DataReqType.BENCHMARK_TASK),
    ],
)
def test_normalize_maps_new_types(
    description: str,
    expected: DataReqType,
) -> None:
    """D2：LLM 把新类型需求误标为 code/unknown 时，按中文/英文描述关键词映射。"""
    out = _normalize_datareq(_req(description, None, DataReqType.CODE))
    assert out.req_type == expected
    out_unknown = _normalize_datareq(_req(description, None, DataReqType.UNKNOWN))
    assert out_unknown.req_type == expected


@pytest.mark.parametrize(
    "req_type",
    [
        DataReqType.CAMERA_CALIB,
        DataReqType.TEACHING_TRAJECTORY,
        DataReqType.ROBOT_CONFIG,
        DataReqType.BENCHMARK_TASK,
    ],
)
def test_normalize_keeps_llm_filled_new_types(req_type: DataReqType) -> None:
    """D2：LLM 已正确输出新类型时，后处理保持原类型不被改走。"""
    out = _normalize_datareq(_req("描述内容", None, req_type))
    assert out.req_type == req_type


def test_normalize_new_types_do_not_misclassify_existing() -> None:
    """D2 不回归：新类型关键词不误伤已有类型。"""
    # SIM_CONFIG 描述含"配置"不应被 ROBOT_CONFIG 转走（ROBOT_CONFIG 不收中文"配置"）
    s = _req("MuJoCo 仿真场景配置", None, DataReqType.SIM_CONFIG)
    assert _normalize_datareq(s).req_type == DataReqType.SIM_CONFIG
    # ROBOT_URDF 描述含 "robot" 但无 "robot config" 整词，不被 ROBOT_CONFIG 转走
    r = _req("Franka Panda robot URDF 模型", None, DataReqType.ROBOT_URDF)
    assert _normalize_datareq(r).req_type == DataReqType.ROBOT_URDF
    # GRASP 描述含"轨迹"（抓取姿态）不应被 TEACHING_TRAJECTORY 转走
    g = _req("grasp pose 轨迹数据", None, DataReqType.GRASP)
    assert _normalize_datareq(g).req_type == DataReqType.GRASP


# ─── D4: _dedupe_requirements 重复需求去重 ───


def _req_full(
    req_type: DataReqType,
    description: str,
    object_name: str = "",
) -> DataReq:
    """构造带 req_id/object_name 的 DataReq（用于去重测试）。"""
    return DataReq(
        req_id="req_000",
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
        object_name=object_name,
    )


def test_dedupe_merges_same_type_same_object() -> None:
    """同一目标内相同 (req_type, object_name) 的重复需求合并为 1 条，保留第一条。"""
    reqs = [
        _req_full(DataReqType.ROBOT_URDF, "Franka Panda 机器人 URDF 描述文件"),
        _req_full(DataReqType.MESH, "YCB blocks 的 3D 网格模型", object_name="blocks"),
        _req_full(DataReqType.ROBOT_URDF, "Franka Panda 的 URDF（重复生成）"),
    ]
    out = _dedupe_requirements(reqs)
    assert len(out) == 2
    assert [r.req_type for r in out] == [DataReqType.ROBOT_URDF, DataReqType.MESH]
    assert out[0].description == "Franka Panda 机器人 URDF 描述文件"  # 保留第一条
    # 去重后 req_id 重编号为连续
    assert [r.req_id for r in out] == ["req_000", "req_001"]


def test_dedupe_keeps_different_objects() -> None:
    """不同物体的同类型需求（banana/apple GRASP）不应被合并。"""
    reqs = [
        _req_full(DataReqType.GRASP, "YCB banana 的抓取姿态数据", object_name="banana"),
        _req_full(DataReqType.GRASP, "YCB apple 的抓取姿态数据", object_name="apple"),
    ]
    out = _dedupe_requirements(reqs)
    assert len(out) == 2


def test_dedupe_keeps_different_types() -> None:
    """不同类型需求（ROBOT_URDF + MESH + SIM_CONFIG）全部保留。"""
    reqs = [
        _req_full(DataReqType.ROBOT_URDF, "UR5 机器人 URDF 模型"),
        _req_full(DataReqType.MESH, "YCB mug 的 3D 网格模型", object_name="mug"),
        _req_full(DataReqType.SIM_CONFIG, "PyBullet 仿真场景配置"),
    ]
    out = _dedupe_requirements(reqs)
    assert len(out) == 3
    assert [r.req_id for r in out] == ["req_000", "req_001", "req_002"]


def test_dedupe_object_name_case_insensitive() -> None:
    """object_name 大小写不敏感：'Banana' 与 'banana' 视为同一物体。"""
    reqs = [
        _req_full(DataReqType.MESH, "Banana 的 mesh", object_name="Banana"),
        _req_full(DataReqType.MESH, "banana 的 mesh", object_name="banana"),
    ]
    out = _dedupe_requirements(reqs)
    assert len(out) == 1
