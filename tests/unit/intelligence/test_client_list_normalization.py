# tests/unit/intelligence/test_client_list_normalization.py
"""P1-C：LLM list[str] 字段字符串输出归一化（逗号/顿号/分号拆分重试）测试。"""

import json
from unittest.mock import patch

import pytest
from pydantic import BaseModel

from rdi.exceptions import LLMParseError
from rdi.intelligence.client import LLMClient

BASE_URL = "https://test.example.com/v1"


class _HasList(BaseModel):
    """含 list[str] 字段的 schema 桩。"""

    keywords: list[str]
    name: str


class _HasIntList(BaseModel):
    """非 list[str]（list[int]）字段不受归一化影响。"""

    indices: list[int]


def _client() -> LLMClient:
    return LLMClient(api_key="test-key", base_url=BASE_URL, model="qwen-max")


def test_split_list_fields_splits_comma_string() -> None:
    """qwen-max 逗号字符串 → 数组归一化后可通过 schema 校验。"""
    raw = json.dumps({"keywords": "apple,banana", "name": "banana"})
    normalized = LLMClient._split_list_fields(raw, _HasList)
    assert normalized is not None
    obj = json.loads(normalized)
    assert obj["keywords"] == ["apple", "banana"]
    assert obj["name"] == "banana"
    parsed = _HasList.model_validate_json(normalized)
    assert parsed.keywords == ["apple", "banana"]


def test_split_handles_fullwidth_and_list_delimiters() -> None:
    """中文全角逗号/顿号/分号/空白均按分隔符拆分。"""
    raw = json.dumps({"keywords": "苹果，香蕉、马克杯;mug", "name": "mug"})
    normalized = LLMClient._split_list_fields(raw, _HasList)
    assert normalized is not None
    assert json.loads(normalized)["keywords"] == ["苹果", "香蕉", "马克杯", "mug"]


def test_split_returns_none_when_already_list() -> None:
    """字段已是数组时不改动（返回 None，走正常路径）。"""
    raw = json.dumps({"keywords": ["apple"], "name": "apple"})
    assert LLMClient._split_list_fields(raw, _HasList) is None


def test_split_ignores_non_str_list_fields() -> None:
    """list[int] 字段为字符串时不拆分（避免无意义的类型强转）。"""
    raw = json.dumps({"indices": "1,2,3"})
    assert LLMClient._split_list_fields(raw, _HasIntList) is None


def test_call_structured_normalizes_and_returns_instance() -> None:
    """端到端：LLM 返回逗号字符串时 call_structured 归一化后成功返回模型实例。"""
    client = _client()
    raw = json.dumps({"keywords": "apple,banana", "name": "banana"})
    with patch.object(client, "_invoke_with_retry", return_value=raw) as mock_call:
        out = client.call_structured("测试", _HasList)
    mock_call.assert_called_once()
    assert out.name == "banana"
    assert out.keywords == ["apple", "banana"]


def test_unfixable_fields_still_raise_llm_parse_error() -> None:
    """归一化后仍不符合 schema（缺 name 字段）→ 原降级 LLMParseError。"""
    client = _client()
    raw = json.dumps({"keywords": "apple,banana"})  # 缺 name
    with patch.object(client, "_invoke_with_retry", return_value=raw), pytest.raises(LLMParseError):
        client.call_structured("测试", _HasList)
