# src/rdi/adapters/selectors.py
"""文件树目标数据文件选择器。

按需求类型（DataReqType）在源文件树的条目列表（tree API 输出）中定位目标
数据文件：只依据 name/type/size/url 等条目元信息，不解析文件内容。供 fetch
前的目标文件预选，以及 download_guide（下载指引）结构生成使用。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from rdi.models.common import DataReqType

# ─── 规则表 ───
# 每个需求类型对应一组选择规则：
# - exts: 扩展名白名单；None 表示不限制扩展名
# - signals: 名字信号，命中数多的候选优先（大小写不敏感子串匹配）
# - skip_keywords: 名称含这些词的条目直接跳过（元数据类文件）

_POLICY_EXTS = frozenset({".safetensors", ".bin", ".pt", ".pth"})
_POLICY_SIGNALS = ("policy", "checkpoint", "actuator", "model")

_SENSOR_EXTS = frozenset({".csv", ".json"})
_SENSOR_SIGNALS = ("sensor", "torque", "force", "joint", "time")

_GRASP_EXTS = frozenset({".npz"})
_GRASP_SIGNALS = ("grasp_label",)

# DATASET 与未列出的需求类型共用兜底规则：无扩展名限制、跳过元数据类文件
_METADATA_KEYWORDS = ("readme", "license", "metadata", "config")


@dataclass(frozen=True)
class _Rule:
    """单条需求类型的选择规则。"""

    exts: frozenset[str] | None = None
    signals: tuple[str, ...] = ()
    skip_keywords: tuple[str, ...] = ()


_RULES: dict[DataReqType, _Rule] = {
    DataReqType.POLICY_MODEL: _Rule(exts=_POLICY_EXTS, signals=_POLICY_SIGNALS),
    DataReqType.SENSOR_DATA: _Rule(exts=_SENSOR_EXTS, signals=_SENSOR_SIGNALS),
    DataReqType.GRASP: _Rule(exts=_GRASP_EXTS, signals=_GRASP_SIGNALS),
}
_FALLBACK_RULE = _Rule(skip_keywords=_METADATA_KEYWORDS)


def _entry_name(entry: dict[str, Any]) -> str:
    """返回条目文件名（小写，缺失时为空串）。"""
    return str(entry.get("name", "")).lower()


def _entry_size(entry: dict[str, Any]) -> int:
    """返回条目字节大小（缺失/非法时按 0 处理，避免排序崩溃）。"""
    try:
        return int(entry.get("size", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _matched_signals(name: str, signals: tuple[str, ...]) -> list[str]:
    """返回 name 中命中的信号列表（大小写不敏感子串匹配）。"""
    return [s for s in signals if s in name]


def select_target_file(
    tree: list[dict[str, Any]], req_type: DataReqType
) -> list[dict[str, Any]]:
    """在源文件树中按需求类型定位目标数据文件。

    Args:
        tree: 文件树条目列表，每项 dict 至少含 name/type（"file"/"dir"），
            可能含 path、size、url。
        req_type: 需求类型（rdi.models.DataReqType 枚举值）。

    Returns:
        候选排序列表：仅含 type=="file" 条目，先按扩展名白名单过滤，再按
        名字信号命中数降序、同分按 size 降序排序；无候选或 tree 为空返回 []。
    """
    if not tree:
        return []
    rule = _RULES.get(req_type, _FALLBACK_RULE)
    files = [e for e in tree if e.get("type") == "file"]
    if rule.exts is not None:
        files = [e for e in files if Path(_entry_name(e)).suffix in rule.exts]
    if rule.skip_keywords:
        files = [
            e for e in files if not any(k in _entry_name(e) for k in rule.skip_keywords)
        ]
    if not files:
        return []
    return sorted(
        files,
        key=lambda e: (
            len(_matched_signals(_entry_name(e), rule.signals)),
            _entry_size(e),
        ),
        reverse=True,
    )


def _selection_reason(candidate: dict[str, Any], rule: _Rule) -> str:
    """生成 selected_by 描述：扩展名 + 命中信号，无信号时说明大小依据。"""
    name = _entry_name(candidate)
    ext = Path(name).suffix
    hits = _matched_signals(name, rule.signals)
    bits = [f"ext={ext}"] if ext else []
    if hits:
        bits.append("signals=" + ",".join(hits))
    else:
        bits.append("size=largest")
        if rule.skip_keywords:
            bits.append("skipped=metadata")
    return "; ".join(bits) or "size=largest"


def build_download_guide(
    candidate: dict[str, Any],
    reason: str,
    req_type: DataReqType | None = None,
) -> dict[str, Any]:
    """为选中的候选文件生成 download_guide 结构 dict。

    Args:
        candidate: select_target_file 返回的单个候选条目（含 url/path/size/name）。
        reason: 未下载的原因说明。
        req_type: 需求类型；提供时 selected_by 可精确写出命中的信号与扩展名，
            缺省时仅按候选自身扩展名/大小描述。

    Returns:
        download_guide dict：status/reason/source_file_url/file_size_bytes/
        method_hint（wget 命令）/selected_by/alternatives。
    """
    rule = _Rule() if req_type is None else _RULES.get(req_type, _FALLBACK_RULE)
    url = str(candidate.get("url") or candidate.get("path") or "")
    local = str(candidate.get("path") or candidate.get("name") or "")
    return {
        "status": "not_downloaded",
        "reason": reason,
        "source_file_url": url,
        "file_size_bytes": _entry_size(candidate),
        "method_hint": f"wget {url} -O {local}" if url else "",
        "selected_by": _selection_reason(candidate, rule),
        "alternatives": [],
    }