# src/rdi/graph/edges.py
"""条件边路由逻辑集中定义。

节点内部不直接做路由判断，所有条件分支逻辑集中在此，
便于维护和测试。
"""

from rdi.graph.state import SystemState


def route_after_validate(state: SystemState) -> str:
    """validate 节点后的路由：校验通过则打包，否则重试。

    重试次数超过 3 次时强制通过，避免无限循环。

    Args:
        state: 当前全局状态

    Returns:
        "pass" 或 "retry"
    """
    issues = state.get("validation_issues", [])
    iteration = state.get("iteration_count", 0)

    # 超过 3 次重试，强制通过（降级处理）
    if iteration >= 3:
        return "pass"

    # 存在 ERROR 级问题才需要重试，WARNING 可通过
    has_errors = any(issue.severity == "error" for issue in issues)
    return "retry" if has_errors else "pass"


def route_after_review(state: SystemState) -> str:
    """human_review 节点后的路由：用户满意则结束。

    Args:
        state: 当前全局状态

    Returns:
        "satisfied" 或 "revise"
    """
    decision = state.get("review_decision", "satisfied")
    return decision
