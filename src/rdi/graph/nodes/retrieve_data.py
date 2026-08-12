# src/rdi/graph/nodes/retrieve_data.py
"""数据查找节点。

按数据需求清单并行调用 Adapter 执行查找（每个需求有独立超时预算），
汇总所有结果后返回 state 更新。
"""

import asyncio
import time
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rdi.adapters.registry import select_adapter
from rdi.config.settings import settings
from rdi.exceptions import (
    AdapterAuthError,
    AdapterCatalogError,
    AdapterError,
    AdapterNotFoundError,
    AdapterRateLimitError,
    AdapterTimeoutError,
)
from rdi.graph.state import SystemState
from rdi.hermes.engine import HermesEngine
from rdi.intelligence import decisions
from rdi.logging import get_logger
from rdi.models import DataReqType, DataSource, RetrievalError, RetrievalResult, SearchResult

if TYPE_CHECKING:
    from rdi.intelligence.schemas import RetrievalPlan

# 模块级懒加载 HermesEngine 单例，便于测试 monkeypatch
_hermes_engine: HermesEngine | None = None

logger = get_logger(__name__)


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


def _to_retrieval_error(req_id: str, source: DataSource, exc: AdapterError) -> RetrievalError:
    """把 AdapterError 归类为结构化 RetrievalError。

    按异常子类 / HTTP 状态码优先级归类 error_type：
    rate_limit(429) > timeout(408) > not_found(404) > auth(401/403) > unknown。
    """
    if isinstance(exc, AdapterRateLimitError) or exc.status_code == 429:
        error_type = "rate_limit"
    elif isinstance(exc, AdapterTimeoutError) or exc.status_code == 408:
        error_type = "timeout"
    elif isinstance(exc, AdapterNotFoundError) or exc.status_code == 404:
        error_type = "not_found"
    elif isinstance(exc, AdapterAuthError) or exc.status_code in (401, 403):
        error_type = "auth"
    else:
        error_type = "unknown"
    return RetrievalError(
        req_id=req_id,
        source=source,
        error_type=error_type,
        error_message=str(exc),
    )


def _first_candidate_source(req_type: str) -> DataSource:
    """返回需求最先尝试的候选源。

    超时发生时无法确定尝试到哪个 source，而 ``RetrievalError.source`` 是必填
    字段；``DataSource`` 没有 UNKNOWN 枚举（common.py 不在本任务改动范围），
    因此用注册表中该需求的第一个候选源近似表示（即单需求正常流程里
    最先尝试的源，与真实失败源最接近）。
    """
    try:
        adapter_classes = select_adapter(DataReqType(req_type))
    except ValueError:
        adapter_classes = []
    if adapter_classes:
        return adapter_classes[0].source
    # 兜底：该需求没有注册任何候选源（异常路径），正常流程不会走到；
    # 取 GITHUB 仅用于满足 RetrievalError.source 必填约束。
    return DataSource.GITHUB


async def _retrieve_single_with_timeout(payload: dict[str, Any]) -> dict[str, Any]:
    """单个需求的检索任务：用 ``settings.per_req_timeout`` 独立超时预算包裹。

    超时时返回结构化 timeout 失败（RetrievalResult status=error + RetrievalError
    error_type=timeout + provenance 记录），不向外抛异常，因此单需求超时
    不会阻塞 ``asyncio.gather`` 中的其他需求。
    """
    req_id = payload["req_id"]
    start = time.monotonic()
    try:
        async with asyncio.timeout(settings.per_req_timeout):
            return await node_retrieve_single(payload)
    except TimeoutError:
        elapsed = time.monotonic() - start
        message = "检索超时（超过 per_req_timeout 秒）"
        logger.warning(
            "retrieve.timeout",
            req_id=req_id,
            status="timeout",
            elapsed_seconds=round(elapsed, 3),
        )
        result = RetrievalResult(
            req_id=req_id,
            status="error",
            error_message=message,
            elapsed_seconds=elapsed,
        )
        error = RetrievalError(
            req_id=req_id,
            # 超时时不知道尝试到哪个 source，用最先尝试的候选源近似（见 _first_candidate_source）
            source=_first_candidate_source(payload.get("req_type", "unknown")),
            error_type="timeout",
            error_message=message,
        )
        provenance = [
            f"[{datetime.now().isoformat()}] retrieve_data: 检索 {req_id} 超时"
            f"（超过 per_req_timeout 秒），已跳过，不阻塞其他需求"
        ]
        return {
            "retrieval_results": {req_id: result},
            "provenance": provenance,
            "retrieval_errors": [error],
        }


async def node_retrieve_data(state: SystemState) -> dict[str, Any]:
    """按数据需求清单并行执行查找，返回合并后的检索结果。

    每个需求用独立超时预算（``settings.per_req_timeout``）包裹，通过
    ``asyncio.gather`` 并发执行：单个需求超时或失败不阻塞其他需求。
    原实现曾通过 ``Send`` 做 fan-out，但 LangGraph 要求普通节点只能返回
    dict，因此改为在节点内部用 ``asyncio.gather`` 并行汇总。

    C5：当 state 设了 ``retry_req_ids``（human_review revised/unsatisfied 写入）
    时，只重跑失败 req + 新增需求（不在既有 ``retrieval_results`` 中的 req），
    成功项沿用上一轮结果，不重新检索；``retrieval_results`` 以既有结果起步，
    不再整体覆盖。未设 ``retry_req_ids``（首次运行 / validate 重试）时全部处理，
    保持原行为。
    """
    requirements = state.get("data_requirements", [])
    if not requirements:
        logger.info("retrieve.none", status="skipped", reason="no_requirements")
        return {
            "provenance": [f"[{datetime.now().isoformat()}] retrieve_data: 无数据需求，跳过查找"],
        }

    context_keywords = _extract_context_keywords(requirements)
    retry_req_ids = set(state.get("retry_req_ids") or [])
    existing = state.get("retrieval_results") or {}
    if retry_req_ids:
        # 只处理失败/新增需求；既有成功项跳过（沿用上一轮结果，不重拉）
        to_process = [
            r for r in requirements if r.req_id in retry_req_ids or r.req_id not in existing
        ]
        to_skip = [
            r for r in requirements if r.req_id not in retry_req_ids and r.req_id in existing
        ]
    else:
        to_process = requirements  # 首次运行 / validate 重试（未设 retry_req_ids）：全部处理
        to_skip = []

    retrieval_results: dict[str, RetrievalResult] = dict(existing)  # 以既有结果起步，保留成功项
    provenance: list[str] = []
    retrieval_errors: list[RetrievalError] = []
    # ② 合并各需求的检索策略规划与 LLM 调用记录（单需求超时路径不产生，取空）
    retrieval_plan: dict[str, RetrievalPlan] = {}
    llm_usage: list[dict[str, Any]] = []
    for req in to_skip:
        provenance.append(
            f"[{datetime.now().isoformat()}] retrieve_data: 沿用上一轮结果，不重拉 ({req.req_id})"
        )

    # 为每个需求构造 payload 并并行执行；gather 返回顺序与输入顺序一致，
    # 超时/成功均由 _retrieve_single_with_timeout 兜底为普通返回。
    updates = await asyncio.gather(
        *(
            _retrieve_single_with_timeout(
                {
                    "req_id": req.req_id,
                    "req_type": req.req_type.value,
                    "description": req.description,
                    "keywords": req.keywords,
                    "fallback_sources": [s.value for s in req.fallback_sources],
                    "context_keywords": context_keywords,
                    "object_name": str(getattr(req, "object_name", "") or ""),
                }
            )
            for req in to_process
        )
    )

    for update in updates:
        retrieval_results.update(update.get("retrieval_results", {}))
        provenance.extend(update.get("provenance", []))
        retrieval_errors.extend(update.get("retrieval_errors", []))
        retrieval_plan.update(update.get("retrieval_plan", {}))
        llm_usage.extend(update.get("llm_usage", []))

    return {
        "retrieval_results": retrieval_results,
        "provenance": provenance,
        "retrieval_errors": retrieval_errors,
        "retrieval_plan": retrieval_plan,
        "llm_usage": llm_usage,
    }


async def node_retrieve_single(payload: dict[str, Any]) -> dict[str, Any]:
    """单个数据需求的查找执行节点。

    按 Hermes 优先级逐个尝试候选 Adapter：search → fetch。
    首个候选源成功返回 success；非首个成功标记 is_fallback；
    全部 search 无结果返回 missing；全部抛 AdapterError 返回 error。

    Args:
        payload: Send 传递的参数字典

    Returns:
        更新 state 的字段：retrieval_results、provenance、retrieval_errors
    """
    req_id = payload["req_id"]
    req_type = payload.get("req_type", "unknown")
    description = payload.get("description", "")
    keywords = payload.get("keywords") or []
    logger.info("retrieve.start", req_id=req_id, req_type=req_type)
    # C2-fix: 用英文/中文关键词搜索，而不是整段中文长描述。
    # Adapter 的 fallback 列表多为英文 id/title，中文 description 会导致匹配失败。
    query = " ".join(str(k) for k in keywords) if keywords else description

    hermes = _get_hermes_engine()
    experience_hint = hermes.inject_experience(description, req_type)

    provenance = [f"[{datetime.now().isoformat()}] retrieve_data: 查找 {req_id} (type={req_type})"]
    if experience_hint:
        provenance.append(experience_hint)
    retrieval_errors: list[RetrievalError] = []

    start = time.monotonic()

    try:
        adapter_classes = select_adapter(DataReqType(req_type))
    except ValueError:
        adapter_classes = []
    if not adapter_classes:
        # D2: 该 req_type 无内置数据源（如 CAMERA_CALIB / TEACHING_TRAJECTORY /
        # ROBOT_CONFIG / BENCHMARK_TASK 暂未注册 Adapter）。诚实失败为 missing，
        # reason 明确「该类型暂无内置数据源」，不塞 UNKNOWN、不误报为有源但未收录
        # （后者是 AdapterCatalogError 的「有源但未收录」语义，与无源是两回事）。
        elapsed = time.monotonic() - start
        message = "该类型暂无内置数据源，未执行检索"
        logger.warning(
            "retrieve.missing",
            req_id=req_id,
            req_type=req_type,
            status="missing",
            reason=message,
            elapsed_seconds=round(elapsed, 3),
        )
        result = RetrievalResult(
            req_id=req_id,
            status="missing",
            error_message=message,
            elapsed_seconds=elapsed,
        )
        hermes.record_experience(
            task_desc=description,
            req_type=req_type,
            result_status="missing",
            sources_used=[],
            elapsed_seconds=elapsed,
        )
        return {
            "retrieval_results": {req_id: result},
            "provenance": provenance,
            "retrieval_errors": retrieval_errors,
        }
    # Hermes 动态优先级对全部候选源生效：显式传入候选源，保证优先级列表覆盖实际 Adapter。
    priority_sources = hermes.get_source_priority(
        req_type, [cls.source.value for cls in adapter_classes]
    )
    priority_index = {src: i for i, src in enumerate(priority_sources)}
    fallback_sources = payload.get("fallback_sources") or []
    fallback_index = {src: i for i, src in enumerate(fallback_sources)}
    # ② 检索策略规划（LLM 决策层）。此时 adapter_classes 必非空（空源已在 D2 路径
    # 提前返回 missing），LLM 失败返回 None 时走规则兜底：queries/源排序不变，
    # 仅 provenance 记录降级（decisions 内部已记录具体错误类型日志）。
    _start = time.monotonic()
    retrieval_plan = decisions.plan_retrieval(
        req_type=req_type,
        description=description,
        keywords=[str(k) for k in keywords],
        object_name=str(payload.get("object_name", "") or ""),
        context_keywords=[str(k) for k in (payload.get("context_keywords") or [])],
        fallback_sources=fallback_sources,
        candidate_sources=[cls.source.value for cls in adapter_classes],
    )
    llm_usage_entry = {
        "decision": "retrieval_plan",
        "req_id": req_id,
        "status": "ok" if retrieval_plan else "fallback",
        "model": settings.llm_model,
        "elapsed": round(time.monotonic() - _start, 3),
    }
    if retrieval_plan is None:
        provenance.append(
            f"[{datetime.now().isoformat()}] retrieve_data: 检索策略 LLM 降级，使用规则兜底"
        )
    # LLM 偏好源为第二优先级（fallback_sources 之后），其余源按 Hermes 优先级排序；
    # plan 为空时 llm_pref_index 为空 dict，全部取 0 并列，行为与现状完全一致。
    llm_pref_index = (
        {src: i for i, src in enumerate(retrieval_plan.preferred_sources)} if retrieval_plan else {}
    )
    # fallback_sources 顺序为第一优先级；其次 LLM 偏好源；其余源按 Hermes 优先级
    # （priority_index 越小越靠前），不在 Hermes 候选列表中的源排最后。
    sorted_adapters = sorted(
        adapter_classes,
        key=lambda cls: (
            fallback_index.get(cls.source.value, len(fallback_sources)),
            llm_pref_index.get(cls.source.value, len(llm_pref_index)),
            priority_index.get(cls.source.value, len(priority_sources)),
        ),
    )

    # C2-fix: Adapter fallback 搜索多使用单 token 匹配，直接传整句中文+英文
    # 会导致无匹配。先尝试完整 query，再逐个尝试 keyword/英文 token。
    seen: set[str] = {query.lower()}
    # ② LLM 搜索词置前（plan 为空时不产生，行为与现状一致），
    # 确定性 query/keywords 兜底追加在尾部，全程用 seen 去重。
    queries: list[str] = []
    if retrieval_plan and retrieval_plan.queries:
        for q in retrieval_plan.queries:
            q_str = str(q).strip()
            if q_str and q_str.lower() not in seen:
                seen.add(q_str.lower())
                queries.append(q_str)
    queries.append(query)
    if keywords:
        for kw in keywords:
            kw_str = str(kw).strip()
            if kw_str and kw_str.lower() not in seen:
                seen.add(kw_str.lower())
                queries.append(kw_str)

    # C1: object_name 作为额外 query token，帮助 YCB/MuJoCo 等 search 按物体名匹配
    object_name = payload.get("object_name", "") or ""
    if object_name:
        object_str = str(object_name).strip()
        if object_str and object_str.lower() not in seen:
            seen.add(object_str.lower())
            queries.append(object_str)

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
    # C2: 累积各源「清单外目标」诊断（跨 adapter 保留），用于 missing 的 error_message
    search_failures: list[str] = []

    for idx, adapter_cls in enumerate(sorted_adapters):
        is_fallback = idx > 0
        last_source = adapter_cls.source.value
        try:
            # ponytail: type[BaseAdapter] 的 __init__ 签名包含 base_url，但各子类均为无参构造；
            # mypy 无法推导子类重载，此处忽略构造参数检查。
            adapter = adapter_cls()  # type: ignore[call-arg]
            search_results: list[SearchResult] = []
            for q in queries:
                try:
                    search_results = await adapter.search(q)
                except AdapterCatalogError as exc:
                    # C2: 清单外目标——收集可诊断语义，继续尝试剩余 query（如物体名）
                    search_failures.append(f"{adapter_cls.source.value}: {exc.message}")
                    continue
                if search_results:
                    break
            if not search_results:
                had_empty_search = True
                continue
            # C1: object_name 为 GraspNet/DexGrasp 扩展参数，优先整包透传；
            # 旧 Adapter 不接受时逐级降级到 req_type / 无参签名。
            fetch_kwargs: dict[str, Any] = {"req_type": DataReqType(req_type)}
            if object_name:
                fetch_kwargs["object_name"] = object_name
            try:
                raw = await adapter.fetch(search_results[0].item_id, **fetch_kwargs)
            except TypeError:
                try:
                    raw = await adapter.fetch(
                        search_results[0].item_id, req_type=DataReqType(req_type)
                    )
                except TypeError:
                    # 兼容旧 Adapter 的 fetch(item_id) 签名
                    raw = await adapter.fetch(search_results[0].item_id)
            elapsed = time.monotonic() - start
            logger.info(
                "retrieve.success",
                req_id=req_id,
                req_type=req_type,
                status="success",
                source=raw.source.value,
                is_fallback=is_fallback,
                elapsed_seconds=round(elapsed, 3),
            )
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
                "retrieval_errors": retrieval_errors,
                "retrieval_plan": {req_id: retrieval_plan} if retrieval_plan else {},
                "llm_usage": [llm_usage_entry] if llm_usage_entry else [],
            }
        except AdapterError as exc:
            retrieval_errors.append(_to_retrieval_error(req_id, adapter_cls.source, exc))
            continue

    elapsed = time.monotonic() - start
    if had_empty_search:
        status = "missing"
        error_message = "；".join(search_failures)
    else:
        status = "error"
        error_message = "所有候选源均失败: " + "; ".join(
            f"{e.source.value}:{e.error_type}" for e in retrieval_errors
        )
    if status == "missing":
        logger.warning(
            "retrieve.missing",
            req_id=req_id,
            req_type=req_type,
            status=status,
            reason=error_message or "no_result",
            elapsed_seconds=round(elapsed, 3),
        )
    else:
        logger.error(
            "retrieve.error",
            req_id=req_id,
            req_type=req_type,
            status=status,
            error_types=[e.error_type for e in retrieval_errors],
            elapsed_seconds=round(elapsed, 3),
        )
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
        "retrieval_errors": retrieval_errors,
        "retrieval_plan": {req_id: retrieval_plan} if retrieval_plan else {},
        "llm_usage": [llm_usage_entry] if llm_usage_entry else [],
    }
