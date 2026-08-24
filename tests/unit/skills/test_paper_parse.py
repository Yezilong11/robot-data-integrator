"""PaperSkill 测试：重点覆盖 fetch 层显式降级（fmt=json）的消费路径。

Day2 回归：arxiv fetch 下载到损坏 PDF 时显式降级返回 metadata JSON，
PaperSkill 此前忽略 fmt 仍把 JSON 字节当 PDF 打开（"Failed to open stream"）。
"""

import json

import pytest

from rdi.models.common import Severity, StandardResult
from rdi.skills.paper_parse import PaperSkill

_META = {
    "arxiv_id": "2304.06524",
    "title": "Dexterous Grasping",
    "url": "https://arxiv.org/abs/2304.06524",
    "download_hint": "https://arxiv.org/pdf/2304.06524.pdf",
    "size": 123456,
}


@pytest.fixture
def skill() -> PaperSkill:
    return PaperSkill()


def test_process_json_fallback_returns_usable_result(skill: PaperSkill) -> None:
    """fmt=json：metadata JSON 装配为可用结果并标记 is_fallback。"""
    res = skill.process(json.dumps(_META).encode("utf-8"), fmt="json")
    assert res.success is True
    assert res.canonical_format == "json"
    assert res.is_fallback is True
    assert res.completeness_pct == 60.0
    assert res.data["text"] == ""
    assert res.data["metadata"]["arxiv_id"] == "2304.06524"
    assert any("降级" in w for w in res.warnings)


def test_process_json_invalid_returns_failure(skill: PaperSkill) -> None:
    """fmt=json 但字节不是合法 JSON：失败而非当 PDF 打开。"""
    res = skill.process(b"not-json-at-all", fmt="json")
    assert res.success is False
    assert "JSON" in res.errors[0]


def test_validate_accepts_fallback_metadata(skill: PaperSkill) -> None:
    """降级结果没有全文 text / page_count，validate 不应判错。"""
    res = skill.process(json.dumps(_META).encode("utf-8"), fmt="json")
    report = skill.validate(res)
    assert report.is_valid is True


def test_validate_rejects_empty_text_without_fallback(skill: PaperSkill) -> None:
    """非降级路径：空文本仍按错误处理（原有行为不变）。"""
    res = StandardResult(
        success=True,
        canonical_format="text",
        data={"text": "", "metadata": {}},
    )
    report = skill.validate(res)
    assert report.is_valid is False
    assert any(i.severity == Severity.ERROR for i in report.issues)
