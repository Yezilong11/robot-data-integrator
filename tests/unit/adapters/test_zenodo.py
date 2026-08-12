# tests/unit/adapters/test_zenodo.py
"""ZenodoAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.zenodo import ZenodoAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestZenodoAdapter:
    """ZenodoAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = ZenodoAdapter()
        assert adapter.source == DataSource.ZENODO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = ZenodoAdapter()
        assert adapter.base_url == "https://zenodo.org/api"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = ZenodoAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = ZenodoAdapter()
        adapter.max_retry = 1
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=AdapterError("fail", source="zenodo"),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("robot grasp dataset")
            assert exc_info.value.source == "zenodo"

    @pytest.mark.asyncio
    async def test_zenodo_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回记录列表。"""
        adapter = ZenodoAdapter()
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "id": 12345,
                        "title": "Robot Grasp Dataset",
                        "doi": "10.1234/test",
                        "links": {"self_html": "https://zenodo.org/records/12345"},
                        "created": "2024-01-01",
                    }
                ]
            }
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("robot grasp dataset")
            assert len(results) > 0
            assert results[0].source == DataSource.ZENODO
            assert results[0].item_id == "12345"
            assert results[0].title == "Robot Grasp Dataset"

    @pytest.mark.asyncio
    async def test_zenodo_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = ZenodoAdapter()
        mock_response = {
            "id": 12345,
            "title": "Robot Grasp Dataset",
            "doi": "10.1234/test",
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            raw = await adapter.fetch("12345")
            assert raw.source == DataSource.ZENODO
            assert raw.item_id == "12345"
            assert raw.format == "json"
            assert raw.size_bytes > 0
