# src/rdi/graph/nodes/validate.py
"""数据质量校验节点。

调用校验规则引擎对所有解析后数据项进行检查，输出问题列表。
校验不通过时触发回退重试。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from rdi.models import Priority, Severity, ValIssue

if TYPE_CHECKING:
    from rdi.graph.state import SystemState


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


def node_validate(state: SystemState) -> dict[str, Any]:
    """校验节点：对所有 parsed_data 运行校验规则。

    规则：
    - 解析数据为空 → ERROR
    - 完整度 < 100 → WARNING
    - 置信度 < 1.0 → WARNING
    - 输出路径为空 → WARNING
    - 缺失项优先级为 REQUIRED → ERROR；其余 → WARNING

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
