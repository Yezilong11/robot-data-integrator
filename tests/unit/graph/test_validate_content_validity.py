"""P0-A 内容有效性校验（占位/元数据代理 + 目标-内容语义匹配）单元测试。"""

from __future__ import annotations

from datetime import datetime

from rdi.graph.nodes.validate import node_validate
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry, Severity
from rdi.models.goal import DataReq
from rdi.models.retrieval import RawReference

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance(fmt: str = "bin", url: str = "https://example.com/asset/a.stl") -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.GRASPNET,
        source_url=url,
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


def _item(
    req_id: str,
    req_type: DataReqType,
    data: object,
    fmt: str = "bin",
    name: str | None = None,
    url: str = "https://example.com/asset/a.stl",
    reference: RawReference | None = None,
    is_fallback: bool = False,
    data_source_quality: str | None = None,
) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=name or req_id,
        canonical_format=fmt,
        output_path="files/out.bin",
        data=data,
        provenance=_provenance(fmt, url),
        reference=reference,
        is_fallback=is_fallback,
        data_source_quality=data_source_quality,
    )


def _req(
    req_id: str,
    req_type: DataReqType,
    description: str = "",
    keywords: list[str] | None = None,
    object_name: str = "",
) -> DataReq:
    return DataReq(
        req_id=req_id,
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
        keywords=keywords or [],
        object_name=object_name,
    )


def _errors(out: dict, req_id: str) -> list:
    return [
        i for i in out["validation_issues"]
        if i.req_id == req_id and i.severity == Severity.ERROR
    ]


# ─── 占位/元数据代理检测 ───


def test_placeholder_reference_is_error() -> None:
    """大文件仅提供远端引用（reference 非空）→ 元数据代理 ERROR。"""
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "t", "file_tree": ["a/b.npy"]},
        fmt="DatasetSummary",
        reference=RawReference(
            url="https://example.com/big.npy",
            reason="体积超过阈值未下载",
        ),
    )
    out = node_validate({"parsed_data": {"r1": item}})
    errs = _errors(out, "r1")
    assert any("仅元数据/占位" in i.message for i in errs)
    assert any(i.context.get("issue_type") == "content_validity" for i in errs)


def test_placeholder_dataset_summary_empty_file_tree_is_error() -> None:
    """DatasetSummary 且 file_tree 为空 → 占位 ERROR。"""
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "t", "description": "d", "file_tree": []},
        fmt="DatasetSummary",
    )
    out = node_validate({"parsed_data": {"r1": item}})
    errs = _errors(out, "r1")
    assert any("仅元数据/占位" in i.message for i in errs)


def test_placeholder_small_fallback_bytes_is_error() -> None:
    """降级来源且数据 <200B → 占位 ERROR（不受 is_fallback 豁免）。"""
    item = _item(
        "r1",
        DataReqType.MESH,
        b"tiny",
        fmt="stl",
        is_fallback=True,
        data_source_quality="fallback",
    )
    out = node_validate({"parsed_data": {"r1": item}})
    errs = _errors(out, "r1")
    assert any("仅元数据/占位" in i.message for i in errs)


def test_non_placeholder_large_fallback_bytes_ok() -> None:
    """降级来源但数据较大（有真实内容）→ 不判占位。"""
    item = _item(
        "r1",
        DataReqType.MESH,
        b"x" * 500,
        fmt="stl",
        is_fallback=True,
    )
    out = node_validate({"parsed_data": {"r1": item}})
    assert not any("仅元数据/占位" in i.message for i in out["validation_issues"])


def test_non_placeholder_dataset_real_file_tree_ok() -> None:
    """DatasetSummary 且 file_tree 非空（真实数据清单）→ 不判占位。"""
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "t", "file_tree": ["grasp_labels/011_banana.npz"]},
        fmt="DatasetSummary",
    )
    out = node_validate({"parsed_data": {"r1": item}})
    assert not any("仅元数据/占位" in i.message for i in out["validation_issues"])


# ─── 目标-内容语义匹配 ───


def test_semantic_mismatch_ur5_franka() -> None:
    """需求 UR5 却拿到 franka panda → 语义不符 ERROR。"""
    req = _req("r1", DataReqType.ROBOT_URDF, "获取 UR5 机械臂模型", keywords=["ur5"])
    item = _item(
        "r1",
        DataReqType.ROBOT_URDF,
        b"<robot name='panda'/>",
        fmt="urdf",
        name="franka_panda",
        url="https://raw.githubusercontent.com/frankaemika/panda/urdf/panda.urdf",
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    errs = _errors(out, "r1")
    assert any("内容与需求语义不符" in i.message for i in errs)
    assert any(i.context.get("issue_type") == "content_validity" for i in errs)


def test_semantic_mismatch_sim_config_ur5_franka() -> None:
    """T4：SIM_CONFIG 语义错配回退——需求 UR5 仿真配置却拿到 franka 资产 → ERROR。

    与 GRASP/MESH/ROBOT_URDF 行为一致：SIM_CONFIG 在 _SEMANTIC_REQ_TYPES 启用
    集合内（isaac 降级回退 franka.py 等真实资产，若与需求目标零重叠须检出）。
    """
    req = _req(
        "r1",
        DataReqType.SIM_CONFIG,
        "获取 UR5 仿真配置",
        keywords=["ur5"],
        object_name="ur5",
    )
    item = _item(
        "r1",
        DataReqType.SIM_CONFIG,
        b"# Franka Emika Panda asset config\nclass FrankaCfg:\n    pass\n",
        fmt="python",
        name="franka",
        url=(
            "https://raw.githubusercontent.com/isaac-sim/IsaacLab/release/3.0.0-beta2/"
            "source/isaaclab_assets/isaaclab_assets/robots/franka.py"
        ),
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    errs = _errors(out, "r1")
    assert any("内容与需求语义不符" in i.message for i in errs)
    assert any(i.context.get("issue_type") == "content_validity" for i in errs)


def test_semantic_mismatch_apple_coffeemaker() -> None:
    """需求苹果却拿到咖啡机 → 语义不符 ERROR。"""
    req = _req("r1", DataReqType.MESH, "苹果物体网格", keywords=["apple"])
    item = _item(
        "r1",
        DataReqType.MESH,
        b"mesh",
        fmt="stl",
        name="coffee_maker",
        url="https://example.com/models/coffee_maker.stl",
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    assert any("内容与需求语义不符" in i.message for i in _errors(out, "r1"))


def test_semantic_match_no_false_positive() -> None:
    """合法匹配（apple ← apple）不误报。"""
    req = _req("r1", DataReqType.MESH, "苹果物体网格", keywords=["apple"])
    item = _item(
        "r1",
        DataReqType.MESH,
        b"mesh",
        fmt="stl",
        name="apple",
        url="https://example.com/models/apple.stl",
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    assert not any("内容与需求语义不符" in i.message for i in _errors(out, "r1"))


def test_semantic_skip_when_no_terms() -> None:
    """需求无具体实体词（泛词）→ 跳过语义校验，不误报。"""
    req = _req(
        "r1",
        DataReqType.ROBOT_URDF,
        "获取机器人模型文件",
        keywords=["机器人"],
    )
    item = _item(
        "r1",
        DataReqType.ROBOT_URDF,
        b"<robot name='panda'/>",
        fmt="urdf",
        name="franka_panda",
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    assert not any("内容与需求语义不符" in i.message for i in _errors(out, "r1"))


def test_semantic_skipped_for_non_semantic_types() -> None:
    """非语义类型（CAMERA_CALIB，不在 _SEMANTIC_REQ_TYPES）不启用语义匹配。"""
    req = _req("r1", DataReqType.CAMERA_CALIB, "相机标定参数", keywords=["apple", "抓取"])
    item = _item(
        "r1",
        DataReqType.CAMERA_CALIB,
        {"intrinsics": [1.0]},
        fmt="yaml",
        name="unrelated_calib",
    )
    out = node_validate({"parsed_data": {"r1": item}, "data_requirements": [req]})
    assert not any("内容与需求语义不符" in i.message for i in _errors(out, "r1"))