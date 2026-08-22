"""数据质量校验节点。

调用校验规则引擎对所有解析后数据项进行检查，输出问题列表。
校验不通过时触发回退重试。
"""

from __future__ import annotations

import ast
import contextlib
import io
import json
import os
import posixpath
import re
import shutil
import tempfile
import time
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rdi.logging import get_logger
from rdi.models import DataReqType, Priority, Severity, ValIssue

logger = get_logger(__name__)

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
    import mujoco
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


# ─── P0-A 内容有效性校验：占位/元数据代理检测 + 目标-内容语义匹配 ───

# 占位数据字节阈值：降级来源且序列化后小于该字节数视为疑似占位（仅元数据/摘要）
_PLACEHOLDER_BYTE_THRESHOLD = 200

# 内容语义匹配仅对"内容是具体物体/机器人/数据内容"的语义关键类型启用。
# dataset / sensor_data / policy_model 依赖 LLM 提炼的 semantic_terms 提供
# 数据内容语义（如 robot manipulation / action labels），无 semantic_terms 时
# 沿用 object_name/keywords 轻量提取，仍无具体词则跳过（fail-open）。
_SEMANTIC_REQ_TYPES: tuple[DataReqType, ...] = (
    DataReqType.GRASP,
    DataReqType.MESH,
    DataReqType.ROBOT_URDF,
    DataReqType.SIM_CONFIG,
    DataReqType.DATASET,
    DataReqType.SENSOR_DATA,
    DataReqType.POLICY_MODEL,
)

# 公共别名：供检索候选语义预筛（retrieve_data._pick_semantic_candidate）复用
SEMANTIC_REQ_TYPES: tuple[DataReqType, ...] = _SEMANTIC_REQ_TYPES

# 需求侧中文物体名 → YCB 英文物体名映射（与 parse_goal._YCB_COMMON_OBJECT_NAMES 呼应）
_YCB_TERM_MAP: dict[str, str] = {
    "苹果": "apple",
    "香蕉": "banana",
    "马克杯": "mug",
    "杯子": "cup",
    "碗": "bowl",
    "饼干盒": "cracker box",
    "糖盒": "sugar box",
    "番茄汤罐": "tomato soup can",
    "主厨罐": "master chef can",
    "芥末罐": "mustard bottle",
    "金枪鱼罐": "tuna fish can",
    "瓶子": "bottle",
    "剪刀": "scissors",
}

# 不计入目标术语的泛词（避免 robot/dataset/grasp 等容器词造成误报）
_SEMANTIC_STOPWORDS: frozenset[str] = frozenset(
    {
        "robot", "robots", "robotic", "robotics", "manipulator", "arm",
        "机械臂", "机器人", "data", "dataset", "datasets", "数据", "模型",
        "model", "models", "mesh", "meshes", "网格", "物体", "object", "objects",
        "grasp", "grasping", "抓取", "标注", "annotation", "annotations",
        "pose", "poses", "config", "configs", "configuration", "配置",
        "simulation", "sim", "仿真", "policy", "策略", "环境", "environment",
        "scene", "scenes", "场景", "file", "files", "文件", "文档", "document",
        "paper", "论文", "code", "repository", "信息", "任务", "benchmark",
    }
)


def _serialized_size(data: Any) -> int:
    """估算数据序列化后的字节数（bytes/str 直接量长度，容器用 JSON 近似）。"""
    if isinstance(data, bytes):
        return len(data)
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    if data is None:
        return 0
    try:
        return len(json.dumps(data, default=str).encode("utf-8"))
    except Exception:  # noqa: BLE001 - 无法序列化视为非占位（有内容）
        return _PLACEHOLDER_BYTE_THRESHOLD + 1


def _is_metadata_proxy(item: Any) -> tuple[bool, str]:
    """检测 ParsedItem 是否仅为元数据/占位（真实数据未获得）。

    任一命中即占位：
    1. ``reference`` 非空（大文件仅提供远端引用，未下载）；
    2. canonical_format 为 DatasetSummary 且 data.file_tree 为空（仅摘要）；
    3. 降级来源（is_fallback 或 data_source_quality==fallback）且序列化后
       < ``_PLACEHOLDER_BYTE_THRESHOLD`` 字节（疑似占位）。

    Returns:
        (is_proxy, reason)：reason 为命中原因（未命中时为空串）。
    """
    if getattr(item, "reference", None) is not None:
        return True, "仅提供远端引用（大文件未下载）"
    cf = (getattr(item, "canonical_format", "") or "").lower()
    data = getattr(item, "data", None)
    if cf in ("datasetsummary", "dataset summary") and isinstance(data, dict):
        if not (data.get("file_tree") or []):
            return True, "数据集仅元数据/摘要，未含实际文件"
    fallback_src = getattr(item, "is_fallback", False) or (
        getattr(item, "data_source_quality", None) or ""
    ) == "fallback"
    if fallback_src and _serialized_size(data) < _PLACEHOLDER_BYTE_THRESHOLD:
        return True, "降级来源且数据过小，疑似占位"
    return False, ""


def _extract_semantic_terms(req: Any) -> set[str]:
    """从需求提取目标实体术语（物体/机器人/数据内容），用于目标-内容匹配。

    来源：LLM 提炼的 ``semantic_terms``（优先，直接采用，仅跳过空串）+
    ``object_name`` + ``keywords`` + description 中的 YCB 中英名单与 YCB id
    （位于 parse_goal 语义，如 011_banana）。泛词与纯符号串被过滤
    （semantic_terms 之外的来源）；semantic_terms 为空时行为与现状完全一致。
    """
    terms: set[str] = set()
    for st in getattr(req, "semantic_terms", []) or []:
        s = str(st).strip().lower()
        if s:
            terms.add(s)
    parts: list[str] = [getattr(req, "description", "") or ""]
    parts.extend(getattr(req, "keywords", None) or [])
    text = " ".join(parts)
    lower = text.lower()
    ob = (getattr(req, "object_name", "") or "").strip().lower()
    if ob and ob not in _SEMANTIC_STOPWORDS:
        terms.add(ob)
    for m in re.finditer(r"\b\d{3}_[a-z0-9_]+\b", lower):
        terms.add(m.group(1))
    for zh, en in _YCB_TERM_MAP.items():
        if zh in text:
            terms.add(en)
        if re.search(rf"\b{re.escape(en)}\b", lower):
            terms.add(en)
    for kw in (getattr(req, "keywords", None) or []):
        k = str(kw).strip().lower()
        if k and k not in _SEMANTIC_STOPWORDS and not re.fullmatch(r"[\W_]+", k):
            terms.add(k)
    return terms


def _item_identity_text(item: Any) -> str:
    """拼装资产标识文本：name + source_url 末两段 + data title/description 前 200 字符。"""
    parts: list[str] = [getattr(item, "name", "") or ""]
    prov = getattr(item, "provenance", None)
    url = getattr(prov, "source_url", "") or ""
    if url:
        tail = url.rstrip("/").split("/")[-2:]
        parts.extend(tail)
    data = getattr(item, "data", None)
    if isinstance(data, dict):
        payload = data.get("title") or data.get("description") or ""
        if isinstance(payload, list):
            payload = " ".join(str(p) for p in payload)
        if isinstance(payload, str):
            parts.append(payload[:200])
    elif isinstance(data, str):
        parts.append(data[:200])
    return " ".join(parts).lower()


def _term_in(text: str, term: str) -> bool:
    """术语匹配：中文按子串包含，英文/ASCII 按整词边界（避免 cup 命中 cupboard）。

    匹配前把 ``-``/``_`` 规范化为空格：资产/仓库命名惯例用下划线/连字符
    代替空格（franka_panda ⇔ 需求词 "franka panda"），不规范化会漏匹配。
    """
    if any(ord(c) > 127 for c in term):
        return term in text
    norm_text = re.sub(r"[-_]", " ", text)
    norm_term = re.sub(r"[-_]", " ", term)
    return re.search(rf"\b{re.escape(norm_term)}\b", norm_text) is not None


def semantic_score(req: Any, name: str = "", url: str = "", desc: str = "") -> int:
    """需求目标术语在候选标识文本中的命中数（公共语义预筛打分）。

    拼装与 ``_item_identity_text`` 一致（name + url 末两段 + desc 前 200 字符，
    lowercase），按 ``_term_in`` 规则统计 ``_extract_semantic_terms`` 提取的
    术语命中个数。检索期候选排序（retrieve_data）与装配期语义校验
    （``_semantic_mismatch``）共用同一打分，保证两处判定同源。
    """
    parts: list[str] = [name or ""]
    if url:
        tail = url.rstrip("/").split("/")[-2:]
        parts.extend(tail)
    if desc:
        parts.append(str(desc)[:200])
    text = " ".join(parts).lower()
    return sum(1 for t in _extract_semantic_terms(req) if _term_in(text, t))


def _semantic_mismatch(req: Any, item: Any) -> str:
    """目标-内容语义匹配：需求目标实体词与资产标识零重叠时返回原因。

    仅对 ``_SEMANTIC_REQ_TYPES`` 启用；目标术语为空（无具体物体/机器人）跳过。
    ponytail: 轻量规则（词表 + 整词重叠），中文泛词可能误判；升级路径为接入
    LLM 深度语义校验替换本规则。
    """
    if getattr(item, "req_type", None) not in _SEMANTIC_REQ_TYPES:
        return ""
    terms = _extract_semantic_terms(req)
    if not terms:
        return ""
    prov = getattr(item, "provenance", None)
    url = getattr(prov, "source_url", "") or ""
    data = getattr(item, "data", None)
    desc = ""
    if isinstance(data, dict):
        payload = data.get("title") or data.get("description") or ""
        if isinstance(payload, list):
            payload = " ".join(str(p) for p in payload)
        if isinstance(payload, str):
            desc = payload
    elif isinstance(data, str):
        desc = data
    if semantic_score(req, getattr(item, "name", "") or "", url, desc) > 0:
        return ""
    return (
        f"内容与需求语义不符（需求目标: {'、'.join(sorted(terms))}，"
        f"实际: {getattr(item, 'name', '')}）"
    )


def _missing_urdf_assets(urdf_bytes: bytes, base_dir: str) -> list[str]:
    """返回 URDF 中相对引用但 ``base_dir`` 下缺失的外部资源（规范化路径）。

    yourdfpy 对缺失 mesh 只打 WARNING 不抛异常，故加载后需显式核对
    自包含性：相对路径引用的 mesh/texture 必须在资产目录中存在，
    否则数据包无法离线完整加载。绝对 URL（package:// 等）与 xacro 变量
    不在此检查范围（下载阶段已跳过）。
    """
    missing: list[str] = []
    try:
        root = ET.fromstring(urdf_bytes)
    except Exception:  # noqa: BLE001 — XML 非法由 yourdfpy 加载报错，不重复报告
        return missing
    for elem in root.iter():
        tag = elem.tag.split("}")[-1].lower()
        if tag not in {"mesh", "texture"}:
            continue
        rel = (elem.get("filename") or elem.get("file") or "").strip()
        if not rel:
            continue
        if rel.startswith(("package://", "model://", "http://", "https://")):
            continue
        if "$(" in rel or rel.startswith("/"):
            continue
        if rel.startswith("./"):
            rel = rel[2:]
        norm = posixpath.normpath(rel)
        while norm.startswith("../"):
            norm = norm[3:]
        if not norm or norm == "..":
            continue
        if not os.path.exists(os.path.join(base_dir, norm)) and norm not in missing:
            missing.append(norm)
    return missing


def _validate_urdf_loadability(item: Any, req_id: str) -> ValIssue | None:
    """校验 URDF 是否能被外部工具加载。

    P0-3 数据包自包含：若 ParsedItem 携带原始字节（raw_bytes）与外部资产
    （assets），把两者写入临时目录后用 ``load_meshes=True`` 深度校验，并核对
    相对引用的 mesh/texture 是否齐备（yourdfpy 对缺失 mesh 仅打 WARNING，
    故需显式检查自包含性）；无 raw_bytes 时维持现状（仅做无网格加载）。
    """
    if yourdfpy is None:
        return ValIssue(
            severity=Severity.ERROR,
            req_id=req_id,
            message="URDF 校验依赖未安装: yourdfpy",
        )
    raw_bytes = getattr(item, "raw_bytes", None)
    if raw_bytes:
        tmp = tempfile.mkdtemp()
        try:
            model_path = os.path.join(tmp, "model.urdf")
            with open(model_path, "wb") as f:
                f.write(raw_bytes)
            # 写入引用的外部资产；剥离前导 ../ 段，防止写入逃逸出临时目录
            for rel_path, content in (getattr(item, "assets", None) or {}).items():
                norm_rel = posixpath.normpath(rel_path)
                while norm_rel.startswith("../"):
                    norm_rel = norm_rel[3:]
                if not norm_rel or norm_rel == "..":
                    continue
                asset_path = os.path.join(tmp, norm_rel)
                os.makedirs(os.path.dirname(asset_path), exist_ok=True)
                with open(asset_path, "wb") as f:
                    f.write(content)
            yourdfpy.URDF.load(model_path, load_meshes=True)
            missing = _missing_urdf_assets(raw_bytes, tmp)
            missing += [m for m in (getattr(item, "assets_missing", None) or []) if m not in missing]
            if missing:
                return ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"URDF 无法解析: 引用的外部资源缺失: {', '.join(missing)}",
                )
        except Exception as exc:  # noqa: BLE001 - 记录加载失败而非中断
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"URDF 无法解析: {exc}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return None
    data = item.data
    if isinstance(data, bytes):
        # 无 raw_bytes（如 Skill 内联展开后的纯字节）：同样写入临时目录执行
        # XML 引用核对（P0-C），并结合下载阶段 assets_missing 判内容错误；
        # 无网格深度加载（与原有行为一致）。
        tmp = tempfile.mkdtemp()
        try:
            model_path = os.path.join(tmp, "model.urdf")
            with open(model_path, "wb") as f:
                f.write(data)
            for rel_path, content in (getattr(item, "assets", None) or {}).items():
                norm_rel = posixpath.normpath(rel_path)
                while norm_rel.startswith("../"):
                    norm_rel = norm_rel[3:]
                if not norm_rel or norm_rel == "..":
                    continue
                asset_path = os.path.join(tmp, norm_rel)
                os.makedirs(os.path.dirname(asset_path), exist_ok=True)
                with open(asset_path, "wb") as f:
                    f.write(content)
            missing = _missing_urdf_assets(data, tmp)
            missing += [
                m for m in (getattr(item, "assets_missing", None) or []) if m not in missing
            ]
            if missing:
                return ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"URDF 无法解析: 引用的外部资源缺失: {', '.join(missing)}",
                )
            yourdfpy.URDF.load(model_path, load_meshes=False)
        except Exception as exc:  # noqa: BLE001 - 记录加载失败而非中断
            return ValIssue(
                severity=Severity.ERROR,
                req_id=req_id,
                message=f"URDF 无法解析: {exc}",
            )
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
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
            # 优先用 canonical_format（归一化后 MESH 项为 "stl" bytes，原始格式可能
            # 是 obj 等与内容不一致的源格式）；未知格式由 _load_mesh_bytes 轮询兜底。
            mesh = _load_mesh_bytes(
                data, item.canonical_format or item.provenance.original_format or ""
            )
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


def _mujoco_load(xml_bytes: bytes, assets: dict[str, bytes]) -> None:
    """用 MuJoCo 加载 MJCF 并运行一步仿真；失败抛异常。

    P0-3：item 带 assets 时把 xml 与外部资源写入临时目录后 ``from_xml_path``
    加载，使 MJCF 引用的相对路径 mesh/texture 可被解析；无 assets 时维持
    ``from_xml_string`` 加载。写入时相对路径防目录逃逸：normpath 并剥离
    前导 ../ 段。
    """
    if not assets:
        model = mujoco.MjModel.from_xml_string(xml_bytes)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            model_path = os.path.join(tmp, "model.xml")
            with open(model_path, "wb") as f:
                f.write(xml_bytes)
            for rel_path, content in assets.items():
                norm_rel = posixpath.normpath(rel_path)
                while norm_rel.startswith("../"):
                    norm_rel = norm_rel[3:]
                if not norm_rel or norm_rel == "..":
                    continue
                asset_path = os.path.join(tmp, norm_rel)
                os.makedirs(os.path.dirname(asset_path), exist_ok=True)
                with open(asset_path, "wb") as f:
                    f.write(content)
            model = mujoco.MjModel.from_xml_path(model_path)
    sim_data = mujoco.MjData(model)
    mujoco.mj_step(model, sim_data)


def _mujoco_runtime_check(item: Any, req_id: str) -> tuple[ValIssue | None, dict[str, Any]]:
    """MuJoCo 运行时验证：加载 MJCF 并运行一步仿真。

    P0-3：item 携带 assets 时把 xml 与外部资源写入临时目录后加载，使 MJCF
    引用的外部 mesh/texture 可解析，加载通过则 status=passed（不再因缺资源
    恒为 skipped）。

    资源缺失降级策略：无 assets、或带 assets 但引用资源仍未下载全时，加载会
    因找不到文件而失败。无 assets 时先尝试写临时文件后用 ``from_xml_path``
    加载（按文件位置解析相对路径）；仍失败或带 assets 仍缺资源，视为「资源
    引用未解析」——XML 语法合法但运行时验证无法完成，降级为 WARNING（非
    ERROR），避免把真实但引用外部资产的 XML 误判为不可运行。其余编译/仿真
    错误（非法几何、actuator 配置等）视为真实失败，记为 ERROR。

    Returns:
        (issue, runtime_check)：issue 为失败时的问题记录（成功为 None）；
        runtime_check 为 ``{status: passed/failed/skipped, detail}``。
    """
    if mujoco is None:
        return None, {"status": "skipped", "detail": "mujoco 未安装，仅做 XML 语法校验"}
    data = item.data
    xml_bytes = data if isinstance(data, bytes) else data.encode("utf-8")
    assets = getattr(item, "assets", None) or {}
    try:
        _mujoco_load(xml_bytes, assets)
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
        if assets:
            # 带 assets 仍缺资源（下载不全）→ 直接降级，无更深的回退
            return (
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"MJCF 资源引用未解析（跳过运行时验证）: {exc}",
                ),
                {"status": "skipped", "detail": f"资源引用未解析: {exc}"},
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


# 降级场景诚实标记前缀（与 sim_config.DEGRADED_SCENE_NOTE 联动，Task 3）。
# SimConfigSkill 对非 MJCF 输入（python/yaml/未知）或解析失败生成最小 MJCF
# 占位场景时，在 warnings 中写入此前缀文本；真实 MJCF 直通与 parse_mujoco
# 重建分支不写标记。
_DEGRADED_SCENE_MARK = "降级场景："


def _sim_config_degraded_scene(item: Any) -> str:
    """返回 SIM_CONFIG 降级场景的诚实提示文本；非降级返回空串。

    在装配后的 ParsedItem.warnings 中检测 ``降级场景：`` 前缀标记，命中则
    返回该说明，供 node_validate 以独立 WARNING 呈现（不改变 passed 判定）。
    """
    if getattr(item, "req_type", None) != DataReqType.SIM_CONFIG:
        return ""
    for w in getattr(item, "warnings", None) or []:
        if w.startswith(_DEGRADED_SCENE_MARK):
            return w
    return ""


def _check_loadability(item: Any, req_id: str) -> tuple[list[ValIssue], dict[str, Any] | None]:
    """根据 req_type 分发到对应可加载性校验函数。

    is_fallback 项（fetch 显式降级，数据为元数据而非真实产物）跳过深度
    loadability 校验：元数据没有可加载的真实文件，深度校验只会误报
    ERROR（如 Grasp 缺必要字段）。与 PaperSkill.validate 对 is_fallback
    空字段不视为错误的语义一致。例外：SIM_CONFIG 仍执行 MuJoCo 运行时
    验证——降级的最小 MJCF 是真实可加载的 XML，integration 契约要求
    runtime_check 写入 manifest（passed/skipped）。

    Returns:
        (issues, runtime_check)：runtime_check 为 SIM_CONFIG 的 MuJoCo 运行时
        验证结果（{status, detail}），其他类型返回 None。
    """
    issues: list[ValIssue] = []
    runtime_check: dict[str, Any] | None = None
    req_type = item.req_type
    if getattr(item, "is_fallback", False):
        if req_type == DataReqType.SIM_CONFIG:
            try:
                issue, runtime_check = _validate_sim_config_loadability(item, req_id)
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
        更新 state 的字段：validation_issues, validate_iteration, provenance
    """
    now = datetime.now()
    start = time.monotonic()
    parsed_data = state.get("parsed_data", {})
    missing_items = state.get("missing_items", [])
    requirements = state.get("data_requirements", [])
    iteration = state.get("validate_iteration", 0) + 1

    req_by_id = {req.req_id: req for req in requirements}
    issues: list[ValIssue] = []
    runtime_checks: dict[str, Any] = {}

    for req_id, item in parsed_data.items():
        item_issues: list[ValIssue] = []
        if _is_empty(item.data):
            item_issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message="解析数据为空",
                    auto_fixable=False,
                )
            )
        if item.completeness_pct < 100.0:
            item_issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"完整度不足 {item.completeness_pct:.1f}%",
                    context={"completeness_pct": item.completeness_pct},
                )
            )
        if item.confidence_score < 1.0:
            item_issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=f"置信度不足 {item.confidence_score:.2f}",
                    context={"confidence_score": item.confidence_score},
                )
            )
        if item.output_path == "":
            item_issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message="输出路径为空",
                )
            )

        # 降级场景诚实标记（Task 3）：SIM_CONFIG 最小 MJCF 占位场景（非真实
        # MJCF 直通）按现有 warning 通道呈现；不影响 passed 判定。
        degraded_note = _sim_config_degraded_scene(item)
        if degraded_note:
            item_issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=req_id,
                    message=degraded_note,
                    context={"issue_type": "degraded_scene"},
                )
            )

        # P0-A 内容有效性：占位/元数据代理检测 + 目标-内容语义匹配
        # 对所有项生效（不受 is_fallback 豁免）：占位项判 ERROR 而非仅 WARNING，
        # 语义错配（命中非目标资产）判 ERROR 触发重试换源或如实失败。
        req = req_by_id.get(req_id)
        is_proxy, proxy_reason = _is_metadata_proxy(item)
        if is_proxy:
            item_issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=req_id,
                    message=f"需求实际未获得真实数据（仅元数据/占位）: {proxy_reason}",
                    context={"issue_type": "content_validity"},
                )
            )
        if req is not None and not is_proxy:
            mismatch = _semantic_mismatch(req, item)
            if mismatch:
                item_issues.append(
                    ValIssue(
                        severity=Severity.ERROR,
                        req_id=req_id,
                        message=mismatch,
                        context={"issue_type": "content_validity"},
                    )
                )

        # 可加载性深度校验
        load_issues, runtime_check = _check_loadability(item, req_id)
        item_issues.extend(load_issues)
        if runtime_check is not None:
            runtime_checks[req_id] = runtime_check
        issues.extend(item_issues)
        logger.info(
            "validate.item",
            req_id=req_id,
            req_type=item.req_type.value,
            status="pass" if not item_issues else "issues",
            issue_count=len(item_issues),
            error_count=sum(1 for i in item_issues if i.severity == Severity.ERROR),
        )

    for m in missing_items:
        req = req_by_id.get(m.req_id)
        if req is not None and req.priority == Priority.REQUIRED:
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id=m.req_id,
                    message=f"必需需求缺失: {m.reason}",
                    auto_fixable=False,
                    context={"issue_type": "retrieval_axis"},
                )
            )
        else:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id=m.req_id,
                    message="非必需需求缺失",
                    context={"issue_type": "retrieval_axis"},
                )
            )
        logger.warning(
            "validate.missing",
            req_id=m.req_id,
            priority=(req.priority.value if req is not None else "unknown"),
        )

    error_count = sum(1 for i in issues if i.severity == Severity.ERROR)

    logger.info(
        "validate.done",
        parsed=len(parsed_data),
        missing=len(missing_items),
        issues=len(issues),
        errors=error_count,
        iteration=iteration,
        elapsed_seconds=round(time.monotonic() - start, 3),
    )

    return {
        "validation_issues": issues,
        "runtime_check": runtime_checks,
        "validate_iteration": iteration,
        "provenance": [
            f"[{now.isoformat()}] validate: 检查 {len(parsed_data)} 项解析数据、"
            f"{len(missing_items)} 项缺失，发现 {len(issues)} 个问题 "
            f"({error_count} error, {len(issues) - error_count} warning)"
        ],
    }
