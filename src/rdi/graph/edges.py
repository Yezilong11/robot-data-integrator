# src/rdi/graph/edges.py
"""条件边路由逻辑集中定义。

节点内部不直接做路由判断，所有条件分支逻辑集中在此，
便于维护和测试。
"""

from rdi.graph.state import SystemState


def route_after_validate(state: SystemState) -> str:
    """validate 节点后的路由：校验通过则打包，否则重试。

    重试次数超过 3 次时强制通过，避免无限循环。
    P1-A：全部 ERROR 均为``retrieval_axis``（数据源确实无此数据，重试拿不到
    新结果）且无 human_review 写入的定向重试排队时，直出 pass，不再空转重试。

    Args:
        state: 当前全局状态

    Returns:
        "pass" 或 "retry"
    """
    issues = state.get("validation_issues", [])
    iteration = state.get("validate_iteration", 0)

    # 超过 3 次重试，强制通过（降级处理）
    if iteration >= 3:
        return "pass"

    # 存在 ERROR 级问题才需要重试，WARNING 可通过
    errors = [issue for issue in issues if issue.severity == "error"]
    if not errors:
        return "pass"

    if not state.get("retry_req_ids") and all(
        issue.context.get("issue_type") == "retrieval_axis" for issue in errors
    ):
        return "pass"
    return "retry"


def route_after_review(state: SystemState) -> str:
    """human_review 节点后的路由：满意结束，修订回 parse_goal，不满意回 retrieve_data。

    Args:
        state: 当前全局状态

    Returns:
        "satisfied" / "revised" / "unsatisfied" 之一
    """
    decision = state.get("review_decision", "satisfied")
    return decision
