# tests/unit/adapters/test_allegro.py
"""AllegroAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.allegro import AllegroAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestAllegroAdapter:
    """AllegroAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = AllegroAdapter()
        assert adapter.source == DataSource.ALLEGRO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确（C7 修复后走 pal-robotics）。"""
        adapter = AllegroAdapter()
        assert (
            adapter.base_url == "https://raw.githubusercontent.com/pal-robotics/allegro_hand/main"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = AllegroAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            results = await adapter.search("allegro")
        assert len(results) > 0
        assert results[0].source == DataSource.ALLEGRO
        assert "allegro" in results[0].item_id
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """C7 修复后：单路径 fetch，mock _download_bytes 返回数据，format 为 urdf。"""
        adapter = AllegroAdapter()
        fake_urdf = b'<robot name="allegro_hand"/>'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ) as mock_dl:
            raw = await adapter.fetch("allegro_hand_v4")
        assert raw.source == DataSource.ALLEGRO
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.size_bytes == len(fake_urdf)
        assert "allegro_hand.urdf.xacro" in raw.url
        # C7: 单路径，只调用一次
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_fail_raises(self) -> None:
        """C7 修复后：单路径 fetch 失败直接抛 AdapterError。"""
        adapter = AllegroAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = AdapterError(
                message="download failed", source=DataSource.ALLEGRO.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("allegro_hand_v4")
        # C7: 单路径，只尝试一次
        mock_dl.assert_awaited_once()
