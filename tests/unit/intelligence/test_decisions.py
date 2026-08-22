# tests/unit/intelligence/test_decisions.py
"""LLM 决策层 decisions 模块单元测试。

覆盖四个决策函数：
- 正常路径：返回对应 schema 实例、字段值正确；
- LLMUnavailableError / LLMParseError：返回 None 且不抛异常（降级）；
- 降级路径记录 warning 日志。
"""

from typing import Any

import pytest

from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.intelligence import decisions
from rdi.intelligence.schemas import (
    QualityExplanation,
    RetrievalPlan,
    ReviewSuggestions,
    SemanticConvention,
)


class _FakeLLMClient:
    """模拟 LLMClient：按请求 schema 返回预置实例，或抛出注入异常。"""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc
        self.calls: list[tuple[str, type, str | None]] = []

    def call_structured(self, prompt: str, schema: type, system: str | None = None) -> Any:
        self.calls.append((prompt, schema, system))
        if self._exc is not None:
            raise self._exc
        if schema is RetrievalPlan:
            return RetrievalPlan(
                queries=["Franka Panda URDF", "YCB banana grasp"],
                preferred_sources=["github", "franka"],
                reason="测试检索理由",
                confidence=0.9,
            )
        if schema is SemanticConvention:
            return SemanticConvention(
                dataset_name="test_dataset",
                semantic_type="grasp_pose",
                rotation="quaternion_wxyz",
                origin="camera",
                unit="millimeter",
                field_map={"rot": "orientation"},
                confidence=0.8,
            )
        if schema is QualityExplanation:
            return QualityExplanation(
                summary="数据整体可用",
                strengths=["字段完整"],
                risks=["置信度偏低"],
                recommendations=["补充更多样本"],
                usage_guidance="仅用于演示实验",
                confidence=0.7,
            )
        return ReviewSuggestions(
            verdict="revised",
            issues=["缺失 grasp 数据"],
            rationale="关键项缺失需修正",
            confidence=0.6,
        )


def _patch_llm(monkeypatch: pytest.MonkeyPatch, fake: _FakeLLMClient) -> None:
    monkeypatch.setattr(decisions, "_get_llm_client", lambda: fake)


# ─── 正常路径 ───


def test_plan_retrieval_returns_retrieval_plan(monkeypatch: pytest.MonkeyPatch) -> None:
    """plan_retrieval：返回 RetrievalPlan 且字段值正确、入参拼入 prompt。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    result = decisions.plan_retrieval(
        req_type="grasp",
        description="YCB banana 的抓取姿态数据",
        keywords=["grasp", "抓取姿态"],
        object_name="banana",
        context_keywords=["YCB"],
        fallback_sources=["graspnet"],
        candidate_sources=["graspnet", "dexgrasp"],
    )
    assert isinstance(result, RetrievalPlan)
    assert result.queries == ["Franka Panda URDF", "YCB banana grasp"]
    assert result.preferred_sources == ["github", "franka"]
    assert result.reason == "测试检索理由"
    assert result.confidence == 0.9
    prompt, schema, system = fake.calls[0]
    assert "banana" in prompt and "graspnet" in prompt
    assert schema is RetrievalPlan
    assert system == decisions.RETRIEVAL_PLAN_SYSTEM_PROMPT


def test_unify_semantics_returns_semantic_convention(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unify_semantics：返回 SemanticConvention 且字段值正确。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    result = decisions.unify_semantics(
        dataset_name="test_dataset",
        field_names=["rot", "pos"],
        dtypes={"rot": "float32"},
        sample_values={"rot": "[0.1,0.2,0.3,0.9]"},
        expected_fields=["position", "orientation"],
    )
    assert isinstance(result, SemanticConvention)
    assert result.dataset_name == "test_dataset"
    assert result.semantic_type == "grasp_pose"
    assert result.rotation == "quaternion_wxyz"
    assert result.origin == "camera"
    assert result.unit == "millimeter"
    assert result.field_map == {"rot": "orientation"}
    assert result.confidence == 0.8
    assert fake.calls[0][1] is SemanticConvention


def test_explain_quality_returns_quality_explanation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """explain_quality：返回 QualityExplanation 且字段值正确。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    result = decisions.explain_quality(
        total_requirements=3,
        fulfilled=2,
        missing=1,
        validation_issues=["位置字段缺失"],
        avg_confidence=0.8,
        avg_completeness=0.7,
        manifest_summary="2/3 需求已满足",
    )
    assert isinstance(result, QualityExplanation)
    assert result.summary == "数据整体可用"
    assert result.strengths == ["字段完整"]
    assert result.risks == ["置信度偏低"]
    assert result.recommendations == ["补充更多样本"]
    assert result.usage_guidance == "仅用于演示实验"
    assert result.confidence == 0.7
    prompt, schema, _ = fake.calls[0]
    assert "位置字段缺失" in prompt
    assert schema is QualityExplanation


def test_explain_quality_prompt_contains_undownloaded_items(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 9：传入未下载项清单时，prompt 包含每项路径/URL/大小/原因/wget/download_guide。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    items = [
        {
            "path": "resources/req_big.json",
            "file_url": "https://example.com/big.tar",
            "file_size": 12345,
            "reason": "体积超限",
            "wget": "wget https://example.com/big.tar -O big.tar",
            "download_guide": {"status": "not_downloaded", "method_hint": "wget ..."},
        }
    ]
    result = decisions.explain_quality(
        total_requirements=3,
        fulfilled=2,
        missing=1,
        validation_issues=["v"],
        avg_confidence=0.8,
        avg_completeness=0.7,
        manifest_summary="s",
        undownloaded_items=items,
    )
    assert isinstance(result, QualityExplanation)
    prompt, schema, _ = fake.calls[0]
    assert "未下载项清单" in prompt
    assert "https://example.com/big.tar" in prompt
    assert "体积超限" in prompt
    assert "resources/req_big.json" in prompt
    assert schema is QualityExplanation
    # 不传清单时 prompt 不含该上下文（行为不回归）
    fake2 = _FakeLLMClient()
    _patch_llm(monkeypatch, fake2)
    decisions.explain_quality(
        total_requirements=1,
        fulfilled=1,
        missing=0,
        validation_issues=[],
        avg_confidence=1.0,
        avg_completeness=1.0,
        manifest_summary="s",
    )
    assert "未下载项清单" not in fake2.calls[0][0]


def test_suggest_review_returns_review_suggestions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """suggest_review：返回 ReviewSuggestions 且字段值正确。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    result = decisions.suggest_review(
        quality_summary="基本可用",
        missing_items=["grasp 数据"],
        validation_issues=["完整度不足"],
        retrieval_errors=["graspnet 超时"],
        revision_history=["第 1 轮修订"],
    )
    assert isinstance(result, ReviewSuggestions)
    assert result.verdict == "revised"
    assert result.issues == ["缺失 grasp 数据"]
    assert result.rationale == "关键项缺失需修正"
    assert result.confidence == 0.6
    prompt, schema, system = fake.calls[0]
    assert "graspnet 超时" in prompt
    assert schema is ReviewSuggestions
    assert system == decisions.REVIEW_SUGGESTIONS_SYSTEM_PROMPT


# ─── 降级路径（LLM 失败返回 None，绝不抛异常） ───

_FUNC_ARGS: dict[str, dict[str, Any]] = {
    "plan_retrieval": dict(
        req_type="grasp",
        description="d",
        keywords=["k"],
        object_name="o",
        context_keywords=["c"],
        fallback_sources=["f"],
        candidate_sources=["c"],
    ),
    "unify_semantics": dict(
        dataset_name="ds",
        field_names=["a"],
        dtypes={"a": "float32"},
        sample_values={"a": "1.0"},
        expected_fields=["position"],
    ),
    "explain_quality": dict(
        total_requirements=3,
        fulfilled=2,
        missing=1,
        validation_issues=["v"],
        avg_confidence=0.8,
        avg_completeness=0.7,
        manifest_summary="s",
    ),
    "suggest_review": dict(
        quality_summary="s",
        missing_items=["m"],
        validation_issues=["v"],
        retrieval_errors=["r"],
        revision_history=["h"],
    ),
}


@pytest.mark.parametrize("name", sorted(_FUNC_ARGS))
def test_llm_unavailable_returns_none(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMUnavailableError：返回 None 且不抛异常。"""
    fake = _FakeLLMClient(exc=LLMUnavailableError("LLM 不可用", model="test"))
    _patch_llm(monkeypatch, fake)
    result = getattr(decisions, name)(**_FUNC_ARGS[name])
    assert result is None


@pytest.mark.parametrize("name", sorted(_FUNC_ARGS))
def test_llm_parse_error_returns_none(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    """LLMParseError：返回 None 且不抛异常。"""
    fake = _FakeLLMClient(exc=LLMParseError("JSON 不符合 schema", model="test"))
    _patch_llm(monkeypatch, fake)
    result = getattr(decisions, name)(**_FUNC_ARGS[name])
    assert result is None


# ─── 日志 ───


class _Recorder:
    """记录结构化日志事件的替身 logger。"""

    def __init__(self) -> None:
        self.records: list[tuple[str, dict[str, Any]]] = []

    def info(self, event: str, **kw: Any) -> None:
        self.records.append((event, dict(kw)))

    def warning(self, event: str, **kw: Any) -> None:
        self.records.append((event, dict(kw)))


def test_fallback_logs_warning(monkeypatch: pytest.MonkeyPatch) -> None:
    """降级路径记录 warning：事件名为 llm_decision.* 且 status=fallback。"""
    fake = _FakeLLMClient(exc=LLMUnavailableError("LLM 不可用", model="test"))
    _patch_llm(monkeypatch, fake)
    recorder = _Recorder()
    monkeypatch.setattr(decisions, "logger", recorder)
    result = decisions.plan_retrieval(
        req_type="grasp",
        description="d",
        keywords=["k"],
        object_name="o",
        context_keywords=[],
        fallback_sources=["graspnet"],
        candidate_sources=["graspnet"],
    )
    assert result is None
    assert any(
        event == "llm_decision.plan_retrieval"
        and kw.get("status") == "fallback"
        and kw.get("error_type") == "LLMUnavailableError"
        for event, kw in recorder.records
    )
