# tests/unit/skills/test_mesh.py
"""MeshSkill 单元测试（同步）。

覆盖 spec「MeshSkill — 3D 几何数据处理」全部 scenario：
- 加载 STL 成功
- 毫米→米单位统一
- 质心对齐
- 多精度生成（含 >400 面简化路径的优雅降级）
- 缺面检测（非水密 / 面数过少 warning）
- 处理失败降级（损坏字节）
"""

import io
import zipfile
from pathlib import Path

import numpy as np
import pytest
import trimesh

from rdi.models.common import StandardResult
from rdi.skills.mesh_process import MeshSkill

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "mesh"


@pytest.fixture(scope="module")
def hand_stl_bytes() -> bytes:
    """Franka hand.stl 样本字节。"""
    return (_SAMPLE_DIR / "hand.stl").read_bytes()


@pytest.fixture(scope="module")
def triangle_obj_bytes() -> bytes:
    """单三角形 OBJ 样本字节（非水密、1 面）。"""
    return (_SAMPLE_DIR / "triangle.obj").read_bytes()


# ─── Scenario: 加载 STL 成功 ───


def test_parse_stl_success(hand_stl_bytes: bytes) -> None:
    result = MeshSkill().process(hand_stl_bytes, fmt="stl")
    assert result.success is True
    assert result.canonical_format == "trimesh.Trimesh"
    assert isinstance(result.data, trimesh.Trimesh)
    assert hasattr(result.data, "is_watertight")


# ─── Scenario: 质心对齐 ───


def test_standardize_recenter_to_centroid(hand_stl_bytes: bytes) -> None:
    skill = MeshSkill()
    mesh = skill.parse(hand_stl_bytes, "stl")
    standardized, transformations = skill.standardize(mesh)
    assert "recenter_to_centroid" in transformations
    # hand.stl 水密，center_mass 有限；recenter 后质心近似原点
    assert np.allclose(standardized.center_mass, 0, atol=1e-6)


# ─── Scenario: 毫米→米单位统一 ───


def test_mm_to_m_conversion(hand_stl_bytes: bytes) -> None:
    skill = MeshSkill()
    mesh = skill.parse(hand_stl_bytes, "stl")
    mesh.vertices *= 1000.0  # 模拟毫米单位
    extent_before = float(mesh.extents.max())
    assert extent_before > 10.0
    standardized, transformations = skill.standardize(mesh)
    assert "unit_mm_to_m" in transformations
    extent_after = float(standardized.extents.max())
    assert extent_after < extent_before / 999.0


# ─── Scenario: 缺面检测 —— 非水密 ───


def test_non_watertight_warning(triangle_obj_bytes: bytes) -> None:
    result = MeshSkill().process(triangle_obj_bytes, fmt="obj")
    assert result.success is True
    assert any("非水密" in w for w in result.warnings)


# ─── Scenario: 缺面检测 —— 面数过少 ───


def test_low_face_count_warning(triangle_obj_bytes: bytes) -> None:
    result = MeshSkill().process(triangle_obj_bytes, fmt="obj")
    assert result.success is True
    assert any("面数过少" in w for w in result.warnings)


# ─── Scenario: 多精度生成 ───


def test_generate_lod(hand_stl_bytes: bytes) -> None:
    skill = MeshSkill()
    mesh = skill.parse(hand_stl_bytes, "stl")
    lod = skill.generate_lod(mesh)
    assert "high" in lod and "collision" in lod
    # hand.stl = 200 面 ≤ 400 → collision 退化为原 mesh（同对象）
    if len(mesh.faces) > 400:
        assert len(lod["collision"].faces) < len(lod["high"].faces)
    else:
        assert lod["collision"] is lod["high"]


def test_generate_lod_high_face_mesh() -> None:
    """面数 > 400 走简化路径；fast-simplification 缺失时优雅退化为原 mesh。"""
    skill = MeshSkill()
    mesh = trimesh.creation.icosphere(subdivisions=3)
    assert len(mesh.faces) > 400
    lod = skill.generate_lod(mesh)
    assert "high" in lod and "collision" in lod
    assert len(lod["collision"].faces) <= len(lod["high"].faces)


# ─── Scenario: 处理失败降级 ───


def test_parse_invalid_bytes_degrades() -> None:
    result = MeshSkill().process(b"not a mesh", fmt="stl")
    assert result.success is False
    assert result.errors
    assert result.data is None


def test_metadata_json_degrades_to_fallback() -> None:
    """fetch 显式降级的 metadata JSON → success + is_fallback（PASS_WITH_FALLBACK 语义）。"""
    import json

    payload = {"dataset_id": "ycb-1", "reason": "no single mesh file available"}
    result = MeshSkill().process(
        json.dumps(payload).encode("utf-8"), fmt="json", name="banana"
    )
    assert result.success is True
    assert result.is_fallback is True
    assert result.data_source_quality == "fallback"
    assert result.data is not None
    assert any("元数据" in w for w in result.warnings)


# ─── validate 契约 ───


def test_validate_success_path(hand_stl_bytes: bytes) -> None:
    result = MeshSkill().process(hand_stl_bytes, fmt="stl")
    report = MeshSkill().validate(result)
    assert report.is_valid is True


def test_validate_failure_path() -> None:
    result = StandardResult(success=False, canonical_format="trimesh.Trimesh")
    report = MeshSkill().validate(result)
    assert report.is_valid is False
    assert any(i.severity.value == "error" for i in report.issues)


# ─── glb / zip 支持 ───


def _box_glb_bytes() -> bytes:
    """生成一个最小 glb（box）字节。"""
    mesh = trimesh.creation.box(extents=[0.1, 0.1, 0.1])
    return mesh.export(file_type="glb")


def test_parse_glb_success() -> None:
    """glb 输入可被 trimesh 加载并标准化为 Trimesh。"""
    data = _box_glb_bytes()
    result = MeshSkill().process(data, fmt="glb", name="box")
    assert result.success is True
    assert result.canonical_format == "trimesh.Trimesh"
    assert isinstance(result.data, trimesh.Trimesh)
    assert len(result.data.faces) > 0
    assert result.output_path == "objects/box.stl"


def test_parse_zip_success() -> None:
    """zip 输入解压后找到第一个 mesh 文件并加载。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("model.config", "<model/>")
        zf.writestr(
            "meshes/box.obj", trimesh.creation.box(extents=[0.2, 0.2, 0.2]).export(file_type="obj")
        )
    result = MeshSkill().process(buf.getvalue(), fmt="zip", name="zipped_box")
    assert result.success is True
    assert result.canonical_format == "trimesh.Trimesh"
    assert isinstance(result.data, trimesh.Trimesh)
    assert len(result.data.faces) > 0
    assert result.output_path == "objects/zipped_box.stl"


def test_parse_zip_no_mesh_degrades() -> None:
    """zip 中无支持 mesh 时降级。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("readme.txt", "no mesh")
    result = MeshSkill().process(buf.getvalue(), fmt="zip")
    assert result.success is False
    assert result.data is None
    assert any("zip" in e for e in result.errors)
