# src/rdi/graph/nodes/retrieve_data.py
"""数据查找节点。

按数据需求清单逐个调用 Adapter 执行查找，
汇总所有结果后返回 state 更新。
"""

import time
from datetime import datetime
from typing import Any

from rdi.adapters.registry import select_adapter
from rdi.exceptions import AdapterError
from rdi.graph.state import SystemState
from rdi.hermes.engine import HermesEngine
from rdi.models import DataReqType, RetrievalResult, SearchResult

# 模块级懒加载 HermesEngine 单例，便于测试 monkeypatch
_hermes_engine: HermesEngine | None = None


def _get_hermes_engine() -> HermesEngine:
    """返回缓存的 HermesEngine 单例；首次调用时创建。"""
    global _hermes_engine
    if _hermes_engine is None:
        _hermes_engine = HermesEngine()
    return _hermes_engine


def _extract_context_keywords(requirements: list[Any]) -> list[str]:
    """提取非 sim_config 需求中的机器人/物体名称等上下文关键词。

    当 sim_config 需求查找时，把这些关键词作为额外 query token，帮助 Adapter
    命中包含对应机器人/物体名称的 MuJoCo MJCF 资源。
    """
    context: list[str] = []
    for req in requirements:
        if getattr(req, "req_type", None) == DataReqType.SIM_CONFIG:
            continue
        for kw in getattr(req, "keywords", []) or []:
            if kw and str(kw).strip():
                context.append(str(kw).strip())
        desc = getattr(req, "description", "") or ""
        desc = desc.strip()
        if desc:
            context.append(desc)
    return context


async def node_retrieve_data(state: SystemState) -> dict[str, Any]:
    """按数据需求清单逐个执行查找，返回合并后的检索结果。

    原实现通过 ``Send`` 做 fan-out，但 LangGraph 要求普通节点只能返回 dict，
    因此改为在节点内部顺序调用 ``node_retrieve_single`` 并汇总结果。
    """
    requirements = state.get("data_requirements", [])
    if not requirements:
        return {
            "provenance": [f"[{datetime.now().isoformat()}] retrieve_data: 无数据需求，跳过查找"],
        }

    context_keywords = _extract_context_keywords(requirements)
    retrieval_results: dict[str, RetrievalResult] = {}
    provenance: list[str] = []

    for req in requirements:
        payload = {
            "req_id": req.req_id,
            "req_type": req.req_type.value,
            "description": req.description,
            "keywords": req.keywords,
            "fallback_sources": [s.value for s in req.fallback_sources],
            "context_keywords": context_keywords,
        }
        update = await node_retrieve_single(payload)
        retrieval_results.update(update.get("retrieval_results", {}))
        provenance.extend(update.get("provenance", []))

    return {
        "retrieval_results": retrieval_results,
        "provenance": provenance,
    }


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
    keywords = payload.get("keywords") or []
    # C2-fix: 用英文/中文关键词搜索，而不是整段中文长描述。
    # Adapter 的 fallback 列表多为英文 id/title，中文 description 会导致匹配失败。
    query = " ".join(str(k) for k in keywords) if keywords else description

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
    fallback_sources = payload.get("fallback_sources") or []
    fallback_index = {src: i for i, src in enumerate(fallback_sources)}
    sorted_adapters = sorted(
        adapter_classes,
        key=lambda cls: (
            fallback_index.get(cls.source.value, len(fallback_sources)),
            priority_index.get(cls.source.value, len(priority_sources)),
        ),
    )

    # C2-fix: Adapter fallback 搜索多使用单 token 匹配，直接传整句中文+英文
    # 会导致无匹配。先尝试完整 query，再逐个尝试 keyword/英文 token。
    queries = [query]
    seen: set[str] = {query.lower()}
    if keywords:
        for kw in keywords:
            kw_str = str(kw).strip()
            if kw_str and kw_str.lower() not in seen:
                seen.add(kw_str.lower())
                queries.append(kw_str)

    # sim_config 查找时，把机器人/物体名称等上下文关键词作为额外 query token，
    # 提升命中对应 MuJoCo MJCF 资源的概率。
    if req_type == DataReqType.SIM_CONFIG.value:
        context_keywords = payload.get("context_keywords") or []
        if context_keywords:
            context_query = " ".join(str(k).strip() for k in context_keywords if str(k).strip())
            combined = f"{query} {context_query}".strip()
            if combined and combined.lower() not in seen:
                queries.insert(1, combined)
                seen.add(combined.lower())
            for kw in context_keywords:
                kw_str = str(kw).strip()
                if kw_str and kw_str.lower() not in seen:
                    seen.add(kw_str.lower())
                    queries.append(kw_str)

    had_empty_search = False
    last_source = ""

    for idx, adapter_cls in enumerate(sorted_adapters):
        is_fallback = idx > 0
        last_source = adapter_cls.source.value
        try:
            # ponytail: type[BaseAdapter] 的 __init__ 签名包含 base_url，但各子类均为无参构造；
            # mypy 无法推导子类重载，此处忽略构造参数检查。
            adapter = adapter_cls()  # type: ignore[call-arg]
            search_results: list[SearchResult] = []
            for q in queries:
                search_results = await adapter.search(q)
                if search_results:
                    break
            if not search_results:
                had_empty_search = True
                continue
            try:
                raw = await adapter.fetch(search_results[0].item_id, req_type=DataReqType(req_type))
            except TypeError:
                # 兼容旧 Adapter 的 fetch(item_id) 签名
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
