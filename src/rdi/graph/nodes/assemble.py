# src/rdi/graph/nodes/assemble.py
"""数据包整合打包节点。

将所有处理后的数据组装为标准化的可复现实验数据包，
包含结构化 Manifest 文件、目录结构、溯源日志和缺失项标注。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState
from rdi.models import (
    ManifestFile,
    ManifestMissingItem,
    PackageManifest,
    QualityReport,
)


def node_assemble(state: SystemState) -> dict[str, Any]:
    """整合打包节点。

    将解析成功的 ``ParsedItem`` 转为 Manifest 文件列表，
    并保留 ``parse_convert`` 阶段产生的 ``MissingItem``，
    更新质量报告中的缺失数。
    """
    parsed_data = state.get("parsed_data", {})
    missing_items = state.get("missing_items", [])
    requirements = state.get("data_requirements", [])
    validation_issues = state.get("validation_issues", [])

    manifest_files = [
        ManifestFile(
            req_id=req_id,
            path=f"outputs/{req_id}.bin",
            format=item.canonical_format,
            source_url=item.provenance.source_url,
            retrieved_at=item.provenance.retrieved_at,
            transformations=item.provenance.transformations,
            confidence=item.confidence_score,
            completeness=item.completeness_pct,
        )
        for req_id, item in parsed_data.items()
    ]

    manifest_missing = [
        ManifestMissingItem(
            req_id=m.req_id,
            reason=m.reason,
            alternatives=m.alternatives,
        )
        for m in missing_items
    ]

    package = PackageManifest(
        package_info={
            "goal": state.get("user_goal", ""),
            "created_at": datetime.now().isoformat(),
            "iteration": state.get("iteration_count", 0),
        },
        files=manifest_files,
        missing_items=manifest_missing,
        quality_report=QualityReport(
            total_requirements=len(requirements),
            fulfilled=len(parsed_data),
            missing=len(manifest_missing),
            validation_issues=len(validation_issues),
            avg_confidence=1.0,
            avg_completeness=100.0,
        ),
        provenance_log=[
            f"[{datetime.now().isoformat()}] assemble_package: "
            f"打包 {len(parsed_data)} 个文件，缺失 {len(manifest_missing)} 项 (骨架实现)"
        ],
        output_dir="./data/output_packages/package_placeholder",
    )

    return {
        "experiment_package": package,
        "missing_items": missing_items,
        "provenance": [f"[{datetime.now().isoformat()}] assemble_package: 生成数据包 (骨架实现)"],
    }
