# src/rdi/graph/nodes/retrieve_data.py
"""数据查找节点。

负责将数据需求清单分发为并行查找任务，
使用 LangGraph Send API 实现动态 fan-out。
"""

from datetime import datetime
from typing import Any

from langgraph.types import Send

from rdi.graph.state import SystemState
from rdi.models import DataSource, RawData, RetrievalResult


def node_retrieve_data(state: SystemState) -> list[Send]:
    """根据数据需求清单动态生成并行查找任务。

    当前为空骨架实现，每个需求返回一个占位 Send。
    后续由人员 C（数据工程师）接入真实 Adapter。

    Returns:
        Send 列表，每个 Send 指向 retrieve_single 节点
    """
    requirements = state.get("data_requirements", [])

    sends = []
    for req in requirements:
        sends.append(
            Send(
                "retrieve_single",
                {
                    "req_id": req.req_id,
                    "req_type": req.req_type.value,
                    "description": req.description,
                    "keywords": req.keywords,
                },
            )
        )
    return sends


def node_retrieve_single(payload: dict[str, Any]) -> dict[str, Any]:
    """单个数据需求的查找执行节点。

    当前为空骨架实现，返回占位成功结果。
    后续由人员 C（数据工程师）接入真实 Adapter。

    Args:
        payload: Send 传递的参数字典

    Returns:
        更新 state 的字段：retrieval_results
    """
    req_id = payload["req_id"]
    # 占位变量，后续接入真实 Adapter 时会使用
    _req_type = payload.get("req_type", "unknown")

    # 占位数据：模拟查找成功
    placeholder_result = RetrievalResult(
        req_id=req_id,
        status="success",
        data=RawData(
            source=DataSource.GITHUB,
            item_id=f"placeholder_{req_id}",
            format="unknown",
            data=b"placeholder data",
            url="https://example.com/placeholder",
        ),
        elapsed_seconds=0.1,
    )

    return {
        "retrieval_results": {req_id: placeholder_result},
        "provenance": [f"[{datetime.now().isoformat()}] retrieve_data: 查找 {req_id} (骨架实现)"],
    }
