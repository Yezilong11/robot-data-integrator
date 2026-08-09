# src/rdi/graph/nodes/assemble.py
"""数据包整合打包节点。

将所有处理后的数据组装为标准化的可复现实验数据包：
把 ``parsed_data`` 中每个 ``ParsedItem.data`` 按 req_type 序列化落盘到对应子目录
（如 ``robots/``、``objects/``），写出 ``manifest.json`` 与 ``provenance.log``，
包含结构化 Manifest、目录结构、溯源日志和缺失项标注。
"""

import dataclasses
import io
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np

from rdi.config.settings import settings
from rdi.graph.state import SystemState
from rdi.models import (
    DataReqType,
    ManifestFile,
    ManifestMissingItem,
    PackageManifest,
    QualityReport,
)

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


def node_assemble(state: SystemState) -> dict[str, Any]:
    """整合打包节点：序列化解析数据落盘并生成 Manifest。

    Returns:
        更新 state 的字段：experiment_package, missing_items, provenance
    """
    now = datetime.now()
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
            content, suggested_ext = _serialize_item_data(item.data)
            ext = suggested_ext or _ext_for_format(item.canonical_format)
            filename = f"{_safe_filename(req_id)}{ext}"
            rel_path = f"{_subdir_for_req_type(item.req_type)}/{filename}"
            target = package_dir / rel_path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(content, bytes):
                target.write_bytes(content)
            else:
                target.write_text(content, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 — 单项失败不中断整体打包
            provenance.append(
                f"[{now.isoformat()}] assemble_package: 序列化 {req_id} 失败，已从数据包排除: {exc}"
            )
            continue

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
                data_source_quality=item.data_source_quality or "fallback",
            )
        )

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

    package = PackageManifest(
        package_info={
            "goal": state.get("user_goal", ""),
            "created_at": now.isoformat(),
            "iteration": state.get("iteration_count", 0),
            "package_id": package_id,
            "status": "complete",
        },
        files=manifest_files,
        missing_items=manifest_missing,
        quality_report=QualityReport(
            total_requirements=len(requirements),
            fulfilled=len(manifest_files),
            missing=len(manifest_missing),
            validation_issues=len(validation_issues),
            avg_confidence=avg_confidence,
            avg_completeness=avg_completeness,
        ),
        provenance_log=[
            f"[{now.isoformat()}] assemble_package: 生成数据包 {package_id}，"
            f"落盘 {len(manifest_files)} 个文件，缺失 {len(manifest_missing)} 项"
        ],
        runtime_check=state.get("runtime_check", {}),
        revision_history=state.get("revision_history", []),
        output_dir=str(package_dir.resolve()),
    )

    (package_dir / "manifest.json").write_text(
        json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (package_dir / "provenance.log").write_text(
        "\n".join(package.provenance_log),
        encoding="utf-8",
    )

    provenance.insert(
        0,
        f"[{now.isoformat()}] assemble_package: 生成数据包 {package_id}，"
        f"落盘 {len(manifest_files)} 个文件",
    )

    return {
        "experiment_package": package,
        "missing_items": missing_items,
        "provenance": provenance,
    }
