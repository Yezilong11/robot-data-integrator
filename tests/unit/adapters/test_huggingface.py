# tests/unit/adapters/test_huggingface.py
"""HuggingFaceAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.huggingface import HuggingFaceAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestHuggingFaceAdapter:
    """HuggingFaceAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.source == DataSource.HUGGINGFACE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.base_url == "https://huggingface.co/api"

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
