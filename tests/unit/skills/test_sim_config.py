# tests/unit/skills/test_sim_config.py
"""SimConfigSkill 单元测试（同步）。

覆盖 spec「SimConfigSkill — 仿真环境配置解析」全部 scenario：
- 解析 MJCF 成功
- 场景无物体（WARNING）
- Isaac 配置降级（描述性解析，未生成 USD）
- MJCF 生成（反向 roundtrip）
- 未知格式失败
- 损坏 XML 降级
"""

from pathlib import Path

import pytest

from rdi.models.common import Severity
from rdi.skills.sim_config import (
    Camera,
    SceneDescription,
    SceneObject,
    SimConfigSkill,
)

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "sim"


def _read(name: str) -> bytes:
    return (_SAMPLE_DIR / name).read_bytes()


# ─── Scenario: 解析 MJCF 成功 ───


def test_parse_mujoco_success() -> None:
    data = _read("sample_mujoco.xml")
    result = SimConfigSkill().process(data, fmt="mjcf")
    assert result.success is True
    assert result.canonical_format == "xml"
    assert isinstance(result.data, bytes)
    # 保留 SceneDescription 供内省：从返回的 XML 字节二次解析
    scene = SimConfigSkill().parse_mujoco(result.data)
    assert isinstance(scene, SceneDescription)
    assert scene.source_format == "mjcf"
    assert len(scene.objects) >= 1
    assert len(scene.cameras) >= 1
    obj = scene.objects[0]
    assert isinstance(obj, SceneObject)
    assert obj.name  # 样本 geom 均带 name
    assert len(obj.pos) == 3
    assert len(obj.size) == 3
    cam = scene.cameras[0]
    assert isinstance(cam, Camera)
    assert len(cam.pos) == 3
    assert cam.fov > 0
    assert result.confidence_score == 1.0


# ─── Scenario: 真实 MJCF XML 直通（C13） ───


def test_real_mjcf_passthrough_preserves_bytes() -> None:
    """真实 MJCF XML 原样直通：data 与输入字节一致，不重建，标注真实来源。"""
    skill = SimConfigSkill()
    data = _read("sample_mujoco.xml")
    result = skill.process(data, fmt="mjcf")
    assert result.success is True
    assert result.data_source_quality == "real"
    assert result.canonical_format == "xml"
    assert result.completeness_pct == 100.0
    assert result.confidence_score == 1.0
    assert result.data == data  # 直通：未经过 parse_mujoco -> to_mjcf 重建
    assert result.warnings == []


def test_real_mjcf_passthrough_xml_fmt() -> None:
    """fmt=xml 同样走直通路径（Adapter 真实场景下载的字节）。"""
    skill = SimConfigSkill()
    data = _read("sample_mujoco.xml")
    result = skill.process(data, fmt="xml")
    assert result.data_source_quality == "real"
    assert result.data == data
    # 直通后仍可二次解析，内省契约不变
    scene = skill.parse_mujoco(result.data)
    assert len(scene.objects) >= 1
    assert len(scene.cameras) >= 1


def test_real_mjcf_empty_scene_warns_no_objects() -> None:
    """直通路径保留「场景无物体」警告（空 worldbody 的真实 MJCF）。"""
    result = SimConfigSkill().process(_read("empty_scene.xml"), fmt="mjcf")
    assert result.data_source_quality == "real"
    assert result.data == _read("empty_scene.xml")
    assert any("场景无物体" in w for w in result.warnings)


# ─── Scenario: MJCF 生成（反向 roundtrip） ───


def test_to_mjcf_roundtrip() -> None:
    skill = SimConfigSkill()
    scene = skill.parse_mujoco(_read("sample_mujoco.xml"))
    generated = skill.to_mjcf(scene)
    assert isinstance(generated, bytes)
    text = generated.decode("utf-8")
    assert "<mujoco" in text
    assert "<geom" in text
    assert "<worldbody>" in text
    # 二次解析：物体 name/type 集合保持一致
    scene2 = skill.parse_mujoco(generated)
    names_before = {o.name for o in scene.objects}
    names_after = {o.name for o in scene2.objects}
    types_before = {o.type for o in scene.objects}
    types_after = {o.type for o in scene2.objects}
    assert names_before == names_after
    assert types_before == types_after
    # 相机也回环
    assert {c.name for c in scene.cameras} == {c.name for c in scene2.cameras}


# ─── Scenario: 场景无物体（WARNING） ───


def test_empty_scene_warning() -> None:
    skill = SimConfigSkill()
    result = skill.process(_read("empty_scene.xml"), fmt="mjcf")
    assert result.success is True
    assert result.warnings  # process 提示场景无物体
    assert any("场景无物体" in w for w in result.warnings)
    assert isinstance(result.data, bytes)
    scene = skill.parse_mujoco(result.data)
    assert scene.objects == []
    # validate 同样产出 WARNING 级 ValIssue
    report = skill.validate(result)
    assert report.is_valid is True  # WARNING 非阻断
    assert any(i.severity == Severity.WARNING and "场景无物体" in i.message for i in report.issues)


# ─── Scenario: Isaac 配置回退为最小 MJCF ───


def test_isaac_fallback_to_mjcf() -> None:
    skill = SimConfigSkill()
    result = skill.process(
        _read("isaac_scene.yaml"),
        fmt="isaac",
        urdf_path="robots/franka.urdf",
        mesh_path="objects/banana.stl",
    )
    assert result.success is True
    assert result.completeness_pct < 100.0
    assert result.confidence_score < 1.0
    assert result.canonical_format == "mjcf"
    assert isinstance(result.data, bytes)
    assert b"<mujoco" in result.data
    assert b"robots/franka.urdf" in result.data
    assert b"objects/banana.stl" in result.data
    assert any("未找到真实 MuJoCo MJCF" in w for w in result.warnings)
    report = skill.validate(result)
    assert report.is_valid is True


# ─── Scenario: 未知格式回退为最小 MJCF ───


def test_unknown_format_fallback_to_mjcf() -> None:
    result = SimConfigSkill().process(b"x", fmt="unknown")
    assert result.success is True
    assert result.canonical_format == "mjcf"
    assert isinstance(result.data, bytes)
    assert b"<mujoco" in result.data
    assert any("未找到真实 MuJoCo MJCF" in w for w in result.warnings)


# ─── Scenario: 损坏 XML 回退为最小 MJCF ───


def test_parse_invalid_xml_fallback_to_mjcf() -> None:
    result = SimConfigSkill().process(b"not xml", fmt="mjcf")
    assert result.success is True
    assert result.canonical_format == "mjcf"
    assert isinstance(result.data, bytes)
    assert b"<mujoco" in result.data
    assert any("未找到真实 MuJoCo MJCF" in w for w in result.warnings)
    report = SimConfigSkill().validate(result)
    assert report.is_valid is True


# ─── Scenario: 生成最小 MJCF ───


def test_generate_minimal_mjcf() -> None:
    skill = SimConfigSkill()
    xml_bytes = skill.generate_minimal_mjcf(
        urdf_path="robots/panda.urdf",
        mesh_path="objects/cube.stl",
    )
    assert isinstance(xml_bytes, bytes)
    text = xml_bytes.decode("utf-8")
    assert "<mujoco" in text
    assert "robots/panda.urdf" in text
    assert "objects/cube.stl" in text
    assert '<mesh file="objects/cube.stl" name="cube"/>' in text
    assert '<geom name="object_geom" type="mesh" mesh="cube"' in text
    assert '<geom name="floor" type="plane"' in text
    assert "<worldbody>" in text
    # 二次解析可得到至少 floor 与 object 两个 geom
    scene = skill.parse_mujoco(xml_bytes)
    assert len(scene.objects) >= 2


def test_generate_minimal_mjcf_without_mesh() -> None:
    skill = SimConfigSkill()
    xml_bytes = skill.generate_minimal_mjcf(urdf_path="robots/panda.urdf", mesh_path=None)
    text = xml_bytes.decode("utf-8")
    assert "<mujoco" in text
    assert "robots/panda.urdf" in text
    assert "<mesh" not in text
    scene = skill.parse_mujoco(xml_bytes)
    assert any(o.name == "floor" for o in scene.objects)


# ─── Scenario: fallback 场景包含地面和相机（C13） ───


def test_generate_minimal_mjcf_has_ground_and_camera() -> None:
    """指导书要求：fallback 场景必须含地面平面与相机。"""
    skill = SimConfigSkill()
    xml_bytes = skill.generate_minimal_mjcf(urdf_path=None, mesh_path=None)
    text = xml_bytes.decode("utf-8")
    assert '<geom name="floor" type="plane"' in text
    assert "<camera" in text
    scene = skill.parse_mujoco(xml_bytes)
    assert any(o.name == "floor" and o.type == "plane" for o in scene.objects)
    assert len(scene.cameras) >= 1
    # fallback 路径通过 process 产出时标注 fallback 质量
    result = skill.process(b"not xml", fmt="mjcf")
    assert result.data_source_quality == "fallback"


# ─── Scenario: 真实/fallback MJCF 可被 mujoco 引擎加载（可选） ───


def test_real_mjcf_loadable_in_mujoco() -> None:
    """mujoco 包已安装时验证直通 XML 可被 MuJoCo 引擎加载；未安装则跳过。"""
    mujoco = pytest.importorskip("mujoco")
    result = SimConfigSkill().process(_read("sample_mujoco.xml"), fmt="mjcf")
    mujoco.MjModel.from_xml_string(result.data.decode("utf-8"))


def test_fallback_mjcf_loadable_in_mujoco() -> None:
    """mujoco 包已安装时验证 fallback 生成的 MJCF 可加载（无外部资产依赖）。"""
    mujoco = pytest.importorskip("mujoco")
    xml_bytes = SimConfigSkill().generate_minimal_mjcf(urdf_path=None, mesh_path=None)
    mujoco.MjModel.from_xml_string(xml_bytes.decode("utf-8"))


# ─── validate 契约补充：成功路径无问题 ───


def test_validate_success_path_clean() -> None:
    skill = SimConfigSkill()
    result = skill.process(_read("sample_mujoco.xml"), fmt="mjcf")
    report = skill.validate(result)
    assert report.is_valid is True
    assert report.issues == []


# ─── Scenario: fallback 引用 URDF/Mesh 路径（Task 2 场景组装接线锁定） ───


def test_fallback_python_references_tmp_urdf_and_mesh(tmp_path: Path) -> None:
    """fmt=python 降级产物引用 URDF/Mesh 路径，output_path 由 name 派生。

    锁定当前实现行为：generate_minimal_mjcf 不读取 urdf/mesh 文件内容
    （URDF 仅写入 XML 注释、mesh 写入 <mesh file> 引用），传真实存在的临时
    文件路径即可验证引用正确落进 XML；output_path 由 name 派生为
    ``sim_config/{name}.xml``。
    """
    skill = SimConfigSkill()
    urdf_file = tmp_path / "panda.urdf"
    urdf_file.write_bytes(b"<robot name='panda'/>")
    mesh_file = tmp_path / "cup.stl"
    mesh_file.write_bytes(b"solid cup\nendsolid cup\n")

    result = skill.process(
        b"import numpy as np\ncfg = {'name': 'scene'}\n",
        fmt="python",
        name="scene",
        urdf_path=str(urdf_file),
        mesh_path=str(mesh_file),
    )

    assert result.success is True
    assert result.canonical_format == "mjcf"
    assert result.is_fallback is True
    assert result.output_path == "sim_config/scene.xml"
    text = result.data.decode("utf-8")
    assert str(urdf_file) in text  # URDF 参考（XML 注释）
    assert str(mesh_file) in text  # mesh 引用（<mesh file>）
    assert f'<mesh file="{mesh_file}" name="{mesh_file.stem}"/>' in text
    assert f'<geom name="object_geom" type="mesh" mesh="{mesh_file.stem}"' in text
