"""LLM 决策看板单元测试。

覆盖 E5 工作区式布局的纯逻辑渲染：
- ``build_decision_board`` 五面板结构、当前阶段高亮、四决策点内容
- ``_decision_source`` 的「LLM 生成 / 规则兜底」诚实标注（llm_usage 优先，字段兜底）
- ``build_status_bar`` 的 run_id / 状态徽章 / 五段进度条
- ``semantic_map_json`` 的包落盘文件优先、state 兜底
- 审查面板的 interrupt payload 建议（source=llm|rule）展示
纯逻辑测试，不依赖 gradio 真实渲染。
"""

from __future__ import annotations

import json
from typing import Any

from rdi.frontend.app import (
    _decision_source,
    build_decision_board,
    build_status_bar,
    semantic_map_json,
)

BOARD_OK = {
    "run_id": "run-1",
    "stage_progress": [
        "parse_goal",
        "retrieve_data",
        "parse_and_convert",
        "validate",
        "assemble_package",
    ],
    "retrieval_plan": {
        "req_a": {
            "queries": ["grasp pose dataset"],
            "preferred_sources": ["dexgrasp"],
            "reason": "灵巧手抓取",
            "confidence": 0.8,
        }
    },
    "semantic_map": {
        "req_a": {
            "dataset_name": "dexgrasp",
            "semantic_type": "grasp_pose",
            "rotation": "quaternion_wxyz",
            "origin": "object_center",
            "unit": "meter",
            "field_map": {"rot": "rotation"},
            "confidence": 0.9,
            "needs_human_review": False,
        }
    },
    "validation_issues": [{"severity": "warning", "req_id": "req_a", "message": "完整度略低"}],
    "quality_explanation": {
        "summary": "整体良好",
        "strengths": ["URDF 有效"],
        "risks": [],
        "recommendations": ["补充交叉验证"],
        "usage_guidance": "可直接使用",
        "confidence": 0.85,
    },
    "review_suggestions": {
        "verdict": "satisfied",
        "issues": ["无阻塞缺陷"],
        "rationale": "校验通过",
        "confidence": 0.9,
    },
    "llm_usage": [
        {
            "decision": "retrieval_plan",
            "req_id": "req_a",
            "model": "m1",
            "status": "ok",
            "elapsed": 1.0,
        },
        {"decision": "explain_quality", "model": "m1", "status": "ok", "elapsed": 0.5},
        {"decision": "review_suggestions", "model": "m1", "status": "ok", "elapsed": 0.4},
    ],
}


def test_decision_board_contains_five_panels() -> None:
    board = build_decision_board(BOARD_OK)
    # 五个阶段面板
    for label in ("检索", "转换", "校验", "打包", "审查"):
        assert f"<h3>{label}</h3>" in board
    # 当前阶段 = 最后一个完成阶段（审查）
    assert "rdi-panel-active" in board
    # 四决策点内容
    assert "grasp pose dataset" in board  # 检索 queries
    assert "quaternion_wxyz" in board  # 语义旋转表示
    assert "完整度略低" in board  # 校验问题
    assert "整体良好" in board  # 质量解释
    assert "建议结论" in board  # 审查建议
    # 诚实标注：llm_usage ok → LLM 生成
    assert "LLM 生成" in board
    assert "规则兜底" not in board


def test_decision_board_pending_when_stage_not_run() -> None:
    state: dict[str, Any] = {"user_goal": "g"}
    board = build_decision_board(state)
    assert "尚未执行" in board  # 各面板占位提示
    assert "规则兜底" in board  # quality_explanation 缺失 → 规则兜底标注


def test_decision_source_prefers_llm_usage_status() -> None:
    # llm_usage 记录 fallback → 规则兜底（即使字段存在）
    state = {"llm_usage": [{"decision": "retrieval_plan", "req_id": "r1", "status": "fallback"}]}
    assert _decision_source(state, "retrieval_plan", True, "r1") == "规则兜底"
    # 记录缺失时按字段存在性兜底
    assert _decision_source({}, "explain_quality", True) == "LLM 生成"
    assert _decision_source({}, "explain_quality", False) == "规则兜底"


def test_decision_source_respects_req_id() -> None:
    state = {
        "llm_usage": [
            {"decision": "retrieval_plan", "req_id": "r1", "status": "ok"},
            {"decision": "retrieval_plan", "req_id": "r2", "status": "fallback"},
        ]
    }
    assert _decision_source(state, "retrieval_plan", True, "r1") == "LLM 生成"
    assert _decision_source(state, "retrieval_plan", True, "r2") == "规则兜底"


def test_semantic_human_review_note_rendered() -> None:
    state = dict(BOARD_OK)
    state["semantic_map"] = {
        "req_a": {
            "semantic_type": "robot_urdf",
            "rotation": "unknown",
            "origin": "world",
            "unit": "unknown",
            "field_map": {},
            "confidence": 0.4,
            "needs_human_review": True,
        }
    }
    board = build_decision_board(state)
    assert "语义待人工确认" in board


def test_review_panel_uses_interrupt_payload_source() -> None:
    """首次中断（resume 前）：审查面板读 interrupt_payload.suggestions 的 source 标注。"""
    state: dict[str, Any] = {
        "interrupt_payload": {
            "message": "请审查",
            "suggestions": {
                "verdict": "revised",
                "issues": ["缺失 URDF"],
                "rationale": "必要资产缺失",
                "confidence": 0.6,
                "source": "rule",
            },
        }
    }
    board = build_decision_board(state)
    assert "建议结论：修订" in board
    assert "缺失 URDF" in board
    assert "规则兜底" in board  # source=rule → 规则兜底标注


def test_review_panel_llm_source() -> None:
    state: dict[str, Any] = {
        "interrupt_payload": {
            "suggestions": {
                "verdict": "satisfied",
                "issues": [],
                "rationale": "通过",
                "confidence": 0.9,
                "source": "llm",
            }
        }
    }
    board = build_decision_board(state)
    assert "建议结论：满意" in board
    assert "LLM 生成" in board


def test_status_bar_badges_and_progress() -> None:
    # 待审查徽章 + 五段进度
    bar = build_status_bar(BOARD_OK, "已生成中间结果，请选择审查决定并点击「继续运行」")
    assert "run-1" in bar
    assert "待审查" in bar
    for label in ("检索", "转换", "校验", "打包", "审查"):
        assert label in bar
    # 失败徽章
    assert "失败" in build_status_bar({"run_id": "r"}, "运行失败")
    # 完成徽章
    assert "完成" in build_status_bar({"run_id": "r"}, "运行完成")
    # 运行中徽章（stream 占位）
    assert "运行中" in build_status_bar({}, "运行中")


def test_status_bar_progress_segments() -> None:
    # 完成到打包 → 审查为当前段
    bar = build_status_bar(BOARD_OK, "运行完成")
    assert "rdi-seg-done" in bar
    assert "rdi-seg-current" in bar


def test_semantic_map_json_prefers_package_file(tmp_path: Any) -> None:
    # 构造带落盘 semantic_map.json 的 demo 包目录
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "semantic_map.json").write_text('{"disk": true}', encoding="utf-8")
    state: dict[str, Any] = {
        "semantic_map": {"mem": {"semantic_type": "mesh"}},
        "experiment_package": {"output_dir": str(pkg)},
    }
    assert semantic_map_json(state) == '{"disk": true}'


def test_semantic_map_json_falls_back_to_state() -> None:
    state: dict[str, Any] = {"semantic_map": {"req_a": {"semantic_type": "mesh"}}}
    out = json.loads(semantic_map_json(state))
    assert out["req_a"]["semantic_type"] == "mesh"
    # 演示状态目录存在但无 semantic_map.json → 同样回退 state
    from rdi.frontend.app import DEMO_ROOT

    demo_state = {
        "semantic_map": {"demo": {"semantic_type": "grasp_pose"}},
        "experiment_package": {"output_dir": str(DEMO_ROOT)},
    }
    out = json.loads(semantic_map_json(demo_state))
    assert out["demo"]["semantic_type"] == "grasp_pose"
