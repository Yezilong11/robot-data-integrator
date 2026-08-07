# src/rdi/skills/urdf_convert.py
"""URDFSkill — 机器人描述文件 (URDF) 解析与物理一致性校验。

将 URDF 解析为中间表示 ``CanonicalRobot``（含 ``links`` / ``joints``），
并校验关节限位、惯性张量正定性、总质量合理性。xacro 输入在缺少 ROS
xacro 模块时走降级路径，不抛异常（符合 BaseSkill 契约）。

中间表示使用 dataclass 而非 Pydantic，因其承载 numpy 数组。
``Joint.limit_lower/limit_upper/name/type``、``Link.name/mass/inertia/origin_xyz``
、``CanonicalRobot.links/joints`` 为跨模块契约，校验引擎 (E) 据此内省。
"""

import importlib
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from lxml import etree

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# ─── 中间表示（dataclass，承载 numpy 数组） ───


@dataclass
class Joint:
    """URDF 关节中间表示。

    Attributes:
        name: 关节名
        type: 关节类型（revolute/prismatic/continuous/fixed/...）
        limit_lower: 关节下限（rad 或 m）
        limit_upper: 关节上限（rad 或 m）
        axis: 关节轴向量 [x, y, z]
        parent: 父 link 名
        child: 子 link 名
    """

    name: str
    type: str
    limit_lower: float
    limit_upper: float
    axis: list[float]
    parent: str
    child: str


@dataclass
class Link:
    """URDF link 中间表示。

    Attributes:
        name: link 名
        mass: 质量 (kg)
        inertia: 3x3 惯性张量（对称）
        origin_xyz: inertial 原点平移 [x, y, z] (m)
    """

    name: str
    mass: float
    inertia: np.ndarray
    origin_xyz: list[float]


@dataclass
class CanonicalRobot:
    """机器人标准化中间表示，作为 URDF/MJCF/SDF 互转的桥梁。"""

    name: str
    links: list[Link]
    joints: list[Joint]


# ─── 解析辅助 ───


def _parse_float_list(text: str | None, default: list[float]) -> list[float]:
    """解析 ``"0 0 1"`` 形式的浮点列表；为空或失败时返回 default 的副本。"""
    if not text:
        return list(default)
    try:
        return [float(x) for x in text.split()]
    except ValueError:
        return list(default)


def _parse_inertia(elem: Any) -> np.ndarray:
    """从 ``<inertia>`` 元素解析 3x3 对称惯性张量。

    URDF 惯性张量对称，故用 ixy/ixz/iyz 填充下三角。
    """

    def attr(key: str) -> float:
        v = elem.get(key)
        return float(v) if v is not None else 0.0

    ixx, ixy, ixz = attr("ixx"), attr("ixy"), attr("ixz")
    iyy, iyz, izz = attr("iyy"), attr("iyz"), attr("izz")
    return np.array(
        [[ixx, ixy, ixz], [ixy, iyy, iyz], [ixz, iyz, izz]],
        dtype=float,
    )


# ─── URDFSkill ───


class URDFSkill(BaseSkill):
    """URDF 解析 Skill。

    解析 URDF 为 ``CanonicalRobot``，校验物理一致性。xacro 输入在缺少
    ROS xacro 模块时降级返回失败结果，不抛异常。
    """

    skill_name = "urdf"

    def parse(self, urdf_bytes: bytes) -> CanonicalRobot:
        """解析 URDF 字节为 ``CanonicalRobot``。

        缺失 ``<inertial>`` 的 link 按 mass=0、inertia=单位矩阵处理。
        """
        root = etree.fromstring(urdf_bytes)
        name = root.get("name", "unnamed")
        links = [self._parse_link(elem) for elem in root.findall("link")]
        joints = [self._parse_joint(elem) for elem in root.findall("joint")]
        return CanonicalRobot(name=name, links=links, joints=joints)

    def _parse_link(self, elem: Any) -> Link:
        name = elem.get("name", "")
        inertial = elem.find("inertial")
        if inertial is None:
            return Link(
                name=name,
                mass=0.0,
                inertia=np.eye(3, dtype=float),
                origin_xyz=[0.0, 0.0, 0.0],
            )
        mass_elem = inertial.find("mass")
        mass = float(mass_elem.get("value", "0")) if mass_elem is not None else 0.0
        inertia_elem = inertial.find("inertia")
        inertia = (
            _parse_inertia(inertia_elem) if inertia_elem is not None else np.eye(3, dtype=float)
        )
        origin = inertial.find("origin")
        origin_xyz = (
            _parse_float_list(origin.get("xyz"), [0.0, 0.0, 0.0])
            if origin is not None
            else [0.0, 0.0, 0.0]
        )
        return Link(name=name, mass=mass, inertia=inertia, origin_xyz=origin_xyz)

    def _parse_joint(self, elem: Any) -> Joint:
        name = elem.get("name", "")
        jtype = elem.get("type", "")
        limit_elem = elem.find("limit")
        lower = float(limit_elem.get("lower", "0")) if limit_elem is not None else 0.0
        upper = float(limit_elem.get("upper", "0")) if limit_elem is not None else 0.0
        axis_elem = elem.find("axis")
        axis = (
            _parse_float_list(axis_elem.get("xyz"), [1.0, 0.0, 0.0])
            if axis_elem is not None
            else [1.0, 0.0, 0.0]
        )
        parent_elem = elem.find("parent")
        child_elem = elem.find("child")
        parent = parent_elem.get("link", "") if parent_elem is not None else ""
        child = child_elem.get("link", "") if child_elem is not None else ""
        return Joint(
            name=name,
            type=jtype,
            limit_lower=lower,
            limit_upper=upper,
            axis=axis,
            parent=parent,
            child=child,
        )

    def validate_physics(self, robot: CanonicalRobot) -> list[tuple[str, str, str]]:
        """校验物理一致性，返回 ``(severity, name, message)`` 列表。

        检查项（均为 ERROR 级）：
        - 关节限位：``limit_lower < limit_upper``（continuous/fixed 跳过）
        - 惯性张量正定性：所有特征值 > 0
        - 总质量：``0 < sum <= 200`` kg
        """
        issues: list[tuple[str, str, str]] = []
        for joint in robot.joints:
            # continuous/fixed 关节无有效限位，跳过限位检查
            if joint.type in ("continuous", "fixed"):
                continue
            if joint.limit_lower >= joint.limit_upper:
                issues.append(
                    (
                        "error",
                        joint.name,
                        f"关节 {joint.name} 限位非法: "
                        f"lower={joint.limit_lower} >= upper={joint.limit_upper}",
                    )
                )
        for link in robot.links:
            # ponytail: 对称化后用 eigvalsh（实特征值，避免复数比较）；
            # URDF 惯性张量理论对称，对称化容忍手填时的微小不一致
            i_sym = (link.inertia + link.inertia.T) * 0.5
            eigvals = np.linalg.eigvalsh(i_sym)
            if not bool(np.all(eigvals > 0)):
                issues.append(
                    (
                        "error",
                        link.name,
                        f"link {link.name} 惯性张量非正定 (特征值: {eigvals.tolist()})",
                    )
                )
        total_mass = float(sum(link.mass for link in robot.links))
        if total_mass <= 0 or total_mass > 200:
            issues.append(
                (
                    "error",
                    robot.name,
                    f"总质量不合理: {total_mass}kg (应在 (0, 200] 范围内)",
                )
            )
        return issues

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        fmt = str(kwargs.get("fmt", ""))
        if self._is_xacro(data, fmt):
            return self._handle_xacro(data)
        try:
            robot = self.parse(data)
        except (etree.XMLSyntaxError, ValueError, TypeError) as exc:
            return StandardResult(
                success=False,
                canonical_format="CanonicalRobot",
                errors=[f"URDF 解析失败: {exc}"],
            )
        issues = self.validate_physics(robot)
        warnings = [msg for _, _, msg in issues]
        error_count = sum(1 for sev, _, _ in issues if sev == "error")
        completeness = 100.0 if error_count == 0 else max(0.0, 100.0 - 10.0 * error_count)
        confidence = max(0.5, 1.0 - 0.1 * error_count)
        name = kwargs.get("name")
        output_path = f"robots/{name}.urdf" if name else None
        return StandardResult(
            success=True,
            canonical_format="CanonicalRobot",
            output_path=output_path,
            completeness_pct=completeness,
            confidence_score=confidence,
            warnings=warnings,
            data=robot,
        )

    @staticmethod
    def _is_xacro(data: bytes, fmt: str) -> bool:
        """识别 xacro 输入：显式 fmt 标记或内容含 xacro 命名空间/标签。"""
        return fmt == "xacro" or b"xmlns:xacro" in data or b"<xacro:" in data

    def _handle_xacro(self, data: bytes) -> StandardResult:
        """处理 xacro 输入：模块缺失或展开失败时降级，不抛异常。"""
        try:
            xacro = importlib.import_module("xacro")
        except ImportError:
            return StandardResult(
                success=False,
                canonical_format="CanonicalRobot",
                errors=["xacro 展开需要 ROS xacro 模块，请提供已展开的 URDF"],
            )
        # xacro 模块可用：尝试展开（需文件路径，写临时文件）
        try:
            expanded = self._expand_xacro(xacro, data)
        except Exception as exc:  # noqa: BLE001 — 任意展开失败均降级
            return StandardResult(
                success=False,
                canonical_format="CanonicalRobot",
                errors=[f"xacro 展开失败: {exc}"],
            )
        if expanded is None:
            return StandardResult(
                success=False,
                canonical_format="CanonicalRobot",
                errors=["xacro 展开失败，请提供已展开的 URDF"],
            )
        return self.process(expanded)

    @staticmethod
    def _expand_xacro(xacro: Any, data: bytes) -> bytes | None:
        """用 xacro 模块展开宏；返回展开后 URDF 字节，失败返回 None。"""
        with tempfile.NamedTemporaryFile(suffix=".urdf.xacro", delete=False) as f:
            f.write(data)
            tmp_path = f.name
        try:
            doc = xacro.process_file(tmp_path)
            expanded: bytes = doc.toxml().encode("utf-8")
            return expanded
        except Exception:
            return None
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验处理结果，构建 ``ValidationReport``。"""
        if not result.success or result.data is None:
            return ValidationReport(is_valid=False, summary="URDF 解析失败")
        robot = result.data
        if not isinstance(robot, CanonicalRobot):
            return ValidationReport(
                is_valid=False,
                summary="URDF 解析失败: 中间表示类型错误",
            )
        issues = self.validate_physics(robot)
        val_issues = [
            ValIssue(
                severity=Severity.ERROR if sev == "error" else Severity.WARNING,
                req_id=name,
                message=msg,
                suggestion="请检查 URDF 中对应元素的定义" if sev == "error" else "",
                auto_fixable=False,
            )
            for sev, name, msg in issues
        ]
        has_error = any(vi.severity == Severity.ERROR for vi in val_issues)
        summary = f"URDF 校验完成: {len(val_issues)} 个问题" + ("，含 ERROR" if has_error else "")
        return ValidationReport(
            is_valid=not has_error,
            issues=val_issues,
            summary=summary,
        )
