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
    PackageManifest,
    QualityReport,
)


def node_assemble(state: SystemState) -> dict[str, Any]:
    """整合打包节点。

    当前为空骨架实现，返回占位 PackageManifest。
    后续由人员 E（产品工程师）接入真实打包逻辑。

    Returns:
        更新 state 的字段：experiment_package, missing_items, provenance
    """
    parsed_data = state.get("parsed_data", {})
    requirements = state.get("data_requirements", [])
    validation_issues = state.get("validation_issues", [])

    # 占位：构造 Manifest
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

    package = PackageManifest(
        package_info={
            "goal": state.get("user_goal", ""),
            "created_at": datetime.now().isoformat(),
            "iteration": state.get("iteration_count", 0),
        },
        files=manifest_files,
        missing_items=[],
        quality_report=QualityReport(
            total_requirements=len(requirements),
            fulfilled=len(parsed_data),
            missing=0,
            validation_issues=len(validation_issues),
            avg_confidence=1.0,
            avg_completeness=100.0,
        ),
        provenance_log=[
            f"[{datetime.now().isoformat()}] assemble_package: "
            f"打包 {len(parsed_data)} 个文件 (骨架实现)"
        ],
        output_dir="./data/output_packages/package_placeholder",
    )

    return {
        "experiment_package": package,
        "missing_items": [],
        "provenance": [f"[{datetime.now().isoformat()}] assemble_package: 生成数据包 (骨架实现)"],
    }
