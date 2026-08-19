# tests/unit/adapters/test_huggingface.py
"""HuggingFaceAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.huggingface import HuggingFaceAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestHuggingFaceAdapter:
    """HuggingFaceAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.source == DataSource.HUGGINGFACE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 与配置一致（国内环境走 hf-mirror 镜像）。"""
        adapter = HuggingFaceAdapter()
        assert adapter.base_url == settings.huggingface_api_url

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = HuggingFaceAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = HuggingFaceAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "huggingface"

    @pytest.mark.asyncio
    async def test_huggingface_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回模型列表。"""
        adapter = HuggingFaceAdapter()
        mock_response = [
            {
                "id": "bert-base-uncased",
                "modelId": "bert-base-uncased",
                "downloads": 1000,
                "likes": 50,
                "tags": ["transformers"],
            }
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("bert")
            assert len(results) > 0
            assert results[0].source == DataSource.HUGGINGFACE
            assert results[0].item_id == "bert-base-uncased"
            assert results[0].metadata["downloads"] == 1000

    @pytest.mark.asyncio
    async def test_huggingface_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert"}'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_config
        ):
            raw = await adapter.fetch("bert-base-uncased")
            assert raw.source == DataSource.HUGGINGFACE
            assert raw.item_id == "bert-base-uncased"
            assert raw.format == "json"
            assert raw.size_bytes > 0

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_uses_model_info(self) -> None:
        """POLICY_MODEL 类型：fetch 拉取 model_info.json 而非默认 config.json。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        fake_model_info = b'{"modelId": "lerobot/act_aloha", "tags": ["policy"]}'
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return fake_model_info

        with patch.object(adapter, "_download_bytes", side_effect=_fake_download):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert any("model_info.json" in u for u in called_urls)
            assert not any("config.json" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_huggingface_fetch_default_uses_config(self) -> None:
        """默认类型（非 POLICY_MODEL）：仍拉取 config.json（不回归）。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert"}'
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return fake_config

        with patch.object(adapter, "_download_bytes", side_effect=_fake_download):
            raw = await adapter.fetch("bert-base-uncased")
            assert raw.format == "json"
            assert any("config.json" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_invalid_json_fallback(self) -> None:
        """POLICY_MODEL：model_info.json 404 → 降级 config.json → metadata 引用（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        responses = {
            "model_info.json": b"<html>404</html>",
            "config.json": b'{"model_type": "act"}',
        }

        async def _fake_download(url: str) -> bytes:
            for name, body in responses.items():
                if name in url:
                    return body
            raise RuntimeError(f"unexpected url: {url}")

        with patch.object(adapter, "_download_bytes", side_effect=_fake_download):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert b"model_type" in raw.data or b"model_id" in raw.data

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_all_fail_returns_meta(self) -> None:
        """POLICY_MODEL：model_info.json 与 config.json 均不可用 → 返回 metadata 引用（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, side_effect=RuntimeError("boom")
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert b"model_id" in raw.data
