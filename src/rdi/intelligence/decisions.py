# src/rdi/intelligence/decisions.py
"""LLM 智能决策层：检索规划 / 语义统一 / 质量解释 / 审查建议。

四个决策函数均为纯函数：LLM 失败（不可用 / 解析失败）时返回 None，
绝不抛异常、绝不中断上层流程（降级模式与 human_review 节点一致）。
"""

import json
import time
from typing import TypeVar

from pydantic import BaseModel

from rdi.config import settings
from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.intelligence import LLMClient
from rdi.intelligence.prompts.quality_explanation import QUALITY_EXPLANATION_SYSTEM_PROMPT
from rdi.intelligence.prompts.retrieval_plan import RETRIEVAL_PLAN_SYSTEM_PROMPT
from rdi.intelligence.prompts.review_suggestions import REVIEW_SUGGESTIONS_SYSTEM_PROMPT
from rdi.intelligence.prompts.semantic_unification import SEMANTIC_UNIFICATION_SYSTEM_PROMPT
from rdi.intelligence.schemas import (
    QualityExplanation,
    RetrievalPlan,
    ReviewSuggestions,
    SemanticConvention,
)
from rdi.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T", bound=BaseModel)

# 模块级懒加载 LLMClient 单例，便于测试 monkeypatch
_llm_client: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    """返回缓存的 LLMClient 单例；首次调用时创建。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def _fmt_list(items: list[str]) -> str:
    """列表转提示词文本，空列表显示占位。"""
    return "、".join(items) if items else "（无）"


def _call_decision(name: str, prompt: str, schema: type[T], system: str) -> T | None:
    """调用 LLM 结构化输出并统一记录调用日志。

    LLM 不可用 / 解析失败时记录 warning 并返回 None，绝不抛异常。
    """
    start = time.monotonic()
    try:
        result = _get_llm_client().call_structured(
            prompt=prompt,
            schema=schema,
            system=system,
        )
        logger.info(
            f"llm_decision.{name}",
            model=settings.llm_model,
            status="ok",
            elapsed=round((time.monotonic() - start) * 1000, 1),
        )
        return result
    except (LLMUnavailableError, LLMParseError) as e:
        logger.warning(
            f"llm_decision.{name}",
            status="fallback",
            error_type=type(e).__name__,
            reason=str(e),
        )
        return None


def plan_retrieval(
    *,
    req_type: str,
    description: str,
    keywords: list[str],
    object_name: str,
    context_keywords: list[str],
    fallback_sources: list[str],
    candidate_sources: list[str],
) -> RetrievalPlan | None:
    """生成检索策略规划（搜索词组合 / 源偏好 / 理由）。

    LLM 失败返回 None，由上层使用 fallback 数据源兜底。
    """
    prompt = (
        f"需求类型：{req_type}\n"
        f"需求描述：{description}\n"
        f"关键词：{_fmt_list(keywords)}\n"
        f"目标物体：{object_name}\n"
        f"上下文关键词：{_fmt_list(context_keywords)}\n"
        f"备选数据源：{_fmt_list(fallback_sources)}\n"
        f"候选数据源：{_fmt_list(candidate_sources)}\n\n"
        "请根据以上输入，按照 schema 输出检索规划（严格 JSON）。"
    )
    return _call_decision("plan_retrieval", prompt, RetrievalPlan, RETRIEVAL_PLAN_SYSTEM_PROMPT)


def unify_semantics(
    *,
    dataset_name: str,
    field_names: list[str],
    dtypes: dict[str, str],
    sample_values: dict[str, str],
    expected_fields: list[str],
) -> SemanticConvention | None:
    """识别未知数据集的抓取数据语义（字段映射 / 旋转 / 坐标系 / 单位）。

    LLM 失败返回 None，由上层退回默认语义约定。
    """
    prompt = (
        f"数据集名称：{dataset_name}\n"
        f"字段名列表：{_fmt_list(field_names)}\n"
        f"字段类型：{json.dumps(dtypes, ensure_ascii=False)}\n"
        f"样本值：{json.dumps(sample_values, ensure_ascii=False)}\n"
        f"期望字段：{_fmt_list(expected_fields)}\n\n"
        "请根据以上输入，按照 schema 输出语义约定（严格 JSON）。"
    )
    return _call_decision(
        "unify_semantics", prompt, SemanticConvention, SEMANTIC_UNIFICATION_SYSTEM_PROMPT
    )


def explain_quality(
    *,
    total_requirements: int,
    fulfilled: int,
    missing: int,
    validation_issues: list[str],
    avg_confidence: float,
    avg_completeness: float,
    manifest_summary: str,
) -> QualityExplanation | None:
    """基于质量报告数字生成自然语言质量解释。

    LLM 失败返回 None，由上层省略解释或使用规则模板。
    """
    prompt = (
        f"需求总数：{total_requirements}\n"
        f"已满足：{fulfilled}\n"
        f"缺失：{missing}\n"
        f"校验问题：{_fmt_list(validation_issues)}\n"
        f"平均置信度：{avg_confidence}\n"
        f"平均完整度：{avg_completeness}\n"
        f"manifest 摘要：{manifest_summary}\n\n"
        "请根据以上输入，按照 schema 输出质量解释（严格 JSON）。"
    )
    return _call_decision(
        "explain_quality", prompt, QualityExplanation, QUALITY_EXPLANATION_SYSTEM_PROMPT
    )


def suggest_review(
    *,
    quality_summary: str,
    missing_items: list[str],
    validation_issues: list[str],
    retrieval_errors: list[str],
    revision_history: list[str],
) -> ReviewSuggestions | None:
    """基于缺失项 / 校验问题给出审查建议。

    LLM 失败返回 None，由上层退回默认 satisfied 决策。
    """
    prompt = (
        f"质量摘要：{quality_summary}\n"
        f"缺失项：{_fmt_list(missing_items)}\n"
        f"校验问题：{_fmt_list(validation_issues)}\n"
        f"检索错误：{_fmt_list(retrieval_errors)}\n"
        f"修订历史：{_fmt_list(revision_history)}\n\n"
        "请根据以上输入，按照 schema 输出审查建议（严格 JSON）。"
    )
    return _call_decision(
        "suggest_review", prompt, ReviewSuggestions, REVIEW_SUGGESTIONS_SYSTEM_PROMPT
    )
