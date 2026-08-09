# tests/unit/adapters/test_google_scanned.py
"""GoogleScannedAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.google_scanned import GoogleScannedAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestGoogleScannedAdapter:
    """GoogleScannedAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = GoogleScannedAdapter()
        assert adapter.source == DataSource.GOOGLE_SCANNED

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = GoogleScannedAdapter()
        assert adapter.base_url == "https://fuel.gazebosim.org/1.0/GoogleResearch"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = GoogleScannedAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = GoogleScannedAdapter()
        adapter.max_retry = 1
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=AdapterError("fail", source="google_scanned"),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("mug")
            assert exc_info.value.source == "google_scanned"

    @pytest.mark.asyncio
    async def test_google_scanned_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回模型列表。"""
        adapter = GoogleScannedAdapter()
        mock_response = [
            {
                "name": "Mug",
                "displayName": "Coffee Mug",
                "links": {"self": "https://fuel.gazebosim.org/1.0/GoogleResearch/models/Mug"},
                "description": "A coffee mug",
                "tags": ["kitchen"],
                "version": 1,
            }
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("mug")
            assert len(results) > 0
            assert results[0].source == DataSource.GOOGLE_SCANNED
            assert results[0].item_id == "Mug"
            assert results[0].title == "Coffee Mug"

    @pytest.mark.asyncio
    async def test_google_scanned_fetch_with_mock(self) -> None:
        """C5 修复后：fetch 返回 zip 压缩包，format 为 zip。"""
        adapter = GoogleScannedAdapter()
        fake_zip = b"PK\x03\x04zip data"
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_zip
        ):
            raw = await adapter.fetch("ACE_Coffee_Mug")
            assert raw.source == DataSource.GOOGLE_SCANNED
            assert raw.item_id == "ACE_Coffee_Mug"
            assert raw.format == "zip"
            assert raw.size_bytes > 0
            assert raw.url.endswith(".zip")
