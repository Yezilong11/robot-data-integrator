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
    """System prompt 应列出全部 13 种 req_type 枚举值。"""
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
        "camera_calib",
        "teaching_trajectory",
        "robot_config",
        "benchmark_task",
    ]
    for t in required_types:
        assert t in GOAL_PARSING_SYSTEM


def test_system_prompt_explains_new_req_types() -> None:
    """D2：系统提示应含 4 个新类型的识别说明（拆分规则 + 无内置源留空 fallback 提示）。"""
    assert "camera_calib" in GOAL_PARSING_SYSTEM
    assert "teaching_trajectory" in GOAL_PARSING_SYSTEM
    assert "robot_config" in GOAL_PARSING_SYSTEM
    assert "benchmark_task" in GOAL_PARSING_SYSTEM
    # 识别说明：每类新类型在拆分规则中被点名
    for keyword in ("相机标定", "示教轨迹", "机器人配置", "基准测试"):
        assert keyword in GOAL_PARSING_SYSTEM
    # 诚实语义：新类型 fallback_sources 留空，不硬凑源
    assert "暂无内置数据源" in GOAL_PARSING_SYSTEM
    assert 'fallback_sources": []' in GOAL_PARSING_SYSTEM
    # 示例 13 覆盖四类新类型的完整输出
    assert "示例 13" in GOAL_PARSING_SYSTEM


def test_returned_tuple_has_two_strings() -> None:
    """返回值应为长度 2 的 tuple，且两个元素都是 str。"""
    result = build_goal_parsing_prompt("test")
    assert isinstance(result, tuple)
    assert len(result) == 2
    assert all(isinstance(x, str) for x in result)


def test_build_prompt_with_placeholder_literal_in_input() -> None:
    """用户输入含{user_goal}等字面量时不应被错误替换（str.replace安全隐患）。"""
    goal = "研究 {user_goal} 这个主题"
    _system, user = build_goal_parsing_prompt(goal, paper_text="{paper_text}")
    assert "{user_goal}" in user  # 作为用户输入的原始文本应保留
    assert "{paper_text}" in user  # paper_text中的字面量应保留
    assert "研究" in user


def test_system_prompt_contains_ten_plus_few_shot_examples() -> None:
    """System prompt 应包含 10+ 组完整 few-shot 示例。"""
    assert GOAL_PARSING_SYSTEM.count("### 示例") >= 10


def test_system_prompt_few_shot_covers_required_goals() -> None:
    """5.1 要求的 10 个示例输入应全部出现在 few-shot 中。"""
    inputs = [
        "Franka Panda grasps YCB banana in MuJoCo",
        "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉",
        "Kinova Gen3 picks up EGAD mug in Isaac Sim",
        "UR5 with Robotiq 2F-85 grasps YCB apple",
        "Franka Panda stacks YCB blocks in PyBullet",
        "load UR5 robot model",
        "下载香蕉的 3D 网格模型",
        "get grasp poses for YCB objects",
        "仿真场景配置 MuJoCo",
        "在 PyBullet 中为 Kinova Gen3 规划抓取姿态",
    ]
    for goal in inputs:
        assert goal in GOAL_PARSING_SYSTEM


def test_system_prompt_few_shot_covers_four_types_and_languages() -> None:
    """few-shot 输出应覆盖四类需求（robot_urdf/mesh/grasp/sim_config）与中英文表述。"""
    for req_type in ("robot_urdf", "mesh", "grasp", "sim_config"):
        assert f'"req_type": "{req_type}"' in GOAL_PARSING_SYSTEM
    assert "Franka Panda grasps YCB banana in MuJoCo" in GOAL_PARSING_SYSTEM
    assert "下载香蕉的 3D 网格模型" in GOAL_PARSING_SYSTEM


def test_system_prompt_schema_mentions_unknown_req_type() -> None:
    """Schema 的 req_type 枚举应包含 unknown，供后处理标记未识别需求。"""
    assert "unknown" in GOAL_PARSING_SYSTEM


def test_system_prompt_explains_sensor_data() -> None:
    """sensor_data 应在拆分规则与示例中明确说明，且 fallback_sources 非空。"""
    # 枚举列表含 sensor_data（拆分规则 / 示例中也应出现）
    assert "sensor_data" in GOAL_PARSING_SYSTEM
    # 拆分规则含传感器识别说明
    assert "传感器" in GOAL_PARSING_SYSTEM
    assert "时序数据" in GOAL_PARSING_SYSTEM
    # few-shot 示例 14 覆盖 sensor_data 完整输出
    assert "示例 14" in GOAL_PARSING_SYSTEM
    # 传感器示例 fallback_sources 非空且 Zenodo 优先（GitHub 检索仅返回 README，
    # 不适合传感器时序数据；Zenodo 收录真实数据集），
    # 唯一带 expected_format: CSV 的条目即示例 14 的 sensor_data
    assert (
        '"fallback_sources": ["zenodo", "github"], "expected_format": "CSV"' in GOAL_PARSING_SYSTEM
    )
