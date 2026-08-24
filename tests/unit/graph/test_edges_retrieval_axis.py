# tests/unit/graph/test_edges_retrieval_axis.py
"""P1-A：validate 重试路由区分检索轴失败的测试。"""

from rdi.graph.edges import route_after_validate
from rdi.models import Severity, ValIssue


def _issue(req_id: str, severity: Severity, issue_type: str | None = None) -> ValIssue:
    context = {"issue_type": issue_type} if issue_type else {}
    return ValIssue(severity=severity, req_id=req_id, message="test", context=context)


def test_all_retrieval_axis_errors_pass_without_retry_ids() -> None:
    """P1-A：全部 ERROR 均为检索轴失败且无定向重试排队 → 直出 pass。"""
    state = {
        "validate_iteration": 1,
        "validation_issues": [
            _issue("r1", Severity.ERROR, "retrieval_axis"),
            _issue("r2", Severity.ERROR, "retrieval_axis"),
        ],
    }
    assert route_after_validate(state) == "pass"


def test_retrieval_axis_errors_still_retry_with_retry_ids() -> None:
    """P1-A：human_review 写入定向重试（retry_req_ids）时即使全为检索轴也 retry。"""
    state = {
        "validate_iteration": 1,
        "retry_req_ids": ["r1"],
        "validation_issues": [_issue("r1", Severity.ERROR, "retrieval_axis")],
    }
    assert route_after_validate(state) == "retry"


def test_content_error_retries() -> None:
    """P1-A：存在内容类 ERROR（非检索轴）时仍 retry。"""
    state = {
        "validate_iteration": 1,
        "validation_issues": [
            _issue("r1", Severity.ERROR, "content_validity"),
            _issue("r2", Severity.ERROR, "retrieval_axis"),
        ],
    }
    assert route_after_validate(state) == "retry"


def test_no_issue_type_errors_retry() -> None:
    """既有行为：无 issue_type 标记的 ERROR 视作内容问题 → retry。"""
    state = {
        "validate_iteration": 1,
        "validation_issues": [_issue("r1", Severity.ERROR, None)],
    }
    assert route_after_validate(state) == "retry"


def test_no_errors_pass() -> None:
    """既有行为：无 ERROR 直接 pass（WARNING 不阻塞）。"""
    state = {
        "validate_iteration": 1,
        "validation_issues": [_issue("r1", Severity.WARNING)],
    }
    assert route_after_validate(state) == "pass"


def test_iteration_limit_force_pass() -> None:
    """既有行为：超过 3 次重试强制 pass。"""
    state = {
        "validate_iteration": 3,
        "validation_issues": [_issue("r1", Severity.ERROR, "content_validity")],
    }
    assert route_after_validate(state) == "pass"
