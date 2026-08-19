# src/rdi/graph/nodes/assemble.py
"""数据包整合打包节点。

将所有处理后的数据组装为标准化的可复现实验数据包：
把 ``parsed_data`` 中每个 ``ParsedItem.data`` 按 req_type 序列化落盘到对应子目录
（如 ``robots/``、``objects/``），写出 ``manifest.json`` 与 ``provenance.log``，
包含结构化 Manifest、目录结构、溯源日志和缺失项标注。
"""

import dataclasses
import hashlib
import io
import json
import posixpath
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from rdi.config.settings import PIPELINE_VERSION, settings
from rdi.graph.state import SystemState
from rdi.intelligence import decisions as _decisions
from rdi.intelligence.schemas import QualityExplanation
from rdi.logging import get_logger
from rdi.models import (
    DataReqType,
    ManifestFile,
    ManifestMissingItem,
    PackageManifest,
    Priority,
    QualityReport,
)

logger = get_logger(__name__)

# req_type → 数据包子目录；未知/未收录类型统一兜底 resources/
# （与 CODE/DATASET/PAPER 归为同一通用资源目录，避免再引入碎片化 misc/ 目录）
_SUBDIR_BY_REQ_TYPE: dict[DataReqType, str] = {
    DataReqType.ROBOT_URDF: "robots",
    DataReqType.MESH: "objects",
    DataReqType.GRASP: "grasps",
    DataReqType.SIM_CONFIG: "sim_config",
    DataReqType.POLICY_MODEL: "policies",
    DataReqType.CODE: "resources",
    DataReqType.DATASET: "resources",
    DataReqType.PAPER: "resources",
}


def _subdir_for_req_type(req_type: DataReqType) -> str:
    """req_type → 数据包子目录名；未收录类型兜底 resources/。"""
    return _SUBDIR_BY_REQ_TYPE.get(req_type, "resources")


# canonical_format → 文件扩展名映射；未知格式默认 .bin
_EXT_BY_FORMAT: dict[str, str] = {
    "urdf": ".urdf",
    "xml": ".xml",
    "mjcf": ".xml",
    "stl": ".stl",
    "obj": ".obj",
    "npz": ".npz",
    "json": ".json",
    "text": ".txt",
    "markdown": ".md",
    "md": ".md",
}


def _ext_for_format(canonical_format: str) -> str:
    """把 canonical_format 映射为文件扩展名；未知格式返回 .bin。"""
    return _EXT_BY_FORMAT.get(canonical_format.lower(), ".bin")


def _ext_for_raw_format(original_format: str, canonical_format: str) -> str:
    """按原始格式决定原始 XML 落盘扩展名；未知格式回退 canonical_format 映射。

    D4 修复：IsaacLab 资产为 Python 配置（原始格式 python/py），此前回退到
    canonical_format（mjcf→.xml）把 python 脚本落盘为 .xml，MuJoCo 解析报
    XML_ERROR_PARSING_TEXT（ms_003 req_003 格式错配根因）。python 原始字节
    必须以 .py 落盘（SimConfigSkill 对 python 的降级产物在 item.data，原始
    文件本身是 python 源码）。
    """
    fmt = (original_format or "").lower()
    if fmt in ("urdf", "xacro"):
        return ".urdf"
    if fmt in ("xml", "mjcf"):
        return ".xml"
    if fmt in ("python", "py"):
        return ".py"
    return _ext_for_format(canonical_format)


# 资产文件扩展名 → 语义格式；未知扩展名兜底 "asset"
_ASSET_FORMAT_BY_EXT: dict[str, str] = {
    ".stl": "mesh",
    ".dae": "mesh",
    ".obj": "mesh",
    ".png": "texture",
    ".jpg": "texture",
    ".jpeg": "texture",
    ".xml": "xml",
    ".urdf": "urdf",
}


def _asset_format(rel_asset: str) -> str:
    """按资产文件扩展名推断语义格式（mesh/texture/xml/urdf）；未知扩展名用 "asset"。"""
    ext = posixpath.splitext(rel_asset)[1].lower()
    return _ASSET_FORMAT_BY_EXT.get(ext, "asset")


def _safe_filename(req_id: str) -> str:
    """清洗 req_id 中的非法字符（非字母数字下划线替换为 _），防止路径注入。"""
    return re.sub(r"[^A-Za-z0-9_]", "_", req_id)


def _is_trimesh(data: Any) -> bool:
    """判断 data 是否为 trimesh 网格对象（有 export 方法且模块名含 trimesh）。"""
    return hasattr(data, "export") and "trimesh" in data.__class__.__module__


def _json_default(obj: Any) -> Any:
    """json.dumps 的 default 处理器：兼容 numpy 与 datetime。"""
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, np.generic):
        return obj.item()
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"无法序列化类型: {type(obj).__name__}")


def _serialize_item_data(data: Any) -> tuple[bytes | str, str]:
    """把 ParsedItem.data 序列化为可写盘内容，返回 (内容, 建议扩展名)。

    建议扩展名为空表示沿用 canonical_format 映射的扩展名（bytes/str 保留原格式）；
    trimesh 导出二进制 STL；结构化对象导出 JSON；其余对象兜底 repr 文本。
    """
    if isinstance(data, bytes):
        return data, ""
    if isinstance(data, str):
        return data, ""
    if isinstance(data, np.ndarray):
        buf = io.BytesIO()
        np.savez(buf, data=data)
        return buf.getvalue(), ".npz"
    if _is_trimesh(data):
        return data.export(file_type="stl"), ".stl"
    if dataclasses.is_dataclass(data) and not isinstance(data, type):
        payload = json.dumps(dataclasses.asdict(data), ensure_ascii=False, default=_json_default)
        return payload, ".json"
    if hasattr(data, "model_dump"):
        return data.model_dump_json(), ".json"
    if isinstance(data, dict | list):
        return json.dumps(data, ensure_ascii=False, indent=2, default=_json_default), ".json"
    return repr(data), ".txt"


def _derive_package_status(
    num_files: int, missing_items: list[Any], requirements: list[Any]
) -> str:
    """推导数据包状态：failed / partial / complete。

    - 无任何落盘文件 → failed
    - 存在 REQUIRED 优先级需求缺失 → failed
    - 存在非必需需求缺失 → partial
    - 其余 → complete
    """
    if num_files == 0:
        return "failed"
    req_by_id = {r.req_id: r for r in requirements}
    has_missing = False
    for m in missing_items:
        req = req_by_id.get(m.req_id)
        if req is not None and req.priority == Priority.REQUIRED:
            return "failed"
        has_missing = True
    return "partial" if has_missing else "complete"


def _render_llm_quality_md(qe: QualityExplanation) -> str:
    """把 LLM 生成的质量解释渲染为 markdown 落盘内容（文件头标注来源）。"""
    return "\n".join(
        [
            "# 质量报告解释",
            "",
            "> 由 LLM 基于 manifest.json 生成",
            "",
            "## 整体概述",
            qe.summary,
            "",
            "## 数据优势",
            *([f"- {s}" for s in qe.strengths] or ["- （无）"]),
            "",
            "## 潜在风险",
            *([f"- {r}" for r in qe.risks] or ["- （无）"]),
            "",
            "## 改进建议",
            *([f"- {r}" for r in qe.recommendations] or ["- （无）"]),
            "",
            "## 使用指引",
            qe.usage_guidance,
            "",
            "## 置信度",
            f"{qe.confidence:.2f}",
            "",
        ]
    )


def _render_rule_quality_md(report: QualityReport, issues: list[str]) -> str:
    """LLM 不可用时用规则模板渲染质量解释段落（基于质量报告六项数字 + 状态判断）。"""
    if report.fulfilled == 0:
        verdict = "数据包为空（无任何落盘文件），无法支撑实验，需重新检索"
    elif report.missing > 0:
        verdict = "存在缺失项，数据包部分满足需求，使用前需人工确认缺失项影响"
    elif report.validation_issues > 0:
        verdict = "存在校验问题，数据可用性需人工复核后再使用"
    else:
        verdict = "需求全部满足且无校验问题，数据包整体可用"
    return "\n".join(
        [
            "# 质量报告解释",
            "",
            "> 规则模板生成（LLM 不可用）",
            "",
            "## 整体概述",
            f"需求总数 {report.total_requirements} 项，已满足 {report.fulfilled} 项，"
            f"缺失 {report.missing} 项，校验问题 {report.validation_issues} 项；"
            f"平均置信度 {report.avg_confidence:.2f}，平均完整度 {report.avg_completeness:.1f}%",
            "",
            "## 校验问题",
            *([f"- {v}" for v in issues] or ["- 无"]),
            "",
            "## 状态判断",
            verdict,
            "",
        ]
    )


def node_assemble(state: SystemState) -> dict[str, Any]:
    """整合打包节点：序列化解析数据落盘并生成 Manifest。

    Returns:
        更新 state 的字段：experiment_package, missing_items, provenance
    """
    now = datetime.now()
    start = time.monotonic()
    parsed_data = state.get("parsed_data", {})
    missing_items = state.get("missing_items", [])
    requirements = state.get("data_requirements", [])
    validation_issues = state.get("validation_issues", [])

    package_id = f"package-{now.strftime('%Y%m%d-%H%M%S')}"
    package_dir = Path(settings.output_dir) / package_id
    package_dir.mkdir(parents=True, exist_ok=True)

    manifest_files: list[ManifestFile] = []
    provenance: list[str] = []

    for req_id, item in parsed_data.items():
        try:
            subdir = _subdir_for_req_type(item.req_type)
            # 资产文件条目暂存，主文件条目之后统一追加（保持 files[0] 为主文件）
            asset_entries: list[ManifestFile] = []
            if item.raw_bytes is not None:
                # P0-3 数据包自包含：原始 XML 与其引用的外部资产直接落盘
                ext = _ext_for_raw_format(item.provenance.original_format, item.canonical_format)
                filename = f"{_safe_filename(req_id)}{ext}"
                rel_path = f"{subdir}/{filename}"
                target = package_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(item.raw_bytes)
                written_size = len(item.raw_bytes)
                for rel_asset, content in (item.assets or {}).items():
                    # 剥离前导 ../ 段，防止资产路径逃逸出数据包
                    norm_asset = posixpath.normpath(rel_asset)
                    while norm_asset.startswith("../"):
                        norm_asset = norm_asset[3:]
                    if not norm_asset or norm_asset == "..":
                        continue
                    asset_rel_path = f"{subdir}/{norm_asset}"
                    asset_target = package_dir / asset_rel_path
                    asset_target.parent.mkdir(parents=True, exist_ok=True)
                    asset_target.write_bytes(content)
                    # P0-5：资产文件同样纳入 manifest 与 checksums.txt（校验和与磁盘一致）
                    asset_entries.append(
                        ManifestFile(
                            req_id=req_id,
                            path=asset_rel_path,
                            format=_asset_format(norm_asset),
                            source_url=item.provenance.source_url,
                            retrieved_at=item.provenance.retrieved_at,
                            transformations=[f"written_to:{asset_rel_path}"],
                            confidence=item.confidence_score,
                            completeness=item.completeness_pct,
                            data_source_quality=item.data_source_quality or "unknown",
                            is_fallback=item.is_fallback,
                            downloaded=True,
                            file_url=item.provenance.source_url,
                            file_size=len(content),
                            local_path=asset_rel_path,
                            checksum_sha256=hashlib.sha256(content).hexdigest(),
                        )
                    )
            else:
                serialized, suggested_ext = _serialize_item_data(item.data)
                ext = suggested_ext or _ext_for_format(item.canonical_format)
                filename = f"{_safe_filename(req_id)}{ext}"
                rel_path = f"{subdir}/{filename}"
                target = package_dir / rel_path
                target.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(serialized, bytes):
                    target.write_bytes(serialized)
                    written_size = len(serialized)
                else:
                    target.write_text(serialized, encoding="utf-8")
                    written_size = len(serialized.encode("utf-8"))
            # P0-5：文件写入成功后统一计算 SHA-256（raw 分支与序列化分支均覆盖；
            # reference 项写入的是 metadata JSON 代理文件，同样可算校验和）
            sha256 = hashlib.sha256(target.read_bytes()).hexdigest()
        except Exception as exc:  # noqa: BLE001 — 单项失败不中断整体打包
            logger.warning("assemble.item_failed", req_id=req_id, reason=str(exc))
            provenance.append(
                f"[{now.isoformat()}] assemble_package: 序列化 {req_id} 失败，已从数据包排除: {exc}"
            )
            continue

        # P0-4：带 reference 的项表示大文件未下载（如 tar/PDF/zip），
        # manifest 标记 downloaded=false 并提供远端 URL 供用户手动获取
        reference = getattr(item, "reference", None)
        if reference is not None:
            downloaded, file_url, file_size, local_path = (
                False,
                reference.url or reference.download_hint,
                reference.file_size,
                "",
            )
        else:
            downloaded, file_url, file_size, local_path = (
                True,
                item.provenance.source_url,
                written_size,
                rel_path,
            )
        manifest_files.append(
            ManifestFile(
                req_id=req_id,
                path=rel_path,
                format=item.canonical_format,
                source_url=item.provenance.source_url,
                retrieved_at=item.provenance.retrieved_at,
                transformations=[*item.provenance.transformations, f"written_to:{rel_path}"],
                confidence=item.confidence_score,
                completeness=item.completeness_pct,
                data_source_quality=item.data_source_quality or "unknown",
                is_fallback=item.is_fallback,
                downloaded=downloaded,
                file_url=file_url,
                file_size=file_size,
                local_path=local_path,
                checksum_sha256=sha256,
            )
        )
        # 主文件条目之后追加资产条目，保持 manifest 中主文件在前
        manifest_files.extend(asset_entries)

    manifest_missing = [
        ManifestMissingItem(
            req_id=m.req_id,
            reason=m.reason,
            alternatives=m.alternatives,
        )
        for m in missing_items
    ]

    total_conf = sum(f.confidence for f in manifest_files)
    total_comp = sum(f.completeness for f in manifest_files)
    avg_confidence = total_conf / len(manifest_files) if manifest_files else 0.0
    avg_completeness = total_comp / len(manifest_files) if manifest_files else 0.0

    # ⑤ 质量报告解释：LLM 决策层生成自然语言解释，失败走规则模板兜底（空包同样生成）
    quality_report = QualityReport(
        total_requirements=len(requirements),
        fulfilled=len(manifest_files),
        missing=len(manifest_missing),
        validation_issues=len(validation_issues),
        avg_confidence=avg_confidence,
        avg_completeness=avg_completeness,
    )
    issue_strs = [v if isinstance(v, str) else str(v) for v in validation_issues]
    _start = time.monotonic()
    qe = _decisions.explain_quality(
        total_requirements=quality_report.total_requirements,
        fulfilled=quality_report.fulfilled,
        missing=quality_report.missing,
        validation_issues=issue_strs,
        avg_confidence=quality_report.avg_confidence,
        avg_completeness=quality_report.avg_completeness,
        manifest_summary=f"{len(manifest_files)} 个文件，缺失 {len(manifest_missing)} 项",
    )
    explain_usage_entry = {
        "decision": "explain_quality",
        "req_id": "package",
        "status": "ok" if qe is not None else "fallback",
        "model": settings.llm_model,
        "elapsed": round(time.monotonic() - _start, 3),
    }
    if qe is not None:
        quality_md = _render_llm_quality_md(qe)
        explain_note, transform_tag, entry_confidence = (
            "质量解释已生成（LLM 生成）",
            "generated:llm_explanation",
            qe.confidence,
        )
    else:
        quality_md = _render_rule_quality_md(quality_report, issue_strs)
        explain_note, transform_tag, entry_confidence = (
            "质量解释已生成（规则模板生成）",
            "generated:rule_explanation",
            0.5,
        )
    quality_entry = ManifestFile(
        req_id="package",
        path="quality_explanation.md",
        format="md",
        source_url="",
        retrieved_at=now,
        transformations=[transform_tag],
        confidence=entry_confidence,
        completeness=100.0,
        downloaded=True,
        local_path="quality_explanation.md",
        file_size=len(quality_md.encode("utf-8")),
        checksum_sha256=hashlib.sha256(quality_md.encode("utf-8")).hexdigest(),
    )
    (package_dir / "quality_explanation.md").write_text(quality_md, encoding="utf-8")

    # P0-5：校验和清单（含质量解释文件），每行 "<sha256>  <path>"，按路径排序保证确定性；缺失校验和的项跳过
    checksum_lines = [
        f"{f.checksum_sha256}  {f.path}"
        for f in sorted([*manifest_files, quality_entry], key=lambda f: f.path)
        if f.checksum_sha256
    ]
    (package_dir / "checksums.txt").write_text(
        "\n".join(checksum_lines),
        encoding="utf-8",
    )

    package = PackageManifest(
        package_info={
            "goal": state.get("user_goal", ""),
            "created_at": now.isoformat(),
            "iteration": state.get("iteration_count", 0),
            "package_id": package_id,
            "run_id": str(state.get("run_id", "")),  # str() 包裹兼容 None；单跑/测试为空串
            "pipeline_version": PIPELINE_VERSION,
            # E3：真实流程产物显式标记非 demo（与演示流程 demo=true 区分）
            "demo": "false",
            # 契约字段，源 metadata 提供时填充（当前数据链路未透传 license/citation）
            "license": "",
            "citation": "",
            "status": _derive_package_status(len(manifest_files), missing_items, requirements),
        },
        files=[*manifest_files, quality_entry],
        missing_items=manifest_missing,
        quality_report=quality_report,
        provenance_log=[
            f"[{now.isoformat()}] assemble_package: 生成数据包 {package_id}，"
            f"落盘 {len(manifest_files)} 个文件，缺失 {len(manifest_missing)} 项",
            f"[{now.isoformat()}] assemble_package: {explain_note}",
        ],
        runtime_check=state.get("runtime_check", {}),
        revision_history=state.get("revision_history", []),
        output_dir=str(package_dir.resolve()),
    )

    (package_dir / "manifest.json").write_text(
        json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # D1: 物理量纲显式化 —— 每个成功落盘 req 的单位/坐标系/时间戳 + LLM 语义约定
    # 落盘 semantic_map.json（保留原 units.json 字段，追加语义字段；转换参数不再
    # 只存在于代码常量，LLM 动态识别的约定随包可溯源）
    state_semantic = state.get("semantic_map", {}) or {}
    semantic_map_meta = {}
    for req_id, item in parsed_data.items():
        entry: dict[str, Any] = {
            "units": item.units,
            "coordinate_frame": item.coordinate_frame,
            "timestamp_epoch": item.timestamp_epoch,
        }
        conv = state_semantic.get(req_id)
        if conv is not None:
            entry["semantic_type"] = getattr(conv, "semantic_type", None)
            entry["rotation"] = getattr(conv, "rotation", None)
            entry["origin"] = getattr(conv, "origin", None)
            entry["field_map"] = getattr(conv, "field_map", {})
            entry["confidence"] = getattr(conv, "confidence", None)
            entry["needs_human_review"] = getattr(conv, "needs_human_review", False)
            entry["is_llm"] = True
        else:
            entry["is_llm"] = False
        semantic_map_meta[req_id] = entry
    (package_dir / "semantic_map.json").write_text(
        json.dumps(semantic_map_meta, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (package_dir / "provenance.log").write_text(
        "\n".join(package.provenance_log),
        encoding="utf-8",
    )

    provenance[:0] = [
        f"[{now.isoformat()}] assemble_package: {explain_note}",
        f"[{now.isoformat()}] assemble_package: 生成数据包 {package_id}，"
        f"落盘 {len(manifest_files)} 个文件",
    ]

    logger.info(
        "assemble.done",
        package_id=package_id,
        files=len(manifest_files),
        missing=len(manifest_missing),
        status=package.package_info["status"],
        elapsed_seconds=round(time.monotonic() - start, 3),
    )

    return {
        "experiment_package": package,
        "missing_items": missing_items,
        "provenance": provenance,
        "quality_explanation": qe,
        # llm_usage 为累积字段（Annotated operator.add），节点只返回本次条目
        "llm_usage": [explain_usage_entry],
    }
