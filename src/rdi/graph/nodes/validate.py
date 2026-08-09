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
    import yourdfpy  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - 依赖未安装时优雅降级
    yourdfpy = None

try:
    import mujoco  # type: ignore[import-untyped]
except Exception:  # pragma: no cover - 依赖未安装时优雅降级
    mujoco = None


def _is_empty(data: Any) -> bool:
    """判断解析数据是否为空：None、空 bytes/str 或空容器。"""
    if data is None:
        return True
    if isinstance(data, str | bytes):
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
            faces = len(mesh.faces)
        except AttributeError:
            # 可能是 Scene，取其中所有 mesh 的面数之和
            try:
                faces = sum(len(m.faces) for m in mesh.geometry.values())
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


# mujoco 加载失败中提示外部资源（mesh/texture 文件）缺失的典型错误子串
_MISSING_ASSET_HINTS = (
    "could not find",
    "cannot find",
    "no such file",
    "not found",
    "failed to load",
    "cannot open",
    "opening file",
    "missing file",
)


def _is_missing_asset_error(message: str) -> bool:
    """判断 mujoco 报错是否为外部资源文件缺失（而非 XML 本身非法）。"""
    lower = message.lower()
    return any(hint in lower for hint in _MISSING_ASSET_HINTS)


def _mujoco_runtime_check(item: Any, req_id: str) -> tuple[ValIssue | None, dict[str, Any]]:
    """MuJoCo 运行时验证：加载 MJCF 并运行一步仿真。

    资源缺失降级策略：MJCF 可能引用外部 mesh 文件（相对路径），
    ``from_xml_string`` 无资源目录时会因找不到文件而失败。此时先尝试写临时
    文件后用 ``from_xml_path`` 加载（按文件位置解析相对路径）；若仍失败，
    视为「资源引用未解析」——XML 语法合法但运行时验证无法完成，降级为
    WARNING（非 ERROR），避免把真实但引用外部资产的 XML 误判为不可运行。
    其余编译/仿真错误（非法几何、actuator 配置等）视为真实失败，记为 ERROR。

    Returns:
        (issue, runtime_check)：issue 为失败时的问题记录（成功为 None）；
        runtime_check 为 ``{status: passed/failed/skipped, detail}``。
    """
    if mujoco is None:
        return None, {"status": "skipped", "detail": "mujoco 未安装，仅做 XML 语法校验"}
    data = item.data
    xml_bytes = data if isinstance(data, bytes) else data.encode("utf-8")
    try:
        model = mujoco.MjModel.from_xml_string(xml_bytes)
        sim_data = mujoco.MjData(model)
        mujoco.mj_step(model, sim_data)
    except Exception as exc:  # noqa: BLE001 - 记录 mujoco 加载/仿真失败原因
        if not _is_missing_asset_error(str(exc)):
            return (
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"MJCF 无法通过 MuJoCo 验证: {exc}",
                ),
                {"status": "failed", "detail": f"MuJoCo 加载/仿真失败: {exc}"},
            )
        tmp_path = ""
        try:
            with tempfile.NamedTemporaryFile(suffix=".xml", delete=False) as tmp:
                tmp.write(xml_bytes)
                tmp_path = tmp.name
            model = mujoco.MjModel.from_xml_path(tmp_path)
            sim_data = mujoco.MjData(model)
            mujoco.mj_step(model, sim_data)
        except Exception as exc2:  # noqa: BLE001
            return (
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"MJCF 资源引用未解析（跳过运行时验证）: {exc2}",
                ),
                {"status": "skipped", "detail": f"资源引用未解析: {exc2}"},
            )
        finally:
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)
    return None, {"status": "passed", "detail": "MuJoCo 加载与一步仿真成功"}


def _validate_sim_config_loadability(
    item: Any, req_id: str
) -> tuple[ValIssue | None, dict[str, Any] | None]:
    """校验仿真配置可加载性，返回 (issue, runtime_check)。

    issue 为 ERROR 表示 XML/Python 语法或 MuJoCo 运行时验证失败；
    runtime_check 记录 MuJoCo 运行时验证结果（status: passed/failed/skipped +
    detail），非 MJCF 格式（python/urdf）不参与验证，返回 None。
    """
    fmt = (item.canonical_format or "").lower()
    data = item.data
    if fmt in ("xml", "mjcf", "urdf") and isinstance(data, str | bytes):
        try:
            ET.fromstring(data)
        except Exception as exc:  # noqa: BLE001
            return (
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"XML/MJCF 无法解析: {exc}",
                ),
                {"status": "failed", "detail": f"XML 语法错误: {exc}"},
            )
        if fmt in ("xml", "mjcf"):
            return _mujoco_runtime_check(item, req_id)
    elif (fmt == "python" or fmt.endswith(".py")) and isinstance(data, str | bytes):
        try:
            ast.parse(data)
        except SyntaxError as exc:
            return (
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"Python 仿真配置语法错误: {exc}",
                ),
                None,
            )
    return None, None


def _validate_grasp_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验抓取数据是否包含必要字段。"""
    data = item.data
    if _is_dict_like(data):
        keys = set(data.keys()) if hasattr(data, "keys") else set(data)
        has_pose_pair = "translations" in keys and "rotations" in keys
        has_grasps = "grasps" in keys
        if not has_pose_pair and not has_grasps:
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message="Grasp 数据缺少必要字段: 需要 translations+rotations 或 grasps",
            )
    return None


def _check_loadability(item: Any, req_id: str) -> tuple[list[ValIssue], dict[str, Any] | None]:
    """根据 req_type 分发到对应可加载性校验函数。

    Returns:
        (issues, runtime_check)：runtime_check 为 SIM_CONFIG 的 MuJoCo 运行时
        验证结果（{status, detail}），其他类型返回 None。
    """
    issues: list[ValIssue] = []
    runtime_check: dict[str, Any] | None = None
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
            issue, runtime_check = _validate_sim_config_loadability(item, req_id)
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
    return issues, runtime_check


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
    runtime_checks: dict[str, Any] = {}

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
        load_issues, runtime_check = _check_loadability(item, req_id)
        issues.extend(load_issues)
        if runtime_check is not None:
            runtime_checks[req_id] = runtime_check

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
        "runtime_check": runtime_checks,
        "iteration_count": iteration,
        "provenance": [
            f"[{now.isoformat()}] validate: 检查 {len(parsed_data)} 项解析数据、"
            f"{len(missing_items)} 项缺失，发现 {len(issues)} 个问题 "
            f"({error_count} error, {len(issues) - error_count} warning)"
        ],
    }
