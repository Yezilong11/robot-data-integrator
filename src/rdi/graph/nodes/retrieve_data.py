# src/rdi/graph/nodes/retrieve_data.py
"""数据查找节点。

负责将数据需求清单分发为并行查找任务，
使用 LangGraph Send API 实现动态 fan-out。
"""

from datetime import datetime
from typing import Any

from langgraph.types import Send

from rdi.graph.state import SystemState
from rdi.hermes.engine import HermesEngine
from rdi.models import DataSource, RawData, RetrievalResult

# 模块级懒加载 HermesEngine 单例，便于测试 monkeypatch
_hermes_engine: HermesEngine | None = None


def _get_hermes_engine() -> HermesEngine:
    """返回缓存的 HermesEngine 单例；首次调用时创建。"""
    global _hermes_engine
    if _hermes_engine is None:
        _hermes_engine = HermesEngine()
    return _hermes_engine


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

    当前为骨架实现：调用 Hermes 注入历史经验，返回占位成功结果，
    再将本次经验记录回 Hermes。后续由人员 C（数据工程师）接入真实 Adapter。

    Args:
        payload: Send 传递的参数字典

    Returns:
        更新 state 的字段：retrieval_results
    """
    req_id = payload["req_id"]
    req_type = payload.get("req_type", "unknown")
    description = payload.get("description", "")

    # ponytail: Hermes 经验注入，等 C 的 Adapter 接入后拼接到 LLM 推理上下文
    hermes = _get_hermes_engine()
    experience_hint = hermes.inject_experience(description, req_type)  # noqa: F841

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

    # 记录经验到 Hermes
    hermes.record_experience(
        task_desc=description,
        req_type=req_type,
        result_status=placeholder_result.status,
        sources_used=([placeholder_result.data.source.value] if placeholder_result.data else []),
        elapsed_seconds=placeholder_result.elapsed_seconds,
    )

    return {
        "retrieval_results": {req_id: placeholder_result},
        "provenance": [
            f"[{datetime.now().isoformat()}] retrieve_data: 查找 {req_id} "
            "(骨架实现 + Hermes经验记录)"
        ],
    }
