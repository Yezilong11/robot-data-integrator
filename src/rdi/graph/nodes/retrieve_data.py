# src/rdi/graph/nodes/retrieve_data.py
"""数据查找节点。

负责将数据需求清单分发为并行查找任务，
使用 LangGraph Send API 实现动态 fan-out。
"""

import time
from datetime import datetime
from typing import Any

from langgraph.types import Send

from rdi.adapters.registry import select_adapter
from rdi.exceptions import AdapterError
from rdi.graph.state import SystemState
from rdi.hermes.engine import HermesEngine
from rdi.models import DataReqType, RetrievalResult

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


async def node_retrieve_single(payload: dict[str, Any]) -> dict[str, Any]:
    """单个数据需求的查找执行节点。

    按 Hermes 优先级逐个尝试候选 Adapter：search → fetch。
    首个候选源成功返回 success；非首个成功标记 is_fallback；
    全部 search 无结果返回 missing；全部抛 AdapterError 返回 error。

    Args:
        payload: Send 传递的参数字典

    Returns:
        更新 state 的字段：retrieval_results、provenance
    """
    req_id = payload["req_id"]
    req_type = payload.get("req_type", "unknown")
    description = payload.get("description", "")
    query = description

    hermes = _get_hermes_engine()
    experience_hint = hermes.inject_experience(description, req_type)

    provenance = [f"[{datetime.now().isoformat()}] retrieve_data: 查找 {req_id} (type={req_type})"]
    if experience_hint:
        provenance.append(experience_hint)

    start = time.monotonic()

    try:
        adapter_classes = select_adapter(DataReqType(req_type))
    except ValueError:
        adapter_classes = []
    priority_sources = hermes.get_source_priority(req_type)
    priority_index = {src: i for i, src in enumerate(priority_sources)}
    sorted_adapters = sorted(
        adapter_classes,
        key=lambda cls: priority_index.get(cls.source.value, len(priority_sources)),
    )

    had_empty_search = False
    last_source = ""

    for idx, adapter_cls in enumerate(sorted_adapters):
        is_fallback = idx > 0
        last_source = adapter_cls.source.value
        try:
            # ponytail: type[BaseAdapter] 的 __init__ 签名包含 base_url，但各子类均为无参构造；
            # mypy 无法推导子类重载，此处忽略构造参数检查。
            adapter = adapter_cls()  # type: ignore[call-arg]
            search_results = await adapter.search(query)
            if not search_results:
                had_empty_search = True
                continue
            raw = await adapter.fetch(search_results[0].item_id)
            elapsed = time.monotonic() - start
            result = RetrievalResult(
                req_id=req_id,
                status="success",
                data=raw,
                source=raw.source,
                is_fallback=is_fallback,
                search_results=search_results,
                elapsed_seconds=elapsed,
            )
            hermes.record_experience(
                task_desc=description,
                req_type=req_type,
                result_status="success",
                sources_used=[raw.source.value],
                elapsed_seconds=elapsed,
            )
            return {
                "retrieval_results": {req_id: result},
                "provenance": provenance,
            }
        except AdapterError:
            continue

    elapsed = time.monotonic() - start
    if had_empty_search:
        status = "missing"
        error_message = ""
    else:
        status = "error"
        error_message = f"所有候选源均失败: {req_type}"
    sources_used = [last_source] if last_source else []

    result = RetrievalResult(
        req_id=req_id,
        status=status,
        error_message=error_message,
        elapsed_seconds=elapsed,
    )
    hermes.record_experience(
        task_desc=description,
        req_type=req_type,
        result_status=status,
        sources_used=sources_used,
        elapsed_seconds=elapsed,
    )
    return {
        "retrieval_results": {req_id: result},
        "provenance": provenance,
    }
