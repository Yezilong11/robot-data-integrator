"""数据质量校验节点。

调用校验规则引擎对所有解析后数据项进行检查，输出问题列表。
校验不通过时触发回退重试。
"""

from __future__ import annotations

import ast
import contextlib
import io
import os
import tempfile
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rdi.models import DataReqType, Priority, Severity, ValIssue

if TYPE_CHECKING:
    from rdi.graph.state import SystemState

try:
    import trimesh
except Exception:  # pragma: no cover - 依赖未安装时优雅降级
    trimesh = None  # type: ignore[assignment]

try:
    import yourdfpy
except Exception:  # pragma: no cover - 依赖未安装时优雅降级
    yourdfpy = None  # type: ignore[assignment]


def _is_empty(data: Any) -> bool:
    """判断解析数据是否为空：None、空 bytes/str 或空容器。"""
    if data is None:
        return True
    if isinstance(data, (bytes, str)):
        return len(data) == 0
    try:
        return len(data) == 0
    except TypeError:
        # 无 __len__ 的对象（如 trimesh.Trimesh）视为非空
        return False


def _is_dict_like(data: Any) -> bool:
    """判断对象是否支持键值访问（dict 或 npz-like）。"""
    return isinstance(data, dict) or (
        data is not None and hasattr(data, "__getitem__") and hasattr(data, "keys")
    )


def _validate_urdf_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验 URDF 是否能被外部工具加载。"""
    data = item.data
    if isinstance(data, bytes):
        if yourdfpy is None:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="URDF 校验依赖未安装: yourdfpy",
            )
        try:
            with tempfile.NamedTemporaryFile(suffix=".urdf", delete=False) as tmp:
                tmp.write(data)
                tmp_path = tmp.name
            yourdfpy.URDF.load(tmp_path, load_meshes=False)
        except Exception as exc:  # noqa: BLE001 - 记录加载失败而非中断
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"URDF 无法解析: {exc}",
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
    return None


_MESH_FILE_TYPES: tuple[str, ...] = ("stl", "obj", "ply", "dae", "glb", "gltf")


def _load_mesh_bytes(data: bytes, original_format: str) -> Any:
    """尝试用 trimesh 加载 mesh 字节；未知格式时轮询常见类型。"""
    original_fmt = original_format.lower()
    if original_fmt in _MESH_FILE_TYPES:
        return trimesh.load(io.BytesIO(data), file_type=original_fmt)

    last_exc: Exception | None = None
    for file_type in _MESH_FILE_TYPES:
        try:
            return trimesh.load(io.BytesIO(data), file_type=file_type)
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
    raise last_exc or ValueError("无法识别 mesh 格式")


def _validate_mesh_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验 mesh 是否能被 trimesh 加载且包含有效面片。"""
    data = item.data
    if isinstance(data, bytes):
        if trimesh is None:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="Mesh 校验依赖未安装: trimesh",
            )
        try:
            mesh = _load_mesh_bytes(data, item.provenance.original_format or "")
        except Exception as exc:  # noqa: BLE001
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"Mesh 无法加载: {exc}",
            )
        try:
            faces = len(mesh.faces)  # type: ignore[attr-defined]
        except AttributeError:
            # 可能是 Scene，取其中所有 mesh 的面数之和
            try:
                faces = sum(len(m.faces) for m in mesh.geometry.values())  # type: ignore[union-attr]
            except Exception as exc:  # noqa: BLE001
                return ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"Mesh 面片统计失败: {exc}",
                )
        if faces == 0:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="Mesh 不包含任何面片",
            )
    elif trimesh is not None and isinstance(data, trimesh.Trimesh):
        if len(data.faces) == 0:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="Mesh 不包含任何面片",
            )
    return None


def _validate_sim_config_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验仿真配置（XML/MJCF/Python）语法是否可被外部工具加载。"""
    fmt = (item.canonical_format or "").lower()
    data = item.data
    if fmt in ("xml", "mjcf", "urdf") and isinstance(data, (str, bytes)):
        try:
            ET.fromstring(data)
        except Exception as exc:  # noqa: BLE001
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"XML/MJCF 无法解析: {exc}",
            )
    elif (fmt == "python" or fmt.endswith(".py")) and isinstance(data, (str, bytes)):
        try:
            ast.parse(data)
        except SyntaxError as exc:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"Python 仿真配置语法错误: {exc}",
            )
    return None


def _validate_grasp_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验抓取数据是否包含必要字段。"""
    data = item.data
    if _is_dict_like(data):
        keys = set(data.keys()) if hasattr(data, "keys") else set(data)  # type: ignore[arg-type]
        has_pose_pair = "translations" in keys and "rotations" in keys
        has_grasps = "grasps" in keys
        if not has_pose_pair and not has_grasps:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="Grasp 数据缺少必要字段: 需要 translations+rotations 或 grasps",
            )
    return None


def _check_loadability(item: Any, req_id: str) -> list[ValIssue]:
    """根据 req_type 分发到对应可加载性校验函数。"""
    issues: list[ValIssue] = []
    req_type = item.req_type
    try:
        if req_type == DataReqType.ROBOT_URDF:
            issue = _validate_urdf_loadability(item, req_id)
            if issue is not None:
                issues.append(issue)
        elif req_type == DataReqType.MESH:
            issue = _validate_mesh_loadability(item, req_id)
            if issue is not None:
                issues.append(issue)
        elif req_type == DataReqType.SIM_CONFIG:
            issue = _validate_sim_config_loadability(item, req_id)
            if issue is not None:
                issues.append(issue)
        elif req_type == DataReqType.GRASP:
            issue = _validate_grasp_loadability(item, req_id)
            if issue is not None:
                issues.append(issue)
    except Exception as exc:  # noqa: BLE001 - 校验函数自身异常不中断节点
        issues.append(
            ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"可加载性校验异常: {exc}",
            )
        )
    return issues


def node_validate(state: SystemState) -> dict[str, Any]:
    """校验节点：对所有 parsed_data 运行校验规则。

    规则：
    - 解析数据为空 → ERROR
    - 完整度 < 100 → WARNING
    - 置信度 < 1.0 → WARNING
    - 输出路径为空 → WARNING
    - 缺失项优先级为 REQUIRED → ERROR；其余 → WARNING
    - URDF / mesh / sim_config / grasp 增加外部工具可加载性校验

    Returns:
        更新 state 的字段：validation_issues, iteration_count, provenance
    """
    now = datetime.now()
    parsed_data = state.get("parsed_data", {})
    missing_items = state.get("missing_items", [])
    requirements = state.get("data_requirements", [])
    iteration = state.get("iteration_count", 0) + 1

    req_by_id = {req.req_id: req for req in requirements}
    issues: list[ValIssue] = []

    for req_id, item in parsed_data.items():
        if _is_empty(item.data):
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message="解析数据为空",
                    auto_fixable=False,
                )
            )
        if item.completeness_pct < 100.0:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"完整度不足 {item.completeness_pct:.1f}%",
                    context={"completeness_pct": item.completeness_pct},
                )
            )
        if item.confidence_score < 1.0:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"置信度不足 {item.confidence_score:.2f}",
                    context={"confidence_score": item.confidence_score},
                )
            )
        if item.output_path == "":
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message="输出路径为空",
                )
            )

        # 可加载性深度校验
        issues.extend(_check_loadability(item, req_id))

    for m in missing_items:
        req = req_by_id.get(m.req_id)
        if req is not None and req.priority == Priority.REQUIRED:
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=m.req_id,
                    message=f"必需需求缺失: {m.reason}",
                    auto_fixable=False,
                )
            )
        else:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=m.req_id,
                    message="非必需需求缺失",
                )
            )

    error_count = sum(1 for i in issues if i.severity == Severity.ERROR)

    return {
        "validation_issues": issues,
        "iteration_count": iteration,
        "provenance": [
            f"[{now.isoformat()}] validate: 检查 {len(parsed_data)} 项解析数据、"
            f"{len(missing_items)} 项缺失，发现 {len(issues)} 个问题 "
            f"({error_count} error, {len(issues) - error_count} warning)"
        ],
    }
