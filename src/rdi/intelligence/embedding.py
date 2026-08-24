# src/rdi/intelligence/embedding.py
"""OpenAI 兼容 Embedding 客户端封装。

与 ``client.LLMClient`` 同构：构造函数从 ``settings`` 读默认值，支持显式传参
覆盖；SDK 内置重试已关闭（``max_retries=0``）。API 失败统一抛
``LLMUnavailableError``，不做重试（调用方按需自行处理）。
"""

import hashlib

from openai import OpenAI, OpenAIError

from rdi.config import settings
from rdi.exceptions import LLMUnavailableError


class EmbeddingClient:
    """OpenAI 兼容 Embedding 客户端。

    通过 ``settings.llm_base_url`` 切换厂商，``settings.llm_embedding_model``
    指定模型，对外提供 ``embed`` 方法。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> None:
        # 允许显式传入覆盖 settings（便于测试）
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._base_url = base_url if base_url is not None else settings.llm_base_url
        self._model = model if model is not None else settings.llm_embedding_model
        self._local = self._model.lower() in {"local", "local-hash", "deterministic"}
        if self._local:
            self._api_key = "local"
            self._base_url = ""
            self._client = None
            return
        if not self._api_key:
            raise LLMUnavailableError(
                "LLM API Key 未配置（settings.llm_api_key 为空，请检查 .env 的 LLM_API_KEY）",
                model=self._model,
                retry_count=0,
            )
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=0,
        )

    def embed(self, text: str) -> list[float]:
        """返回单条文本的 embedding 向量。

        任何 ``OpenAIError`` 子类视为不可用，抛 ``LLMUnavailableError``（含
        model 名），不重试。
        """
        if self._local:
            # DeepSeek exposes chat completions but no embeddings endpoint. A
            # deterministic local vector keeps Hermes usable without claiming
            # semantic quality from a remote model.
            digest = hashlib.sha256(text.encode("utf-8")).digest()
            return [((byte / 255.0) * 2.0) - 1.0 for byte in digest]
        try:
            response = self._client.embeddings.create(
                model=self._model,
                input=text,
            )
            return list(response.data[0].embedding)
        except OpenAIError as e:
            raise LLMUnavailableError(
                f"Embedding 调用失败: {e}",
                model=self._model,
                retry_count=0,
            ) from e


# 模块级懒加载单例，便于测试 monkeypatch（与 parse_goal._get_llm_client 同构）
_embedding_client: EmbeddingClient | None = None


def get_embedding(text: str) -> list[float]:
    """便捷函数：用懒加载单例 ``EmbeddingClient`` 计算单条文本的向量。"""
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = EmbeddingClient()
    return _embedding_client.embed(text)
