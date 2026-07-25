# src/rdi/graph/nodes/human_review.py
"""用户审查节点。

用户检查数据包内容，决定是否满意或需要修正。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState


def node_human_review(state: SystemState) -> dict[str, Any]:
    """用户审查节点。

    当前为空骨架实现，默认用户满意（satisfied）。
    后续由人员 E（产品工程师）接入 Gradio 前端交互。

    Returns:
        更新 state 的字段：review_decision, provenance
    """
    # 占位：默认用户满意
    return {
        "review_decision": "satisfied",
        "provenance": [f"[{datetime.now().isoformat()}] human_review: 用户审查通过 (骨架实现)"],
    }
