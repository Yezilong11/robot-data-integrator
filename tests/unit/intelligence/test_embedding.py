# tests/unit/intelligence/test_embedding.py
"""EmbeddingClient 单元测试。

使用 respx mock OpenAI 兼容的 ``/embeddings`` 端点，覆盖成功调用、API 失败、
便捷函数 ``get_embedding`` 三条路径。
"""

import httpx
import pytest
import respx

from rdi.config import settings
from rdi.exceptions import LLMUnavailableError
from rdi.intelligence import embedding as emb_module
from rdi.intelligence.embedding import EmbeddingClient, get_embedding

BASE_URL = "https://test.example.com/v1"
EMBEDDINGS_URL = f"{BASE_URL}/embeddings"


def _make_client() -> EmbeddingClient:
    """构造测试用 EmbeddingClient，显式传参避免依赖真实 settings。"""
    return EmbeddingClient(
        api_key="test-key",
        base_url=BASE_URL,
        model="test-model",
    )


def _ok_response() -> httpx.Response:
    """OpenAI 标准 200 embedding 响应。"""
    return httpx.Response(
        200,
        json={
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
            "model": "test-model",
            "usage": {},
        },
    )


def _err_response() -> httpx.Response:
    """OpenAI 标准 500 错误响应。"""
    return httpx.Response(500, json={"error": {"message": "server error"}})


def test_embed_success() -> None:
    """mock 200 响应，embed 返回预期向量。"""
    with respx.mock:
        respx.post(EMBEDDINGS_URL).mock(return_value=_ok_response())
        client = _make_client()
        assert client.embed("hello") == [0.1, 0.2, 0.3]


def test_embed_api_failure_raises() -> None:
    """mock 500 响应，embed 抛 LLMUnavailableError，含 model 名。"""
    with respx.mock:
        respx.post(EMBEDDINGS_URL).mock(return_value=_err_response())
        client = _make_client()
        with pytest.raises(LLMUnavailableError) as exc_info:
            client.embed("hello")
        assert exc_info.value.model == "test-model"


def test_get_embedding_uses_singleton(monkeypatch: pytest.MonkeyPatch) -> None:
    """get_embedding 走懒加载单例：首次调用创建 client，后续复用同一实例。"""
    # 重置单例 + patch settings 让构造使用测试 URL（避免依赖真实环境）
    monkeypatch.setattr(emb_module, "_embedding_client", None)
    monkeypatch.setattr(settings, "llm_api_key", "test-key")
    monkeypatch.setattr(settings, "llm_base_url", BASE_URL)
    monkeypatch.setattr(settings, "llm_embedding_model", "test-model")
    with respx.mock:
        respx.post(EMBEDDINGS_URL).mock(return_value=_ok_response())
        result = get_embedding("hello")
        assert result == [0.1, 0.2, 0.3]
        # 单例已创建
        assert emb_module._embedding_client is not None
        # 第二次调用复用同一实例
        before = emb_module._embedding_client
        respx.post(EMBEDDINGS_URL).mock(return_value=_ok_response())
        get_embedding("world")
        assert emb_module._embedding_client is before


def test_local_hash_embedding_is_deterministic() -> None:
    """Local mode supports providers such as DeepSeek without embeddings API."""
    client = EmbeddingClient(api_key="", base_url="", model="local-hash")
    first = client.embed("hello")
    assert first == client.embed("hello")
    assert first != client.embed("world")
    assert len(first) == 32
