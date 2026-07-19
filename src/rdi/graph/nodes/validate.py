# src/rdi/graph/nodes/validate.py
"""数据质量校验节点。

调用校验规则引擎对所有解析后数据项进行检查，
输出问题列表。校验不通过时触发回退重试。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from rdi.graph.state import SystemState
    from rdi.models import ValIssue


def node_validate(state: SystemState) -> dict[str, Any]:
    """校验节点：对所有 parsed_data 运行校验规则。

    当前为空骨架实现，返回空问题列表（全部通过）。
    后续由人员 E（产品工程师）接入校验规则引擎。

    Returns:
        更新 state 的字段：validation_issues, iteration_count, provenance
    """
    parsed_data = state.get("parsed_data", {})
    iteration = state.get("iteration_count", 0) + 1

    issues: list[ValIssue] = []

    return {
        "validation_issues": issues,
        "iteration_count": iteration,
        "provenance": [
            f"[{datetime.now().isoformat()}] validate: "
            f"检查 {len(parsed_data)} 项，发现 0 个问题 (骨架实现)"
        ],
    }
