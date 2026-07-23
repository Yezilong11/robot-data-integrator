# src/rdi/skills/sim_config.py
"""SimConfigSkill — 仿真环境配置 (MJCF / Isaac) 解析与场景描述生成。

将 MuJoCo MJCF XML 解析为中间表示 ``SceneDescription``（含 ``objects`` /
``cameras``）；Isaac 配置（IsaacLab YAML/Python，非 USD）走描述性降级解析。

设计决策（依据 spec 真实数据现状）：``pxr`` (USD SDK) 未安装，spec 中提到的
``to_isaac_usd`` 无法实现；本 Skill 提供 ``to_isaac_yaml`` 作为描述性反向输出，
完整 USD 生成需 pxr，留待后续补齐。中间表示使用 dataclass，``SceneDescription
.objects`` 为跨模块契约，校验引擎 (E) 据此内省。
"""

from dataclasses import dataclass
from typing import Any

import yaml  # type: ignore[import-untyped]
from lxml import etree  # type: ignore[import-untyped]

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# ─── 中间表示（dataclass） ───


@dataclass
class SceneObject:
    """场景物体中间表示。

    Attributes:
        name: 物体名（MJCF <geom name=...>，可能为空）
        type: 几何类型（box/sphere/capsule/plane/mesh/...）
        pos: 位置 [x, y, z] (m)
        size: 尺寸参数（语义随 type 变化，box 为半边长）
    """

    name: str
    type: str
    pos: list[float]
    size: list[float]


@dataclass
class Camera:
    """场景相机中间表示。

    Attributes:
        name: 相机名
        pos: 位置 [x, y, z] (m)
        fov: 垂直视场角 (度)，对应 MJCF ``fovy``
    """

    name: str
    pos: list[float]
    fov: float


@dataclass
class SceneDescription:
    """仿真场景标准化中间表示，作为 MJCF/Isaac 互转的桥梁。

    ``objects`` 为跨模块契约：校验引擎 (E) 据此检查「场景无物体」等规则。
    """

    objects: list[SceneObject]
    cameras: list[Camera]
    source_format: str


# ─── 解析辅助 ───


def parse_vec3(s: str) -> list[float]:
    """解析 ``"0 0 1"`` 形式的空白分隔浮点列表为 3 个 float。

    不足 3 个时以 0.0 补齐；解析失败时返回 ``[0.0, 0.0, 0.0]``，不抛异常。
    """
    try:
        parts = [float(x) for x in s.split()]
    except ValueError:
        return [0.0, 0.0, 0.0]
    vals = parts[:3]
    while len(vals) < 3:
        vals.append(0.0)
    return vals


# ─── SimConfigSkill ───


class SimConfigSkill(BaseSkill):
    """仿真环境配置解析 Skill。

    MJCF 解析为 ``SceneDescription``；Isaac 配置走描述性降级（无 pxr 时仅
    提取可识别场景要素，不生成 USD）。处理失败返回降级结果，不抛异常。
    """

    skill_name = "sim_config"

    def parse_mujoco(self, xml_bytes: bytes) -> SceneDescription:
        """解析 MJCF XML 字节为 ``SceneDescription``。

        遍历所有 ``<geom>`` / ``<camera>`` 节点（任意深度）。单节点畸形时跳过，
        不抛异常；仅当顶层 XML 语法错误时由 ``etree.fromstring`` 抛出
        ``XMLSyntaxError``（由 ``process`` 捕获降级）。
        """
        root = etree.fromstring(xml_bytes)
        objects: list[SceneObject] = []
        for elem in root.findall(".//geom"):
            try:
                objects.append(
                    SceneObject(
                        name=elem.get("name", ""),
                        type=elem.get("type", ""),
                        pos=parse_vec3(elem.get("pos", "0 0 0")),
                        size=parse_vec3(elem.get("size", "1 1 1")),
                    )
                )
            except Exception:  # noqa: BLE001 — 跳过单节点畸形，不中断整体解析
                continue
        cameras: list[Camera] = []
        for elem in root.findall(".//camera"):
            try:
                cameras.append(
                    Camera(
                        name=elem.get("name", ""),
                        pos=parse_vec3(elem.get("pos", "0 0 0")),
                        fov=float(elem.get("fovy", "45")),
                    )
                )
            except Exception:  # noqa: BLE001 — 跳过单节点畸形
                continue
        return SceneDescription(objects=objects, cameras=cameras, source_format="mjcf")

    def to_mjcf(self, scene: SceneDescription) -> bytes:
        """由 ``SceneDescription`` 反向生成合法 MJCF XML 字节。"""
        root = etree.Element("mujoco", attrib={"model": "generated"})
        worldbody = etree.SubElement(root, "worldbody")
        for obj in scene.objects:
            etree.SubElement(
                worldbody,
                "geom",
                attrib={
                    "name": obj.name,
                    "type": obj.type,
                    "pos": " ".join(str(v) for v in obj.pos),
                    "size": " ".join(str(v) for v in obj.size),
                },
            )
        for cam in scene.cameras:
            etree.SubElement(
                worldbody,
                "camera",
                attrib={
                    "name": cam.name,
                    "pos": " ".join(str(v) for v in cam.pos),
                    "fovy": str(cam.fov),
                },
            )
        result: bytes = etree.tostring(root, pretty_print=True)
        return result

    def parse_isaac(self, data: bytes) -> SceneDescription:
        """描述性解析 Isaac 配置（YAML）为 ``SceneDescription``。

        识别 ``objects`` / ``cameras`` 列表，提取可识别要素。任何失败均抛
        ``ValueError``，由 ``process`` 捕获降级。

        NOTE: ``pxr`` (USD SDK) 未安装，IsaacLab Python API 配置无法解析为 USD；
        此处仅做 YAML 描述性提取。
        """
        try:
            loaded: Any = yaml.safe_load(data)
        except yaml.YAMLError as exc:
            raise ValueError(f"Isaac YAML 解析失败: {exc}") from exc
        if not isinstance(loaded, dict) or "objects" not in loaded:
            raise ValueError("Isaac 配置缺少 objects 键，无法描述性解析")
        objects: list[SceneObject] = []
        for item in loaded.get("objects", []):
            if not isinstance(item, dict):
                continue
            try:
                objects.append(
                    SceneObject(
                        name=str(item.get("name", "")),
                        type=str(item.get("type", "")),
                        pos=[float(v) for v in item.get("pos", [0.0, 0.0, 0.0])],
                        size=[float(v) for v in item.get("size", [1.0, 1.0, 1.0])],
                    )
                )
            except (TypeError, ValueError):
                continue
        cameras: list[Camera] = []
        for item in loaded.get("cameras", []):
            if not isinstance(item, dict):
                continue
            try:
                cameras.append(
                    Camera(
                        name=str(item.get("name", "")),
                        pos=[float(v) for v in item.get("pos", [0.0, 0.0, 0.0])],
                        fov=float(item.get("fov", 45.0)),
                    )
                )
            except (TypeError, ValueError):
                continue
        return SceneDescription(objects=objects, cameras=cameras, source_format="isaac")

    def to_isaac_yaml(self, scene: SceneDescription) -> bytes:
        """由 ``SceneDescription`` 生成描述性 YAML 字节。

        spec 提到的 ``to_isaac_usd`` 因 ``pxr`` 未安装无法实现；此方法作为
        描述性反向输出替代，完整 USD 生成需补齐 pxr 依赖。
        """
        doc = {
            "objects": [
                {"name": o.name, "type": o.type, "pos": o.pos, "size": o.size}
                for o in scene.objects
            ],
            "cameras": [{"name": c.name, "pos": c.pos, "fov": c.fov} for c in scene.cameras],
        }
        return str(yaml.safe_dump(doc, sort_keys=False)).encode("utf-8")

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """按 ``fmt`` 分发解析，返回标准化结果；失败降级不抛异常。"""
        fmt = str(kwargs.get("fmt", "mjcf")).lower()
        name = kwargs.get("name")
        is_isaac = fmt in ("isaac", "yaml", "usd", "py")
        ext = "yaml" if is_isaac else "xml"
        output_path = f"sim_config/{name}.{ext}" if name else None

        if fmt in ("mjcf", "xml", "mujoco"):
            try:
                scene = self.parse_mujoco(data)
            except (etree.XMLSyntaxError, ValueError, TypeError) as exc:
                return StandardResult(
                    success=False,
                    canonical_format="SceneDescription",
                    errors=[f"MJCF 解析失败: {exc}"],
                )
            warnings = ["场景无物体"] if not scene.objects else []
            return StandardResult(
                success=True,
                canonical_format="SceneDescription",
                output_path=output_path,
                completeness_pct=100.0,
                warnings=warnings,
                data=scene,
            )

        if is_isaac:
            try:
                scene = self.parse_isaac(data)
            except ValueError as exc:
                return StandardResult(
                    success=False,
                    canonical_format="SceneDescription",
                    errors=[f"Isaac 配置解析失败: {exc}"],
                )
            warnings = ["Isaac 配置仅做描述性解析，未生成 USD"]
            if not scene.objects:
                warnings.append("场景无物体")
            return StandardResult(
                success=True,
                canonical_format="SceneDescription",
                output_path=output_path,
                completeness_pct=80.0,
                confidence_score=0.8,
                warnings=warnings,
                data=scene,
            )

        return StandardResult(
            success=False,
            canonical_format="SceneDescription",
            errors=[f"不支持的仿真配置格式: {fmt}"],
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验处理结果，构建 ``ValidationReport``。"""
        if not result.success or result.data is None:
            return ValidationReport(is_valid=False, summary="仿真配置解析失败")
        scene = result.data
        if not isinstance(scene, SceneDescription):
            return ValidationReport(
                is_valid=False,
                summary="仿真配置解析失败: 中间表示类型错误",
            )
        issues: list[ValIssue] = []
        if not scene.objects:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="sim_config",
                    message="场景无物体",
                    suggestion="请在 worldbody 中添加至少一个 <geom>",
                    auto_fixable=False,
                )
            )
        has_error = any(i.severity == Severity.ERROR for i in issues)
        summary = (
            f"仿真配置校验完成: 物体 {len(scene.objects)} 个，"
            f"相机 {len(scene.cameras)} 个，问题 {len(issues)} 个"
        )
        return ValidationReport(
            is_valid=not has_error,
            issues=issues,
            summary=summary,
        )
