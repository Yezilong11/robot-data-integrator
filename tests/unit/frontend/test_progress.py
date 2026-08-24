"""前端进度可视化单元测试。

覆盖 ``build_req_status_table`` 的状态推导规则（成功/降级/失败/检索中/解析中、
失败原因优先级、fallback 标记）与 ``manifest_tree`` 的子目录结构生成。
纯逻辑测试，不依赖 gradio 真实渲染。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from rdi.frontend.app import (
    DEMO_ROOT,
    OUTPUT_ROOT,
    build_req_status_table,
    derive_stage_progress,
    manifest_tree,
    resume_workflow,
    run_workflow,
    stage_progress_view,
    summarize_state,
)

if TYPE_CHECKING:
    import pytest


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
        "validation_issues": [{"severity": "error", "req_id": "req_h", "message": "必需需求缺失"}],
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
        "retrieval_errors": [{"req_id": "req_j", "source": "arxiv", "error_message": "arxiv 失败"}],
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
    (
        status,
        summary,
        req_status,
        tree,
        manifest,
        vissues,
        rcheck,
        missing,
        prov,
        stage,
        decision_board,
        llm_usage,
        semantic_map,
        status_bar,
    ) = resume_workflow("satisfied", "")
    assert "没有待继续的运行" in status
    assert summary == {}
    assert req_status["data"] == []
    assert tree == ""
    assert manifest == "{}"
    assert vissues == []
    assert rcheck == {}
    assert missing == []
    assert prov == ""
    assert decision_board == ""
    assert llm_usage == []
    assert semantic_map == "{}"
    assert "待输入" in status_bar  # 无待继续运行 → 待输入徽章
    # 无待继续运行 → 五个阶段均未开始
    assert stage == {
        "目标解析": "未开始",
        "数据检索": "未开始",
        "解析转换": "未开始",
        "质量校验": "未开始",
        "整合打包": "未开始",
    }


def test_run_workflow_real_mode_interrupted(monkeypatch: pytest.MonkeyPatch) -> None:
    """真实流程首跑中断：14 元组首元素提示到审查选择后继续运行，展示中断态中间结果。"""
    interrupted_state: dict[str, Any] = {
        "user_goal": "goal",
        "data_requirements": [_req("req_a")],
        "retrieval_results": {"req_a": _result("req_a", source="github")},
        "validation_issues": [],
        "runtime_check": {},
        "missing_items": [],
        "provenance": ["p1", "p2"],
        "errors": [],
        # E5：LLM 决策层字段（中断态已产出检索规划/语义约定/质量解释）
        "retrieval_plan": {
            "req_a": {
                "queries": ["grasp pose"],
                "preferred_sources": ["dexgrasp"],
                "reason": "示例理由",
                "confidence": 0.8,
            }
        },
        "semantic_map": {"req_a": {"semantic_type": "grasp_pose", "confidence": 0.9}},
        "quality_explanation": {"summary": "示例质量概述", "confidence": 0.85},
        "llm_usage": [
            {"decision": "retrieval_plan", "req_id": "req_a", "status": "ok"},
            {"decision": "explain_quality", "status": "ok"},
        ],
    }
    monkeypatch.setattr(
        "rdi.frontend.app.run_graph",
        lambda goal, paper_file, local_files_json="": (interrupted_state, "tid-1", True),
    )

    result = run_workflow("真实流程", "goal", None, "")

    assert len(result) == 14
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
    # 中断态阶段进度：mock state 有检索结果与校验记录 → 检索/校验已完成，其余未开始
    assert result[9]["数据检索"] == "完成"
    assert result[9]["质量校验"] == "完成"
    assert result[9]["整合打包"] == "未开始"
    # 新组合视图：灯带 + LLM 分析 + 目标输出
    assert "LLM 分析" in result[10]
    assert "目标输出" in result[10]
    assert "rdi-wf-current" in result[10]
    # E5：llm_usage / semantic_map / 状态条同步输出
    assert result[11] == interrupted_state["llm_usage"]
    assert "grasp_pose" in result[12]
    assert "待审查" in result[13]  # 中断态 → 待审查徽章


def test_run_workflow_demo_mode_returns_14_tuple() -> None:
    """演示流程走 build_demo_state + _format_result，返回完整 14 元组展示数据。"""
    result = run_workflow("演示流程", "演示目标", None, "")
    assert len(result) == 14
    assert result[0] == "运行完成"
    assert result[1]["user_goal"] == "演示目标"
    assert result[3]  # package tree 非空
    assert result[4]  # manifest JSON 非空
    # E3：演示产物 manifest 标记 demo=true
    manifest = json.loads(result[4])
    assert manifest["package_info"]["demo"] == "true"
    # 演示流程视为完整跑完：五个阶段全部完成
    assert result[9] == {
        "目标解析": "完成",
        "数据检索": "完成",
        "解析转换": "完成",
        "质量校验": "完成",
        "整合打包": "完成",
    }
    # 新组合视图：灯带 + LLM 分析 + 目标输出
    assert "LLM 分析" in result[10]
    assert "目标输出" in result[10]
    assert "LLM 生成" in result[10]
    assert "建议通过审查" in result[10]
    assert "robot-data-package 已生成" in result[10]
    # E5：llm_usage 演示记录（decision/model/status/elapsed）
    assert result[11]
    assert result[11][0]["decision"] == "retrieval_plan"
    assert result[11][0]["status"] == "ok"
    assert "semantic_type" in result[12]  # semantic_map.json 内容
    assert "完成" in result[13]  # 演示完整跑完 → 完成徽章
    assert "run_id" in result[13]  # 状态条含 run_id


def test_demo_package_isolated_in_demo_root() -> None:
    """E3：演示流程产物写入独立 DEMO_ROOT，不落入真实 output_packages，且带 demo 标记。"""
    result = run_workflow("演示流程", "隔离目标", None, "")
    manifest = json.loads(result[4])
    package_dir = Path(manifest["output_dir"])
    assert package_dir.is_relative_to(DEMO_ROOT)
    assert not package_dir.is_relative_to(OUTPUT_ROOT)
    assert manifest["package_info"]["demo"] == "true"
    # 演示产物实际落盘
    assert (package_dir / "manifest.json").is_file()
    assert (package_dir / "files" / "goal.txt").is_file()


def _fallback_dirs() -> set[str]:
    return {p.name for p in OUTPUT_ROOT.glob("fallback-package-*")}


def test_real_workflow_failure_no_fallback_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """E3：真实流程返回无 experiment_package 的失败态 → 不创建 fallback 包目录，按失败呈现。"""
    failed_state: dict[str, Any] = {
        "user_goal": "goal",
        "run_id": "r-1",
        "errors": ["backend exploded"],
        "stage_progress": [],
    }
    monkeypatch.setattr(
        "rdi.frontend.app.run_graph",
        lambda goal, paper_file, local_files_json="": (failed_state, "tid-1", False),
    )

    before = _fallback_dirs()
    result = run_workflow("真实流程", "goal", None, "")
    after = _fallback_dirs()

    assert before == after  # 未创建任何 fallback 包目录
    assert len(result) == 14
    assert result[0] == "运行失败"  # 空产物 + 有错误 → 真实失败
    assert result[1]["errors"] == ["backend exploded"]
    assert result[3] == ""  # 无数据包目录树
    assert result[4] == "{}"  # 空产物 manifest
    assert result[8] == ""  # 无 provenance
    assert "失败" in result[13]  # 失败徽章


def test_real_workflow_exception_no_fallback_package(monkeypatch: pytest.MonkeyPatch) -> None:
    """E3：真实流程 run_graph 抛异常 → 同样不伪造 fallback 包，按真实失败呈现。"""

    def boom(goal: str, paper_file: Any, local_files_json: str = "") -> Any:
        raise RuntimeError("graph crashed")

    monkeypatch.setattr("rdi.frontend.app.run_graph", boom)

    before = _fallback_dirs()
    result = run_workflow("真实流程", "goal", None, "")
    after = _fallback_dirs()

    assert before == after  # 未创建任何 fallback 包目录
    assert len(result) == 14
    assert result[0] == "运行失败"
    assert result[1]["errors"] == ["graph crashed"]
    assert result[3] == ""
    assert result[4] == "{}"
    assert "失败" in result[13]


def test_stage_progress_view_explicit_record() -> None:
    """显式 stage_progress（run_graph 流式记录）优先于字段反推。"""
    view = stage_progress_view({"stage_progress": ["parse_goal", "retrieve_data"]})
    assert view["目标解析"] == "完成"
    assert view["数据检索"] == "完成"
    assert view["解析转换"] == "未开始"
    assert view["质量校验"] == "未开始"
    assert view["整合打包"] == "未开始"


def test_stage_progress_view_derives_from_fields() -> None:
    """无 stage_progress 记录时按 state 字段反推（resume / 旧状态兜底）。"""
    state: dict[str, Any] = {
        "parsed_goal": {"goal": "g"},
        "retrieval_results": {"a": {"req_id": "a"}},
        "parsed_data": {"a": {"req_id": "a"}},
        "validation_issues": [],
        "experiment_package": {"files": []},
    }
    assert stage_progress_view(state) == {
        "目标解析": "完成",
        "数据检索": "完成",
        "解析转换": "完成",
        "质量校验": "完成",
        "整合打包": "完成",
    }
    assert derive_stage_progress({}) == []
