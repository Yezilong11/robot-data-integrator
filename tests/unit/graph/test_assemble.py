"""assemble 节点单元测试：数据包按 req_type 结构化子目录落盘。

验证 manifest ``files[].path`` 与实际磁盘路径一致，
且各 ``DataReqType`` 正确映射到子目录。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from rdi.config.settings import PIPELINE_VERSION, settings
from rdi.graph.nodes.assemble import node_assemble
from rdi.models import (
    DataReq,
    DataReqType,
    DataSource,
    MissingItem,
    ParsedItem,
    Priority,
    RawReference,
)
from rdi.models.common import ProvenanceEntry

if TYPE_CHECKING:
    from rdi.graph.state import SystemState

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance() -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.GITHUB,
        source_url="https://example.com",
        retrieved_at=_FIXED_TIME,
        original_format="bin",
    )


def _item(req_id: str, req_type: DataReqType, fmt: str) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=req_id,
        canonical_format=fmt,
        output_path="unused",
        data=b"<payload>",
        provenance=_provenance(),
    )


# req_type → 期望子目录
_CASES: dict[str, tuple[DataReqType, str, str]] = {
    "req_000": (DataReqType.ROBOT_URDF, "urdf", "robots/req_000.urdf"),
    "req_001": (DataReqType.MESH, "stl", "objects/req_001.stl"),
    "req_002": (DataReqType.GRASP, "CanonicalGrasp", "grasps/req_002.bin"),
    "req_003": (DataReqType.SIM_CONFIG, "xml", "sim_config/req_003.xml"),
    "req_004": (DataReqType.POLICY_MODEL, "text", "policies/req_004.txt"),
    "req_005": (DataReqType.CODE, "text", "resources/req_005.txt"),
    "req_006": (DataReqType.DATASET, "json", "resources/req_006.json"),
    "req_007": (DataReqType.PAPER, "markdown", "resources/req_007.md"),
    "req_008": (DataReqType.UNKNOWN, "bin", "resources/req_008.bin"),
}


@pytest.fixture
def output_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """把全局 settings.output_dir 指向临时目录。"""
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    return tmp_path


def test_assemble_writes_structured_subdirs(output_dir: Path) -> None:
    """各类 req_type 落盘到对应子目录，manifest path 与磁盘路径一致。"""
    parsed_data = {
        req_id: _item(req_id, req_type, fmt) for req_id, (req_type, fmt, _) in _CASES.items()
    }
    state: SystemState = {
        "parsed_data": parsed_data,
        "data_requirements": [],
        "missing_items": [],
        "validation_issues": [],
    }

    out = node_assemble(state)
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert len(pkg.files) == len(_CASES) + 1  # +1 为质量解释条目
    for f in pkg.files:
        if f.req_id == "package":  # 质量解释条目（req_id=package，无对应 _CASES）
            assert f.path == "quality_explanation.md"
            continue
        expected_path = _CASES[f.req_id][2]
        assert f.path == expected_path
        # manifest 相对路径与实际磁盘文件一致
        assert (package_dir / f.path).is_file()
        assert not f.path.startswith("files/")

    # 抽查各类子目录均真实存在于磁盘
    for rel in ("robots", "objects", "grasps", "sim_config", "policies", "resources"):
        assert (package_dir / rel).is_dir()


def test_assemble_unknown_type_falls_back_to_resources(output_dir: Path) -> None:
    """未收录的 req_type（如 SENSOR_DATA）兜底到 resources/。"""
    state: SystemState = {
        "parsed_data": {
            "req_009": _item("req_009", DataReqType.SENSOR_DATA, "npz"),
        }
    }

    out = node_assemble(state)
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert pkg.files[0].path == "resources/req_009.npz"
    assert (package_dir / "resources" / "req_009.npz").is_file()


def test_assemble_carries_revision_history(output_dir: Path) -> None:
    """state.revision_history 原样挂到 manifest.revision_history。"""
    revision_history = [
        {
            "revision": 1,
            "decision": "revised",
            "feedback": ["换 UR5"],
            "revised_goal": "用 UR5 在 PyBullet 中抓取 mug",
            "timestamp": "2026-07-23T12:00:00",
        }
    ]
    state: SystemState = {"revision_history": revision_history}

    out = node_assemble(state)
    pkg = out["experiment_package"]

    assert pkg.revision_history == revision_history


def test_assemble_writes_raw_urdf_and_assets(output_dir: Path) -> None:
    """P0-3：带 raw_bytes + assets 时，原始 URDF 与按相对路径的资产文件均落盘。"""
    urdf = b'<robot name="r"><link name="base"/></robot>'
    item = ParsedItem(
        req_id="req_raw",
        req_type=DataReqType.ROBOT_URDF,
        name="req_raw",
        canonical_format="urdf",
        output_path="unused",
        data=b"<payload>",  # 有 raw_bytes 时不走 data 序列化
        raw_bytes=urdf,
        assets={"meshes/base.stl": b"stl-bytes", "./textures/uv.png": b"png-bytes"},
        provenance=ProvenanceEntry(
            source=DataSource.GITHUB,
            source_url="https://example.com/panda.urdf",
            retrieved_at=_FIXED_TIME,
            original_format="urdf",
        ),
    )
    out = node_assemble({"parsed_data": {"req_raw": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    main_file = package_dir / "robots/req_raw.urdf"
    assert main_file.is_file()
    assert main_file.read_bytes() == urdf
    # 资产按相对路径落盘（前导 ./ 已规范化）
    assert (package_dir / "robots/meshes/base.stl").read_bytes() == b"stl-bytes"
    assert (package_dir / "robots/textures/uv.png").read_bytes() == b"png-bytes"
    # manifest 记录沿用现有构造（format 为 canonical_format）
    assert pkg.files[0].path == "robots/req_raw.urdf"
    assert pkg.files[0].format == "urdf"


def test_assemble_assets_in_manifest_and_checksums(output_dir: Path) -> None:
    """P0-5：资产文件纳入 manifest 条目与 checksums.txt，校验和与磁盘一致，主文件不回归。"""
    urdf = b'<robot name="r"><link name="base"/></robot>'
    item = ParsedItem(
        req_id="req_asset_mf",
        req_type=DataReqType.ROBOT_URDF,
        name="req_asset_mf",
        canonical_format="urdf",
        output_path="unused",
        data=b"<payload>",  # 有 raw_bytes 时不走 data 序列化
        raw_bytes=urdf,
        assets={
            "meshes/base.stl": b"stl-bytes",
            "./textures/uv.png": b"png-bytes",
            "config/unknown.zzz": b"zzz-bytes",  # 未知扩展名 → "asset"
            "../..": b"evil-bytes",  # 剥离后为 ".." → continue，不落盘不进 manifest
        },
        provenance=ProvenanceEntry(
            source=DataSource.GITHUB,
            source_url="https://example.com/panda.urdf",
            retrieved_at=_FIXED_TIME,
            original_format="urdf",
        ),
    )
    out = node_assemble({"parsed_data": {"req_asset_mf": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    files_by_path = {f.path: f for f in pkg.files}

    # 主文件条目仍在且行为不回归
    main = files_by_path["robots/req_asset_mf.urdf"]
    assert pkg.files[0].path == "robots/req_asset_mf.urdf"  # 主文件在列表首位
    assert main.format == "urdf"
    assert main.downloaded is True
    assert main.checksum_sha256 == hashlib.sha256(urdf).hexdigest()

    # 资产条目：format 语义推断 + downloaded=True + 校验和与磁盘实际一致
    stl = files_by_path["robots/meshes/base.stl"]
    assert stl.req_id == "req_asset_mf"
    assert stl.format == "mesh"
    assert stl.downloaded is True
    assert stl.file_url == "https://example.com/panda.urdf"
    assert stl.local_path == "robots/meshes/base.stl"
    assert stl.file_size == len(b"stl-bytes")
    assert stl.checksum_sha256 == hashlib.sha256(b"stl-bytes").hexdigest()
    assert hashlib.sha256((package_dir / stl.path).read_bytes()).hexdigest() == stl.checksum_sha256
    assert stl.transformations == ["written_to:robots/meshes/base.stl"]

    png = files_by_path["robots/textures/uv.png"]
    assert png.format == "texture"
    assert png.checksum_sha256 == hashlib.sha256(b"png-bytes").hexdigest()
    assert hashlib.sha256((package_dir / png.path).read_bytes()).hexdigest() == (
        hashlib.sha256(b"png-bytes").hexdigest()
    )

    unknown = files_by_path["robots/config/unknown.zzz"]
    assert unknown.format == "asset"
    assert unknown.downloaded is True

    # 被剥离到空/.. 的资产不落盘、不进 manifest
    assert "robots/.." not in files_by_path

    # checksums.txt 覆盖主文件与全部资产文件路径
    checksums_txt = (package_dir / "checksums.txt").read_text(encoding="utf-8").splitlines()
    for f in pkg.files:
        assert f"{f.checksum_sha256}  {f.path}" in checksums_txt


def test_assemble_uses_original_format_extension(output_dir: Path) -> None:
    """P0-3：原始格式为 xacro/mjcf 时主文件扩展名随之变化。"""
    mjcf = b'<mujoco model="x"><worldbody/></mujoco>'
    item = ParsedItem(
        req_id="req_mj",
        req_type=DataReqType.SIM_CONFIG,
        name="req_mj",
        canonical_format="xml",
        output_path="unused",
        data=mjcf,
        raw_bytes=mjcf,
        assets={},
        provenance=ProvenanceEntry(
            source=DataSource.GITHUB,
            source_url="https://example.com/scene.xml",
            retrieved_at=_FIXED_TIME,
            original_format="mjcf",
        ),
    )
    out = node_assemble({"parsed_data": {"req_mj": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert (package_dir / "sim_config/req_mj.xml").is_file()
    assert pkg.files[0].path == "sim_config/req_mj.xml"


def test_assemble_python_raw_config_uses_py_extension(output_dir: Path) -> None:
    """D4 修复：IsaacLab python 原始配置以 .py 落盘（不再因 canonical=mjcf 写成 .xml）。"""
    py_source = b"from isaaclab_assets import FRANKA_PANDA\n"
    item = ParsedItem(
        req_id="req_py",
        req_type=DataReqType.SIM_CONFIG,
        name="req_py",
        canonical_format="mjcf",  # SimConfigSkill 对 python 输入的降级 canonical 格式
        output_path="unused",
        data=b"<mujoco model='generated_fallback'><worldbody/></mujoco>",
        raw_bytes=py_source,
        assets={},
        provenance=ProvenanceEntry(
            source=DataSource.ISAAC,
            source_url="https://raw.githubusercontent.com/isaac-sim/IsaacLab/release/3.0.0-beta2/source/isaaclab_assets/isaaclab_assets/robots/franka.py",
            retrieved_at=_FIXED_TIME,
            original_format="python",
        ),
    )
    out = node_assemble({"parsed_data": {"req_py": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    # 原始 python 字节以 .py 落盘（内容为 python 源码而非 XML）
    assert (package_dir / "sim_config/req_py.py").is_file()
    assert (package_dir / "sim_config/req_py.py").read_bytes() == py_source
    assert not (package_dir / "sim_config/req_py.xml").exists()
    assert pkg.files[0].path == "sim_config/req_py.py"


# ─── P0-4: 未下载大文件引用 → manifest downloaded=false ───


def test_assemble_reference_marks_not_downloaded(output_dir: Path) -> None:
    """P0-4：带 reference 的项在 manifest 中标记 downloaded=false 并记录远端 URL。"""
    item = ParsedItem(
        req_id="req_big",
        req_type=DataReqType.DATASET,
        name="req_big",
        canonical_format="json",
        output_path="unused",
        data=b'{"dataset_id": "x"}',
        provenance=ProvenanceEntry(
            source=DataSource.GRASPNET,
            source_url="https://huggingface.co/datasets/x",
            retrieved_at=_FIXED_TIME,
            original_format="json",
        ),
        reference=RawReference(
            url="https://example.com/big.tar",
            file_size=12345,
            download_hint="https://mirror.example.com/big.tar",
            reason="过大",
        ),
    )
    out = node_assemble({"parsed_data": {"req_big": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    f = pkg.files[0]
    assert f.downloaded is False
    assert f.file_url == "https://example.com/big.tar"
    assert f.file_size == 12345
    assert f.local_path == ""
    # 未下载的大文件不落盘，但仍保留 metadata 的落盘路径
    assert f.path == "resources/req_big.json"
    assert (package_dir / f.path).is_file()


def test_assemble_no_reference_marks_downloaded(output_dir: Path) -> None:
    """P0-4：不带 reference 的项标记 downloaded=true 且 local_path/file_url 取已落盘信息。"""
    item = _item("req_010", DataReqType.MESH, "stl")
    out = node_assemble({"parsed_data": {"req_010": item}})
    pkg = out["experiment_package"]

    f = pkg.files[0]
    assert f.downloaded is True
    assert f.local_path == "objects/req_010.stl"
    assert f.file_url == "https://example.com"  # provenance.source_url
    assert f.file_size == len(b"<payload>")  # 已写字节数


# ─── P0-5: 校验和与状态推导 ───


def test_assemble_writes_checksum_and_checksums_txt(output_dir: Path) -> None:
    """P0-5：manifest 记录文件 SHA-256，且 checksums.txt 含 "<sha256>  <path>" 行。"""
    item = _item("req_cksum", DataReqType.MESH, "stl")
    out = node_assemble({"parsed_data": {"req_cksum": item}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    f = pkg.files[0]
    expected = hashlib.sha256(b"<payload>").hexdigest()
    assert f.checksum_sha256 == expected
    # 磁盘上实际文件字节与 manifest 的 checksum 一致
    assert hashlib.sha256((package_dir / f.path).read_bytes()).hexdigest() == expected

    checksums_txt = package_dir / "checksums.txt"
    assert checksums_txt.is_file()
    lines = checksums_txt.read_text(encoding="utf-8").splitlines()
    assert f"{expected}  {f.path}" in lines


def test_assemble_status_failed_when_no_files(output_dir: Path) -> None:
    """P0-5：无任何落盘文件 → status=failed。"""
    out = node_assemble({"parsed_data": {}, "data_requirements": [], "missing_items": []})
    pkg = out["experiment_package"]
    assert pkg.package_info["status"] == "failed"


def test_assemble_status_failed_when_required_missing(output_dir: Path) -> None:
    """P0-5：REQUIRED 优先级需求缺失 → status=failed（即使有正常落盘文件）。"""
    req = DataReq(
        req_id="req_miss",
        req_type=DataReqType.MESH,
        description="必须的网格数据",
        priority=Priority.REQUIRED,
    )
    missing = MissingItem(
        req_id="req_miss",
        req_type=DataReqType.MESH,
        description="必须的网格数据",
        reason="未找到",
    )
    state: SystemState = {
        "parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")},
        "data_requirements": [req],
        "missing_items": [missing],
    }
    out = node_assemble(state)
    pkg = out["experiment_package"]
    # 1 个主文件 + 1 个质量解释条目（解释条目不影响状态推导）
    assert len(pkg.files) == 2
    assert pkg.package_info["status"] == "failed"


def test_assemble_status_partial_when_optional_missing(output_dir: Path) -> None:
    """P0-5：非 REQUIRED 需求缺失 + 有落盘文件 → status=partial。"""
    req = DataReq(
        req_id="req_miss",
        req_type=DataReqType.CODE,
        description="可选的参考代码",
        priority=Priority.OPTIONAL,
    )
    missing = MissingItem(
        req_id="req_miss",
        req_type=DataReqType.CODE,
        description="可选的参考代码",
        reason="未找到",
    )
    state: SystemState = {
        "parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")},
        "data_requirements": [req],
        "missing_items": [missing],
    }
    out = node_assemble(state)
    pkg = out["experiment_package"]
    assert pkg.package_info["status"] == "partial"


def test_assemble_status_complete_when_all_success(output_dir: Path) -> None:
    """P0-5：解析全成功无缺失 → status=complete。"""
    out = node_assemble({"parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")}})
    pkg = out["experiment_package"]
    assert pkg.package_info["status"] == "complete"


def test_assemble_package_info_contract(output_dir: Path) -> None:
    """P0-5：package_info 含 pipeline_version/license/citation 契约字段。"""
    out = node_assemble({"parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")}})
    pkg = out["experiment_package"]
    assert pkg.package_info["pipeline_version"] == PIPELINE_VERSION
    assert pkg.package_info["license"] == ""
    assert pkg.package_info["citation"] == ""


def test_assemble_package_info_run_id_passthrough(output_dir: Path) -> None:
    """B2：state.run_id 透传到 manifest.package_info.run_id。"""
    out = node_assemble(
        {
            "parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")},
            "run_id": "20260810-123456-abcdef01",
        }
    )
    pkg = out["experiment_package"]
    assert pkg.package_info["run_id"] == "20260810-123456-abcdef01"


def test_assemble_package_info_run_id_default_empty(output_dir: Path) -> None:
    """B2：state 不含 run_id（单跑/测试）→ package_info.run_id 为空串。"""
    out = node_assemble({"parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")}})
    pkg = out["experiment_package"]
    assert pkg.package_info["run_id"] == ""


def test_assemble_package_info_demo_false(output_dir: Path) -> None:
    """E3：真实流程产物 package_info.demo=false（与演示流程 demo=true 区分）。"""
    out = node_assemble({"parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")}})
    pkg = out["experiment_package"]
    assert pkg.package_info["demo"] == "false"


# ─── P1-2: data_source_quality 显式化 / is_fallback 透传 ───


def test_assemble_data_source_quality_default_unknown(output_dir: Path) -> None:
    """ParsedItem 未标注 data_source_quality（默认 None）→ manifest 记为 "unknown"（不再默认 "fallback"）。"""
    item = _item("req_q_unknown", DataReqType.MESH, "stl")
    out = node_assemble({"parsed_data": {"req_q_unknown": item}})
    pkg = out["experiment_package"]

    assert pkg.files[0].data_source_quality == "unknown"


def test_assemble_data_source_quality_keeps_real(output_dir: Path) -> None:
    """ParsedItem 标注 data_source_quality="real" → manifest 原样保留，不降级为 unknown/fallback。"""
    item = ParsedItem(
        req_id="req_q_real",
        req_type=DataReqType.MESH,
        name="req_q_real",
        canonical_format="stl",
        output_path="unused",
        data=b"<payload>",
        provenance=_provenance(),
        data_source_quality="real",
    )
    out = node_assemble({"parsed_data": {"req_q_real": item}})
    pkg = out["experiment_package"]

    assert pkg.files[0].data_source_quality == "real"


def test_assemble_is_fallback_passthrough(output_dir: Path) -> None:
    """ParsedItem.is_fallback=True → manifest 透传 True；未设置（默认 False）时为 False。"""
    item = ParsedItem(
        req_id="req_fb",
        req_type=DataReqType.MESH,
        name="req_fb",
        canonical_format="stl",
        output_path="unused",
        data=b"<payload>",
        provenance=_provenance(),
        is_fallback=True,
    )
    out = node_assemble({"parsed_data": {"req_fb": item}})
    pkg = out["experiment_package"]
    assert pkg.files[0].is_fallback is True

    item_default = _item("req_fb_default", DataReqType.MESH, "stl")
    out_default = node_assemble({"parsed_data": {"req_fb_default": item_default}})
    assert out_default["experiment_package"].files[0].is_fallback is False


def test_assemble_writes_units_json(output_dir: Path) -> None:
    """D1：semantic_map.json 落盘（原 units.json 字段保留），每 req 记录 units/coordinate_frame/timestamp_epoch。"""
    item_urdf = _item("req_urdf", DataReqType.ROBOT_URDF, "urdf")
    item_urdf.units = "meter"
    item_urdf.coordinate_frame = "world"
    item_urdf.timestamp_epoch = 1710000000.0

    item_mesh = _item("req_mesh", DataReqType.MESH, "stl")
    # 未标注单位：保持默认空串/None

    out = node_assemble({"parsed_data": {"req_urdf": item_urdf, "req_mesh": item_mesh}})
    package_dir = Path(out["experiment_package"].output_dir)

    units_file = package_dir / "semantic_map.json"
    assert units_file.is_file()
    units_meta = json.loads(units_file.read_text(encoding="utf-8"))

    assert units_meta["req_urdf"] == {
        "units": "meter",
        "coordinate_frame": "world",
        "timestamp_epoch": 1710000000.0,
        "is_llm": False,
    }
    assert units_meta["req_mesh"] == {
        "units": "",
        "coordinate_frame": "",
        "timestamp_epoch": None,
        "is_llm": False,
    }


def test_assemble_semantic_map_with_llm_convention(output_dir: Path) -> None:
    """D2：state.semantic_map 注入 → semantic_map.json 追加 LLM 语义字段（is_llm=True）。"""
    from rdi.intelligence.schemas import SemanticConvention

    item = _item("req_grasp", DataReqType.GRASP, "CanonicalGrasp")
    item.units = "millimeter"
    item.coordinate_frame = "object_center"
    item.timestamp_epoch = 1710000000.0
    conv = SemanticConvention(
        dataset_name="mygrid",
        semantic_type="grasp_pose",
        rotation="quaternion_xyzw",
        origin="object_center",
        unit="millimeter",
        field_map={"trans": "position"},
        confidence=0.85,
        needs_human_review=True,
    )
    state: SystemState = {
        "parsed_data": {"req_grasp": item},
        "semantic_map": {"req_grasp": conv},
    }

    out = node_assemble(state)
    package_dir = Path(out["experiment_package"].output_dir)

    meta = json.loads((package_dir / "semantic_map.json").read_text(encoding="utf-8"))
    entry = meta["req_grasp"]
    # 原 units.json 字段保留
    assert entry["units"] == "millimeter"
    assert entry["coordinate_frame"] == "object_center"
    assert entry["timestamp_epoch"] == 1710000000.0
    # LLM 语义字段追加
    assert entry["semantic_type"] == "grasp_pose"
    assert entry["rotation"] == "quaternion_xyzw"
    assert entry["origin"] == "object_center"
    assert entry["field_map"] == {"trans": "position"}
    assert entry["confidence"] == 0.85
    assert entry["needs_human_review"] is True
    assert entry["is_llm"] is True


# ─── ⑤ 质量报告解释：LLM 决策层 / 规则模板兜底 ───


@pytest.fixture(autouse=True)
def _no_llm_explain(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认禁用 LLM 质量解释（explain_quality 恒返回 None），防真实 API 请求（慢且非确定）。"""
    monkeypatch.setattr(
        "rdi.graph.nodes.assemble._decisions.explain_quality",
        lambda **kwargs: None,
    )


def test_assemble_quality_explanation_llm_success(
    output_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """⑤ LLM 成功：quality_explanation.md 落盘并标注 LLM 来源，manifest 追加解释条目，包状态不受影响。"""
    from rdi.intelligence.schemas import QualityExplanation

    qe = QualityExplanation(
        summary="整体质量良好，数据可直接用于抓取仿真",
        strengths=["来源可靠", "完整度较高"],
        risks=["存在部分缺失项"],
        recommendations=["补充缺失数据"],
        usage_guidance="适用于 UR5 抓取仿真验证",
        confidence=0.9,
    )
    monkeypatch.setattr(
        "rdi.graph.nodes.assemble._decisions.explain_quality",
        lambda **kwargs: qe,
    )
    # 空数据包：解释仍生成，且包状态推导/质量报告数字不被解释条目污染
    out = node_assemble({"parsed_data": {}, "data_requirements": [], "missing_items": []})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert out["quality_explanation"] is qe
    md = package_dir / "quality_explanation.md"
    assert md.is_file()
    md_text = md.read_text(encoding="utf-8")
    assert "由 LLM 基于 manifest.json 生成" in md_text
    assert "整体质量良好" in md_text

    qf = [f for f in pkg.files if f.path == "quality_explanation.md"]
    assert len(qf) == 1
    assert qf[0].format == "md"
    assert qf[0].req_id == "package"
    assert qf[0].transformations == ["generated:llm_explanation"]
    assert qf[0].confidence == 0.9
    assert qf[0].file_size == len(md_text.encode("utf-8"))
    assert qf[0].checksum_sha256 == hashlib.sha256(md_text.encode("utf-8")).hexdigest()
    # 包状态与质量报告数字不受解释条目影响（空数据包仍 failed / fulfilled=0）
    assert pkg.package_info["status"] == "failed"
    assert pkg.quality_report.fulfilled == 0
    assert any("质量解释已生成（LLM 生成）" in line for line in pkg.provenance_log)
    assert any("质量解释已生成（LLM 生成）" in line for line in out["provenance"])


def test_assemble_quality_explanation_rule_fallback(output_dir: Path) -> None:
    """⑤ LLM 失败（返回 None）：规则模板解释仍落盘，manifest 条目保留，返回值 quality_explanation 为 None。"""
    out = node_assemble({"parsed_data": {"req_ok": _item("req_ok", DataReqType.MESH, "stl")}})
    pkg = out["experiment_package"]
    package_dir = Path(pkg.output_dir)

    assert out["quality_explanation"] is None
    md = package_dir / "quality_explanation.md"
    assert md.is_file()
    md_text = md.read_text(encoding="utf-8")
    assert "规则模板生成（LLM 不可用）" in md_text
    assert "需求总数" in md_text

    qf = [f for f in pkg.files if f.path == "quality_explanation.md"]
    assert len(qf) == 1
    assert qf[0].transformations == ["generated:rule_explanation"]
    assert qf[0].confidence == 0.5
    # 主文件在前、解释条目在后
    assert pkg.files[0].path == "objects/req_ok.stl"
    assert pkg.files[-1].path == "quality_explanation.md"
    # provenance 记录规则兜底标注（package.provenance_log 与返回值 provenance 均有）
    assert any("质量解释已生成（规则模板生成）" in line for line in pkg.provenance_log)
    assert any("质量解释已生成（规则模板生成）" in line for line in out["provenance"])


def test_assemble_llm_usage_appends_quality_decision(output_dir: Path) -> None:
    """⑤ llm_usage 为累积字段（Annotated operator.add）：节点只返回本次 explain_quality 条目（含 elapsed），既有记录由框架拼接。"""
    out = node_assemble({"llm_usage": [{"decision": "retrieval_plan", "status": "ok", "model": "mock"}]})
    assert len(out["llm_usage"]) == 1
    entry = out["llm_usage"][0]
    assert entry["decision"] == "explain_quality"
    assert entry["req_id"] == "package"
    assert entry["status"] == "fallback"
    assert isinstance(entry["elapsed"], float)
    assert out["quality_explanation"] is None
