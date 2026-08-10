"""前端进度可视化单元测试。

覆盖 ``build_req_status_table`` 的状态推导规则（成功/降级/失败/检索中/解析中、
失败原因优先级、fallback 标记）与 ``manifest_tree`` 的子目录结构生成。
纯逻辑测试，不依赖 gradio 真实渲染。
"""

from __future__ import annotations

from typing import Any

import pytest

from rdi.frontend.app import (
    build_req_status_table,
    manifest_tree,
    resume_workflow,
    run_workflow,
    summarize_state,
)


def _req(req_id: str, req_type: str = "robot_urdf") -> dict[str, Any]:
    return {"req_id": req_id, "req_type": req_type, "description": f"desc {req_id}"}


def _result(req_id: str, **overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {"req_id": req_id, "status": "success", "is_fallback": False}
    base.update(overrides)
    return base


def _rows_of(state: dict[str, Any]) -> dict[str, list[Any]]:
    headers, rows = build_req_status_table(state)
    assert headers == ["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"]
    return {row[0]: row for row in rows}


def test_headers_constant() -> None:
    headers, rows = build_req_status_table({"data_requirements": []})
    assert headers == ["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"]
    assert rows == []


def test_success_row() -> None:
    state = {
        "data_requirements": [_req("req_a")],
        "retrieval_results": {"req_a": _result("req_a", source="github")},
    }
    row = _rows_of(state)["req_a"]
    assert row[2] == "成功"
    assert row[3] == "github"
    assert row[4] == "否"
    assert row[5] == ""


def test_fallback_row() -> None:
    state = {
        "data_requirements": [_req("req_b")],
        "retrieval_results": {"req_b": _result("req_b", source="huggingface", is_fallback=True)},
    }
    row = _rows_of(state)["req_b"]
    assert row[2] == "降级"
    assert row[3] == "huggingface"
    assert row[4] == "是"


def test_error_row_shows_reason() -> None:
    state = {
        "data_requirements": [_req("req_c")],
        "retrieval_results": {"req_c": _result("req_c", status="error", error_message="超时")},
    }
    row = _rows_of(state)["req_c"]
    assert row[2] == "失败"
    assert row[5] == "超时"


def test_missing_row_default_reason() -> None:
    state = {
        "data_requirements": [_req("req_d")],
        "retrieval_results": {"req_d": _result("req_d", status="missing")},
    }
    row = _rows_of(state)["req_d"]
    assert row[2] == "失败"
    assert row[5] == "未找到匹配数据"


def test_no_retrieval_with_parsed_goal_is_retrieving() -> None:
    state = {
        "user_goal": "goal",
        "parsed_goal": {"goal": "goal"},
        "data_requirements": [_req("req_e")],
    }
    row = _rows_of(state)["req_e"]
    assert row[2] == "检索中"
    assert row[5] == ""


def test_no_retrieval_without_parsed_goal_is_parsing() -> None:
    state = {"data_requirements": [_req("req_f")]}
    row = _rows_of(state)["req_f"]
    assert row[2] == "解析中"


def test_retrieval_errors_drive_failure_and_source() -> None:
    state = {
        "data_requirements": [_req("req_g")],
        "retrieval_errors": [
            {
                "req_id": "req_g",
                "source": "arxiv",
                "error_type": "not_found",
                "error_message": "论文不存在",
            }
        ],
    }
    row = _rows_of(state)["req_g"]
    assert row[2] == "失败"
    assert row[3] == "arxiv"
    assert row[5] == "论文不存在"


def test_validation_issue_fills_reason_when_result_silent() -> None:
    state = {
        "data_requirements": [_req("req_h")],
        "retrieval_results": {"req_h": _result("req_h", status="missing")},
        "validation_issues": [
            {"severity": "error", "req_id": "req_h", "message": "必需需求缺失"}
        ],
    }
    row = _rows_of(state)["req_h"]
    assert row[2] == "失败"
    assert row[5] == "必需需求缺失"


def test_warning_issues_do_not_fill_reason() -> None:
    state = {
        "data_requirements": [_req("req_i")],
        "validation_issues": [
            {"severity": "warning", "req_id": "req_i", "message": "完整度不足 80.0%"}
        ],
    }
    row = _rows_of(state)["req_i"]
    assert row[2] == "解析中"  # 未解析时 warning 不干扰状态
    assert row[5] == ""


def test_result_source_beats_error_source() -> None:
    state = {
        "data_requirements": [_req("req_j")],
        "retrieval_results": {"req_j": _result("req_j", source="github")},
        "retrieval_errors": [
            {"req_id": "req_j", "source": "arxiv", "error_message": "arxiv 失败"}
        ],
    }
    row = _rows_of(state)["req_j"]
    assert row[2] == "成功"
    assert row[3] == "github"  # 成功时不应混入失败源


def test_manifest_tree_subdirs() -> None:
    manifest = {
        "files": [
            {"req_id": "r1", "path": "robots/r1.urdf"},
            {"req_id": "r2", "path": "objects/r2.stl"},
            {"req_id": "r3", "path": "sim_config/r3.xml"},
            {"req_id": "r4", "path": "resources/r4.json"},
        ]
    }
    tree = manifest_tree(manifest)
    assert "- robots" in tree
    assert "- r1.urdf" in tree
    assert "- objects" in tree
    assert "- r2.stl" in tree
    assert "- sim_config" in tree
    assert "- r3.xml" in tree
    assert "- resources" in tree
    assert "- r4.json" in tree


def test_manifest_tree_empty() -> None:
    assert manifest_tree({}) == ""
    assert manifest_tree({"files": []}) == ""
    assert manifest_tree(None) == ""


def test_summarize_state_plain() -> None:
    summary = summarize_state(
        {
            "user_goal": "g",
            "iteration_count": 2,
            "data_requirements": [_req("req_a")],
            "retrieval_errors": [{"req_id": "req_a", "error_message": "x"}],
            "errors": ["e1"],
        }
    )
    assert summary["user_goal"] == "g"
    assert summary["iteration_count"] == 2
    assert summary["data_requirements"] == [_req("req_a")]
    assert summary["errors"] == ["e1"]


# ─── 两阶段真实流程 ───


def test_resume_workflow_no_pending(monkeypatch: pytest.MonkeyPatch) -> None:
    """无待继续运行时给出明确提示，不触碰 graph。"""
    monkeypatch.setattr("rdi.frontend.app._pending_thread_id", None)
    status, summary, req_status, tree, manifest, vissues, rcheck, missing, prov = (
        resume_workflow("satisfied", "")
    )
    assert "没有待继续的运行" in status
    assert summary == {}
    assert req_status["data"] == []
    assert tree == ""
    assert manifest == ""
    assert vissues == []
    assert rcheck == {}
    assert missing == []
    assert prov == ""


def test_run_workflow_real_mode_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实流程首跑中断：9 元组首元素提示到「数据包审查」继续运行，展示中断态中间结果。"""
    interrupted_state: dict[str, Any] = {
        "user_goal": "goal",
        "data_requirements": [_req("req_a")],
        "retrieval_results": {"req_a": _result("req_a", source="github")},
        "validation_issues": [],
        "runtime_check": {},
        "missing_items": [],
        "provenance": ["p1", "p2"],
        "errors": [],
    }
    monkeypatch.setattr(
        "rdi.frontend.app.run_graph",
        lambda goal, paper_file, local_files_json="": (interrupted_state, "tid-1", True),
    )

    result = run_workflow("真实流程", "goal", None, "")

    assert len(result) == 9
    assert "继续运行" in result[0]
    assert result[1]["user_goal"] == "goal"
    assert result[2]["headers"] == [
        "req_id",
        "req_type",
        "状态",
        "数据源",
        "是否 fallback",
        "失败原因",
    ]
    assert result[2]["data"][0][0] == "req_a"
    # 中断态：未到最终展示阶段，tree / manifest 为空
    assert result[3] == ""
    assert result[4] == ""
    assert result[8] == "p1\np2"


def test_run_workflow_demo_mode_returns_9_tuple() -> None:
    """演示流程走 build_demo_state + _format_result，返回完整 9 元组展示数据。"""
    result = run_workflow("演示流程", "演示目标", None, "")
    assert len(result) == 9
    assert result[0] == "运行完成"
    assert result[1]["user_goal"] == "演示目标"
    assert result[3]  # package tree 非空
    assert result[4]  # manifest JSON 非空
