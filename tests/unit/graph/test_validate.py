"""validate 节点单元测试。

覆盖基础校验规则与 URDF / mesh / sim_config / grasp 的可加载性深度校验。
"""

from __future__ import annotations

import io
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
import trimesh

from rdi.graph.nodes.assemble import node_assemble
from rdi.graph.nodes.validate import node_validate
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry, Severity
from rdi.models.goal import DataReq
from rdi.models.parsed import MissingItem

if TYPE_CHECKING:
    from rdi.graph.state import SystemState

_SAMPLE_DIR = Path(__file__).parent.parent / "skills" / "sample_data"
_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance(fmt: str = "bin") -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.FRANKA,
        source_url="https://example.com",
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


def _item(
    req_id: str,
    req_type: DataReqType,
    data: object,
    fmt: str = "bin",
    completeness: float = 100.0,
    confidence: float = 1.0,
    output_path: str = "files/out.bin",
) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=req_id,
        canonical_format=fmt,
        output_path=output_path,
        data=data,
        provenance=_provenance(fmt),
        completeness_pct=completeness,
        confidence_score=confidence,
    )


def test_validate_empty_data_is_error() -> None:
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.MESH, b"")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and i.message == "解析数据为空" and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_low_completeness_and_confidence_are_warnings() -> None:
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.MESH,
                b"ignore",
                completeness=80.0,
                confidence=0.8,
            )
        },
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "完整度不足" in i.message and i.severity == Severity.WARNING
        for i in out["validation_issues"]
    )
    assert any(
        i.req_id == "r1" and "置信度不足" in i.message and i.severity == Severity.WARNING
        for i in out["validation_issues"]
    )


def test_validate_required_missing_item_is_error() -> None:
    state: SystemState = {
        "parsed_data": {},
        "missing_items": [
            MissingItem(
                req_id="r1",
                req_type=DataReqType.ROBOT_URDF,
                description="urdf",
                reason="未找到",
            )
        ],
        "data_requirements": [
            DataReq(
                req_id="r1",
                req_type=DataReqType.ROBOT_URDF,
                description="urdf",
                priority=Priority.REQUIRED,
            )
        ],
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "必需需求缺失" in i.message and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_urdf_success() -> None:
    urdf_bytes = (_SAMPLE_DIR / "urdf" / "allegro_hand_r.urdf").read_bytes()
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.ROBOT_URDF, urdf_bytes, fmt="urdf")},
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "URDF 无法解析" in i.message for i in out["validation_issues"]
    )


def test_validate_urdf_failure() -> None:
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.ROBOT_URDF, b"not a urdf", fmt="urdf")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "URDF 无法解析" in i.message and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_mesh_bytes_success() -> None:
    mesh_bytes = (_SAMPLE_DIR / "mesh" / "hand.stl").read_bytes()
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.MESH,
                mesh_bytes,
                fmt="trimesh.Trimesh",
                output_path="objects/hand.stl",
            )
        },
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and ("Mesh 无法加载" in i.message or "面片" in i.message)
        for i in out["validation_issues"]
    )


def test_validate_mesh_trimesh_object_success() -> None:
    mesh = trimesh.creation.box(extents=[1.0, 1.0, 1.0])
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.MESH, mesh, fmt="trimesh.Trimesh")},
    }
    out = node_validate(state)
    assert not any(i.req_id == "r1" and "面片" in i.message for i in out["validation_issues"])


def test_validate_mesh_failure_invalid_bytes() -> None:
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.MESH, b"not a mesh", fmt="stl")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1"
        and ("Mesh 无法加载" in i.message or "Mesh 不包含任何面片" in i.message)
        and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_mesh_failure_zero_faces() -> None:
    empty_mesh = trimesh.Trimesh(vertices=[], faces=[])
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.MESH, empty_mesh, fmt="trimesh.Trimesh")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "Mesh 不包含任何面片" in i.message and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_sim_config_xml_success() -> None:
    xml_bytes = (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes()
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, xml_bytes, fmt="xml")},
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "XML/MJCF 无法解析" in i.message for i in out["validation_issues"]
    )


def test_validate_sim_config_xml_failure() -> None:
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, b"<not>xml", fmt="xml")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "XML/MJCF 无法解析" in i.message and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )


def test_validate_sim_config_python_success() -> None:
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.SIM_CONFIG,
                "scene = {'timestep': 0.01}\n",
                fmt="python",
            )
        },
    }
    out = node_validate(state)
    assert not any(i.req_id == "r1" and "语法错误" in i.message for i in out["validation_issues"])


def test_validate_sim_config_python_failure() -> None:
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.SIM_CONFIG,
                "def broken(:\n",
                fmt="python",
            )
        },
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "Python 仿真配置语法错误" in i.message
        for i in out["validation_issues"]
    )


def test_validate_grasp_dict_success() -> None:
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.GRASP,
                {"translations": np.zeros((10, 3)), "rotations": np.zeros((10, 3, 3))},
                fmt="CanonicalGrasp",
            )
        },
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "Grasp 数据缺少必要字段" in i.message for i in out["validation_issues"]
    )


def test_validate_grasp_dict_failure() -> None:
    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.GRASP,
                {"score": 0.5},
                fmt="CanonicalGrasp",
            )
        },
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "Grasp 数据缺少必要字段" in i.message for i in out["validation_issues"]
    )


def test_validate_grasp_npz_success() -> None:
    buf = io.BytesIO()
    np.savez(buf, translations=np.zeros((5, 3)), rotations=np.zeros((5, 3, 3)))
    npz = np.load(io.BytesIO(buf.getvalue()))
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.GRASP, npz, fmt="npz")},
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "Grasp 数据缺少必要字段" in i.message for i in out["validation_issues"]
    )


def test_validate_other_type_no_loadability_check() -> None:
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.PAPER, b"paper bytes", fmt="text")},
    }
    out = node_validate(state)
    # PAPER 不应触发任何可加载性校验，仅有空数据检查
    assert len(out["validation_issues"]) == 0


def test_validate_loadability_never_crashes() -> None:
    class BadData:
        """模拟会在校验中触发异常的 data。"""

    state: SystemState = {
        "parsed_data": {
            "r1": _item(
                "r1",
                DataReqType.MESH,
                BadData(),  # type: ignore[arg-type]
                fmt="trimesh.Trimesh",
            )
        },
    }
    # 不应抛出异常
    out = node_validate(state)
    assert "validation_issues" in out
    assert isinstance(out["validation_issues"], list)


def test_validate_sim_config_mujoco_runtime_passed() -> None:
    """mujoco 可用时，合法 MJCF 应通过加载 + 一步仿真，runtime_check 记为 passed。"""
    pytest.importorskip("mujoco")
    xml_bytes = (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes()
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, xml_bytes, fmt="xml")},
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "无法解析" in i.message for i in out["validation_issues"]
    )
    assert out["runtime_check"]["r1"]["status"] == "passed"


def test_validate_sim_config_invalid_xml_still_error() -> None:
    """非法 XML 即使 mujoco 可用仍记为 ERROR，runtime_check 为 failed。"""
    pytest.importorskip("mujoco")
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, b"<not>xml", fmt="xml")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1"
        and "XML/MJCF 无法解析" in i.message
        and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )
    assert out["runtime_check"]["r1"]["status"] == "failed"


def test_validate_sim_config_mujoco_compile_failure_is_error() -> None:
    """XML 语法合法但 MuJoCo 编译失败（actuator 引用不存在的 joint）记为 ERROR。"""
    pytest.importorskip("mujoco")
    bad_mjcf = (
        b"<mujoco>"
        b"<worldbody><body><joint name='j1'/><geom type='sphere' size='0.1'/></body></worldbody>"
        b"<actuator><motor joint='no_such_joint'/></actuator>"
        b"</mujoco>"
    )
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, bad_mjcf, fmt="mjcf")},
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1"
        and "MJCF 无法通过 MuJoCo 验证" in i.message
        and i.severity == Severity.ERROR
        for i in out["validation_issues"]
    )
    assert out["runtime_check"]["r1"]["status"] == "failed"


def test_validate_sim_config_runtime_check_skipped_without_mujoco(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """mujoco 不可导入时保持 XML 语法校验行为，runtime_check 记为 skipped。"""
    monkeypatch.setattr("rdi.graph.nodes.validate.mujoco", None)
    xml_bytes = (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes()
    state: SystemState = {
        "parsed_data": {"r1": _item("r1", DataReqType.SIM_CONFIG, xml_bytes, fmt="xml")},
    }
    out = node_validate(state)
    assert not any(
        i.req_id == "r1" and "无法解析" in i.message for i in out["validation_issues"]
    )
    assert out["runtime_check"]["r1"]["status"] == "skipped"


def test_validate_sim_config_missing_asset_is_not_error() -> None:
    """引用外部 mesh 但资源缺失的 MJCF 应降级为 WARNING（资源引用未解析），而非 ERROR。"""
    pytest.importorskip("mujoco")
    missing_mesh_mjcf = (
        b'<mujoco model="x"><asset><mesh name="m" file="no_such_dir/no_such.stl"/></asset>'
        b"<worldbody><geom type='mesh' mesh='m'/></worldbody></mujoco>"
    )
    state: SystemState = {
        "parsed_data": {
            "r1": _item("r1", DataReqType.SIM_CONFIG, missing_mesh_mjcf, fmt="xml")
        },
    }
    out = node_validate(state)
    assert any(
        i.req_id == "r1" and "资源引用未解析" in i.message
        for i in out["validation_issues"]
    )
    assert not any(
        i.req_id == "r1" and i.severity == Severity.ERROR for i in out["validation_issues"]
    )
    assert out["runtime_check"]["r1"]["status"] == "skipped"


def test_validate_runtime_check_written_to_manifest(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """validate 输出的 runtime_check 应被 assemble 写入 PackageManifest。"""
    pytest.importorskip("mujoco")
    xml_bytes = (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes()
    item = _item("r1", DataReqType.SIM_CONFIG, xml_bytes, fmt="xml")
    validate_out = node_validate({"parsed_data": {"r1": item}})
    assert validate_out["runtime_check"]["r1"]["status"] == "passed"

    monkeypatch.setattr("rdi.graph.nodes.assemble.settings.output_dir", str(tmp_path))
    assemble_out = node_assemble(
        {
            "parsed_data": {"r1": item},
            "validation_issues": validate_out["validation_issues"],
            "runtime_check": validate_out["runtime_check"],
        }
    )
    pkg = assemble_out["experiment_package"]
    assert pkg.runtime_check["r1"]["status"] == "passed"
