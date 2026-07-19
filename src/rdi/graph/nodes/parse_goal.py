# src/rdi/graph/nodes/parse_goal.py
"""目标解析节点：自然语言 + PDF → 结构化数据需求清单。

系统入口节点，调用 Qwen LLM 理解研究目标并拆解数据需求。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState
from rdi.models import DataReq, DataReqType, GoalSpec, Priority


def node_parse_goal(state: SystemState) -> dict[str, Any]:
    """目标解析节点。

    当前为空骨架实现，返回占位数据。
    后续由人员 B（AI工程师）接入 QwenClient 和 PDFParseSkill。

    Returns:
        更新 state 的字段：parsed_goal, data_requirements, provenance
    """
    user_goal = state.get("user_goal", "")

    # 占位数据：生成一个示例需求
    placeholder_goal = GoalSpec(
        research_topic=user_goal or "机器人抓取实验复现",
        experiment_type="grasping",
    )

    placeholder_reqs = [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.ROBOT_URDF,
            description="机器人 URDF 描述文件",
            priority=Priority.REQUIRED,
            keywords=["franka", "panda", "urdf"],
        ),
        DataReq(
            req_id="req_001",
            req_type=DataReqType.SIM_CONFIG,
            description="仿真环境配置文件",
            priority=Priority.REQUIRED,
            keywords=["mujoco", "isaac", "sim"],
        ),
    ]

    return {
        "parsed_goal": placeholder_goal,
        "data_requirements": placeholder_reqs,
        "provenance": [
            f"[{datetime.now().isoformat()}] parse_goal: "
            f"生成 {len(placeholder_reqs)} 条数据需求 (骨架实现)"
        ],
    }
