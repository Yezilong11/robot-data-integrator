# src/rdi/graph/nodes/human_review.py
"""用户审查节点。

用户检查数据包内容，决定是否满意或需要修正。
尊重 state 中已有的 ``review_decision``（前端在初始 state 传入），
把 ``user_feedback`` 逐条追加到 provenance。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState


def node_human_review(state: SystemState) -> dict[str, Any]:
    """用户审查节点：保留已有审查决定，反馈写入 provenance。

    Returns:
        更新 state 的字段：review_decision, provenance
    """
    now = datetime.now()
    decision = state.get("review_decision", "satisfied")
    feedback = state.get("user_feedback", [])

    provenance = [f"[{now.isoformat()}] human_review: 审查决定为 {decision}"]
    for message in feedback:
        provenance.append(f"[{now.isoformat()}] human_review: 用户反馈: {message}")

    return {
        "review_decision": decision,
        "provenance": provenance,
    }
