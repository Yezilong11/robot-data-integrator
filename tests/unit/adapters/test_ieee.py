# tests/unit/adapters/test_ieee.py
"""IEEEXploreAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.ieee import IEEEXploreAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestIEEEXploreAdapter:
    """IEEEXploreAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = IEEEXploreAdapter()
        assert adapter.source == DataSource.IEEE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = IEEEXploreAdapter()
        assert adapter.base_url == "https://ieeexploreapi.ieee.org/api/v1/search"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = IEEEXploreAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_raises_error_without_api_key(self) -> None:
        """异常情况：API Key 未配置时抛出 AdapterError。"""
        adapter = IEEEXploreAdapter()
        adapter.api_key = ""
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "ieee"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = IEEEXploreAdapter()
        adapter.api_key = "test-key"
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "ieee"

    @pytest.mark.asyncio
    async def test_ieee_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回论文列表。"""
        adapter = IEEEXploreAdapter()
        adapter.api_key = "test-key"
        mock_response = {
            "results": [
                {
                    "article": {
                        "article_number": "12345",
                        "title": "Robot Grasping Survey",
                        "doi": "10.1109/test",
                        "publication_year": "2024",
                        "authors": {"authors": [{"full_name": "Alice Smith"}]},
                    }
                }
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("robot grasping")
            assert len(results) > 0
            assert results[0].source == DataSource.IEEE
            assert results[0].item_id == "12345"
            assert results[0].title == "Robot Grasping Survey"

    @pytest.mark.asyncio
    async def test_ieee_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = IEEEXploreAdapter()
        adapter.api_key = "test-key"
        mock_response = {
            "results": [
                {
                    "article": {
                        "article_number": "12345",
                        "title": "Robot Grasping Survey",
                        "doi": "10.1109/test",
                        "publication_year": "2024",
                        "authors": {"authors": [{"full_name": "Alice Smith"}]},
                    }
                }
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            raw = await adapter.fetch("12345")
            assert raw.source == DataSource.IEEE
            assert raw.item_id == "12345"
            assert raw.format == "json"
            assert raw.size_bytes > 0
