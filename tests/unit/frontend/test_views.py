"""新增视图渲染函数单元测试。

覆盖工作区式改造后的纯逻辑渲染：
- ``render_workflow_html`` 灯带 5 节点（done/current/pending）
- ``render_llm_analysis_html`` 思考文本 + 来源标注，不含 confidence 数字
- ``render_target_output_html`` 单行汇总 + 可展开文件清单
- ``render_file_tree_html`` VSCode 风格文件树（缩进/类型图标/文件名）
- ``render_inspector_html`` 检查器详情概览
- ``build_decision_board`` 组合视图（灯带 + LLM 分析 + 目标输出）
纯逻辑测试，不依赖 gradio 真实渲染。
"""

from __future__ import annotations

from typing import Any

from rdi.frontend.app import (
    build_decision_board,
    render_file_tree_html,
    render_inspector_html,
    render_llm_analysis_html,
    render_target_output_html,
    render_workflow_html,
)


def _state() -> dict[str, Any]:
    return {
        "run_id": "run-1",
        "stage_progress": [
            "parse_goal",
            "retrieve_data",
            "parse_and_convert",
            "validate",
            "assemble_package",
        ],
        "retrieval_plan": {
            "req_a": {"queries": ["grasp pose"], "reason": "优先检索抓取数据", "confidence": 0.8}
        },
        "semantic_map": {
            "req_a": {
                "semantic_type": "grasp_pose",
                "rotation": "quaternion_wxyz",
                "origin": "object_center",
                "unit": "meter",
            }
        },
        "validation_issues": [],
        "quality_explanation": {"summary": "整体良好", "confidence": 0.9},
        "review_suggestions": {"verdict": "satisfied", "rationale": "校验通过", "confidence": 0.9},
        "llm_usage": [
            {"decision": "retrieval_plan", "req_id": "req_a", "status": "ok"},
            {"decision": "explain_quality", "status": "ok"},
            {"decision": "review_suggestions", "status": "ok"},
        ],
        "experiment_package": {
            "package_info": {"package_id": "p1"},
            "files": [
                {"req_id": "req_a", "path": "robots/req_a.urdf"},
                {"req_id": "req_b", "path": "objects/req_b.stl"},
            ],
            "quality_report": {
                "total_requirements": 1,
                "fulfilled": 1,
                "missing": 0,
                "validation_issues": 0,
            },
            "output_dir": "/nonexistent-dir",
        },
    }


def test_workflow_contains_five_stops() -> None:
    html = render_workflow_html(_state())
    for label in ("检索", "转换", "校验", "打包", "审查"):
        assert label in html
    assert "rdi-wf-rail" in html
    assert "rdi-wf-current" in html
    assert "rdi-wf-done" in html


def test_llm_analysis_contains_source_and_no_confidence() -> None:
    html = render_llm_analysis_html(_state())
    assert "LLM 分析" in html
    assert "LLM 生成" in html
    assert "校验通过" in html  # 当前阶段为审查，rationale 被提取
    assert "0.8" not in html
    assert "0.9" not in html


def test_target_output_has_summary() -> None:
    html = render_target_output_html(_state())
    assert "目标输出" in html
    assert "robot-data-package 已生成" in html
    assert "rdi-output" in html


def test_file_tree_has_paths() -> None:
    html = render_file_tree_html(_state())
    assert "robots" in html
    assert "req_a.urdf" in html
    assert "objects" in html
    assert "req_b.stl" in html


def test_file_tree_empty_state(monkeypatch: Any, tmp_path: Any) -> None:
    monkeypatch.setattr("rdi.frontend.app.OUTPUT_ROOT", tmp_path / "out")
    monkeypatch.setattr("rdi.frontend.app.DEMO_ROOT", tmp_path / "demo")
    assert "暂无数据包文件" in render_file_tree_html({})


def test_inspector_shows_quality_report() -> None:
    html = render_inspector_html(_state())
    assert "当前文件" in html
    assert "robots/req_a.urdf" in html
    assert "语义约定" in html
    assert "grasp_pose" in html
    assert "质量校验" in html
    assert "来源标注" in html


def test_decision_board_combines_views() -> None:
    board = build_decision_board(_state())
    assert "rdi-wf-rail" in board
    assert "LLM 分析" in board
    assert "目标输出" in board
