# tests/unit/test_goal_parsing_prompt.py
"""goal_parsing Prompt 构建测试。"""

from rdi.intelligence.prompts import (
    GOAL_PARSING_SYSTEM,
    build_goal_parsing_prompt,
)


def test_build_prompt_without_paper() -> None:
    """无 paper_text 时，user prompt 应含"未提供论文"且无残留占位符。"""
    _system, user = build_goal_parsing_prompt("复现 Franka Panda 抓取实验")
    assert "未提供论文" in user
    assert "{paper_text}" not in user
    assert "{user_goal}" not in user
    assert "复现 Franka Panda 抓取实验" in user


def test_build_prompt_with_paper() -> None:
    """有 paper_text 时，user prompt 应含论文文本且无残留占位符。"""
    paper_text = "这是一篇关于 Franka Panda 抓取的论文..."
    _system, user = build_goal_parsing_prompt("复现", paper_text=paper_text)
    assert paper_text in user
    assert "未提供论文" not in user
    assert "{paper_text}" not in user
    assert "{user_goal}" not in user
    assert "复现" in user


def test_system_prompt_mentions_json_schema() -> None:
    """System prompt 应包含 JSON / req_id / req_type 等关键字。"""
    assert "JSON" in GOAL_PARSING_SYSTEM
    assert "req_id" in GOAL_PARSING_SYSTEM
    assert "req_type" in GOAL_PARSING_SYSTEM


def test_system_prompt_lists_all_req_types() -> None:
    """System prompt 应列出全部 9 种 req_type 枚举值。"""
    required_types = [
        "paper",
        "code",
        "dataset",
        "robot_urdf",
        "mesh",
        "grasp",
        "sim_config",
        "policy_model",
        "sensor_data",
    ]
    for t in required_types:
        assert t in GOAL_PARSING_SYSTEM


def test_returned_tuple_has_two_strings() -> None:
    """返回值应为长度 2 的 tuple，且两个元素都是 str。"""
    result = build_goal_parsing_prompt("test")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(isinstance(x, str) for x in result)
