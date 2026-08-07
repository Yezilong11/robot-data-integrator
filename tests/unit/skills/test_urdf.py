# tests/unit/skills/test_urdf.py
"""URDFSkill 单元测试：URDF 解析、物理一致性校验、xacro 降级。

覆盖 spec「URDFSkill」需求的全部场景：解析纯 URDF 成功、关节限位非法、
惯性张量非正定、总质量不合理、xacro 输入降级、转换后关节限位不变。
所有测试为同步（pytest-asyncio 未全局安装）。
"""

from pathlib import Path

import numpy as np
import pytest
from lxml import etree

from rdi.models.common import Severity, StandardResult, ValidationReport
from rdi.skills.urdf_convert import (
    CanonicalRobot,
    Joint,
    Link,
    URDFSkill,
)

SAMPLE_DIR = Path(__file__).parent / "sample_data" / "urdf"


def _load(name: str) -> bytes:
    """读取 sample_data/urdf 下的样本字节。"""
    return (SAMPLE_DIR / name).read_bytes()


def _make_robot(
    mass: float = 1.0,
    inertia: np.ndarray | None = None,
) -> CanonicalRobot:
    """构造单 link 测试用 CanonicalRobot。"""
    if inertia is None:
        inertia = np.eye(3, dtype=float)
    link = Link(name="base", mass=mass, inertia=inertia, origin_xyz=[0.0, 0.0, 0.0])
    return CanonicalRobot(name="test_bot", links=[link], joints=[])


# ─── 解析纯 URDF ───


class TestURDFParse:
    def test_parse_plain_urdf_success(self) -> None:
        """正常情况：allegro URDF 解析成功，data 为非空 CanonicalRobot。"""
        data = _load("allegro_hand_r.urdf")
        result = URDFSkill().process(data)
        assert result.success is True
        assert result.canonical_format == "CanonicalRobot"
        assert isinstance(result.data, CanonicalRobot)
        assert len(result.data.links) > 0
        assert len(result.data.joints) > 0
        # allegro 物理合法，无问题 → completeness 满分
        assert result.completeness_pct == 100.0
        assert result.confidence_score == 1.0
        assert result.warnings == []

    def test_parse_returns_canonical_robot_with_fields(self) -> None:
        """契约：parse 直接返回 CanonicalRobot，字段正确填充。"""
        robot = URDFSkill().parse(_load("allegro_hand_r.urdf"))
        assert robot.name == "allegro_hand"
        base = next(lk for lk in robot.links if lk.name == "base_link")
        assert base.mass == pytest.approx(4.1685782e-01)
        assert base.inertia.shape == (3, 3)
        # 惯性张量对称
        assert np.allclose(base.inertia, base.inertia.T)
        jmf1 = next(j for j in robot.joints if j.name == "jmf1")
        assert jmf1.type == "revolute"
        assert jmf1.parent == "base_link"
        assert jmf1.child == "mf1"
        assert jmf1.axis == [0.0, 0.0, 1.0]


# ─── 关节限位 ───


class TestJointLimits:
    def test_joint_limits_invalid_raises_error_in_validate(self) -> None:
        """异常情况：关节 lower>=upper → validate 返回 ERROR，is_valid=False。"""
        result = URDFSkill().process(_load("bad_limits.urdf"))
        assert result.success is True  # process 仍返回 success
        assert result.confidence_score < 1.0
        assert any("限位" in w for w in result.warnings)
        report = URDFSkill().validate(result)
        assert isinstance(report, ValidationReport)
        assert report.is_valid is False
        errors = [i for i in report.issues if i.severity == Severity.ERROR]
        assert len(errors) >= 1
        assert any("限位" in i.message for i in errors)
        assert any("bad_joint" in i.req_id for i in errors)

    def test_parse_preserves_joint_limits(self) -> None:
        """数据完整性：转换后关节限位不变，与源 XML 一致。"""
        data = _load("allegro_hand_r.urdf")
        robot = URDFSkill().parse(data)
        root = etree.fromstring(data)
        joint_by_name = {j.name: j for j in robot.joints}
        for j_elem in root.findall("joint"):
            name = j_elem.get("name", "")
            limit_elem = j_elem.find("limit")
            if limit_elem is None:
                continue
            parsed = joint_by_name.get(name)
            assert parsed is not None, f"关节 {name} 未被解析"
            src_lower = float(limit_elem.get("lower", "0"))
            src_upper = float(limit_elem.get("upper", "0"))
            assert parsed.limit_lower == pytest.approx(src_lower)
            assert parsed.limit_upper == pytest.approx(src_upper)

    def test_continuous_and_fixed_joints_skip_limit_check(self) -> None:
        """边界：continuous/fixed 关节无限位，不报限位错误。"""
        fixed_joint = Joint(
            name="jfix",
            type="fixed",
            limit_lower=0.0,
            limit_upper=0.0,
            axis=[1.0, 0.0, 0.0],
            parent="a",
            child="b",
        )
        robot = CanonicalRobot(
            name="bot",
            links=[
                Link(name="a", mass=1.0, inertia=np.eye(3), origin_xyz=[0, 0, 0]),
                Link(name="b", mass=0.5, inertia=np.eye(3), origin_xyz=[0, 0, 0]),
            ],
            joints=[fixed_joint],
        )
        issues = URDFSkill().validate_physics(robot)
        assert not any("限位" in msg for _, _, msg in issues)


# ─── 惯性张量 ───


class TestInertiaValidation:
    def test_inertia_non_positive_definite(self) -> None:
        """异常情况：零惯性张量非正定 → validate_physics 报 ERROR。"""
        robot = _make_robot(inertia=np.zeros((3, 3), dtype=float))
        issues = URDFSkill().validate_physics(robot)
        errors = [i for i in issues if i[0] == "error"]
        assert any("惯性张量非正定" in i[2] for i in errors)

    def test_inertia_negative_eigenvalue_flagged(self) -> None:
        """异常情况：含负特征值的惯性张量非正定。"""
        robot = _make_robot(inertia=np.diag([1.0, 1.0, -0.5]))
        issues = URDFSkill().validate_physics(robot)
        assert any("惯性张量非正定" in msg for _, _, msg in issues)

    def test_inertia_valid_no_issue(self) -> None:
        """正常情况：正定惯性张量不报错。"""
        robot = _make_robot(inertia=np.diag([1.0, 2.0, 3.0]))
        issues = URDFSkill().validate_physics(robot)
        assert not any("惯性张量" in msg for _, _, msg in issues)

    def test_non_pd_inertia_in_validate_report(self) -> None:
        """端到端：非正定惯性 → validate 返回 ERROR ValIssue，is_valid=False。"""
        robot = _make_robot(inertia=np.zeros((3, 3), dtype=float))
        result = StandardResult(
            success=True,
            canonical_format="CanonicalRobot",
            data=robot,
        )
        report = URDFSkill().validate(result)
        assert report.is_valid is False
        assert any(i.severity == Severity.ERROR and "惯性张量" in i.message for i in report.issues)

    def test_non_pd_inertia_process_lowers_confidence(self) -> None:
        """端到端：非正定惯性经 process() → confidence_score<1.0。"""
        data = (
            b'<?xml version="1.0"?><robot name="bad_inertia_bot">'
            b'<link name="base"><inertial><mass value="1.0"/>'
            b'<inertia ixx="0" ixy="0" ixz="0" iyy="0" iyz="0" izz="0"/>'
            b"</inertial></link></robot>"
        )
        result = URDFSkill().process(data)
        assert result.success is True
        assert result.confidence_score < 1.0


# ─── 总质量 ───


class TestTotalMass:
    def test_validate_physics_total_mass_too_large(self) -> None:
        """异常情况：总质量 > 200kg → validate_physics 报 ERROR。"""
        link = Link(
            name="heavy",
            mass=250.0,
            inertia=np.eye(3, dtype=float),
            origin_xyz=[0.0, 0.0, 0.0],
        )
        robot = CanonicalRobot(name="heavy_bot", links=[link], joints=[])
        issues = URDFSkill().validate_physics(robot)
        assert any("总质量" in msg for _, _, msg in issues)

    def test_validate_physics_total_mass_zero(self) -> None:
        """异常情况：总质量 <= 0 → validate_physics 报 ERROR。"""
        robot = _make_robot(mass=0.0, inertia=np.eye(3, dtype=float))
        issues = URDFSkill().validate_physics(robot)
        assert any("总质量" in msg for _, _, msg in issues)


# ─── xacro 降级 ───


class TestXacroFallback:
    def test_xacro_fallback_without_ros_module(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """无 ROS xacro 模块时：字符串级清理，返回 canonical_format='urdf'。"""
        monkeypatch.setattr(
            "rdi.skills.urdf_convert.importlib.import_module",
            lambda _name, _package=None: (_ for _ in ()).throw(ImportError()),
        )
        data = _load("fr3.xacro")
        result = URDFSkill().process(data, fmt="xacro", name="fr3")
        assert result.success is True
        assert result.canonical_format == "urdf"
        assert isinstance(result.data, bytes)
        assert result.output_path == "robots/fr3.urdf"
        assert any("降级" in w for w in result.warnings)
        text = result.data.decode("utf-8")
        assert "<xacro:" not in text
        assert "$(find" not in text

    def test_xacro_fallback_replaces_find_placeholder(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """xacro 标签外的 $(find pkg) 占位符被替换为 /mock/pkg。"""
        monkeypatch.setattr(
            "rdi.skills.urdf_convert.importlib.import_module",
            lambda _name, _package=None: (_ for _ in ()).throw(ImportError()),
        )
        data = (
            b'<?xml version="1.0"?><robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="x">'
            b'<link name="base"><visual><geometry><mesh filename="$(find pkg)/mesh.stl"/></geometry></visual></link>'
            b'<xacro:arg name="foo" default="1"/></robot>'
        )
        result = URDFSkill().process(data, fmt="xacro")
        assert result.success is True
        text = result.data.decode("utf-8")
        assert "/mock/pkg/mesh.stl" in text
        assert "<xacro:" not in text

    def test_xacro_detected_by_content_without_fmt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """边界：未传 fmt 但内容含 xacro 标记 → 同样走降级路径。"""
        monkeypatch.setattr(
            "rdi.skills.urdf_convert.importlib.import_module",
            lambda _name, _package=None: (_ for _ in ()).throw(ImportError()),
        )
        data = _load("fr3.xacro")
        result = URDFSkill().process(data)
        assert result.success is True
        assert result.canonical_format == "urdf"
        assert any("降级" in w for w in result.warnings)

    def test_xacro_fallback_does_not_raise(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """契约：xacro 降级路径不抛异常。"""
        monkeypatch.setattr(
            "rdi.skills.urdf_convert.importlib.import_module",
            lambda _name, _package=None: (_ for _ in ()).throw(ImportError()),
        )
        data = (
            b'<?xml version="1.0"?><robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="x">'
            b'<xacro:include filename="$(find pkg)/missing.xacro"/></robot>'
        )
        result = URDFSkill().process(data)
        assert result.success is True
        assert result.canonical_format == "urdf"

    def test_xacro_module_available_expands_urdf(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """xacro 模块可用时：展开为 URDF 并解析为 CanonicalRobot。"""
        valid_urdf = (
            b'<?xml version="1.0"?><robot name="expanded">'
            b'<link name="base"><inertial><mass value="1.0"/>'
            b'<inertia ixx="1" ixy="0" ixz="0" iyy="1" iyz="0" izz="1"/>'
            b"</inertial></link></robot>"
        )
        monkeypatch.setattr(
            "rdi.skills.urdf_convert.importlib.import_module",
            lambda _name, _package=None: object(),
        )
        monkeypatch.setattr(
            URDFSkill,
            "_expand_xacro",
            staticmethod(lambda _xacro, _data: valid_urdf),
        )
        data = b'<?xml version="1.0"?><robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="x"><xacro:foo/></robot>'
        result = URDFSkill().process(data, fmt="xacro")
        assert result.success is True
        assert result.canonical_format == "CanonicalRobot"
        assert isinstance(result.data, CanonicalRobot)
        assert result.data.name == "expanded"


# ─── validate 报告 ───


class TestValidateReport:
    def test_validate_failure_result(self) -> None:
        """异常情况：失败 StandardResult → ValidationReport(is_valid=False)。"""
        failed = StandardResult(
            success=False,
            canonical_format="CanonicalRobot",
            errors=["parse failed"],
        )
        report = URDFSkill().validate(failed)
        assert report.is_valid is False
        assert "失败" in report.summary
        assert report.issues == []

    def test_validate_valid_robot(self) -> None:
        """正常情况：allegro 解析结果 → validate 通过。"""
        result = URDFSkill().process(_load("allegro_hand_r.urdf"))
        report = URDFSkill().validate(result)
        assert report.is_valid is True
        assert report.issues == []

    def test_process_output_path_from_name_kwarg(self) -> None:
        """契约：传 name kwarg → output_path 设为 robots/{name}.urdf。"""
        result = URDFSkill().process(
            _load("allegro_hand_r.urdf"),
            name="allegro_hand_r",
        )
        assert result.output_path == "robots/allegro_hand_r.urdf"

    def test_process_parse_error_degrades(self) -> None:
        """异常情况：非法 XML → success=False，不抛异常。"""
        result = URDFSkill().process(b"not a valid xml <<")
        assert result.success is False
        assert any("URDF 解析失败" in e for e in result.errors)
        assert result.data is None
