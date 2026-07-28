# tests/unit/adapters/test_allegro.py
"""AllegroAdapter 的单元测试。"""

import pytest

from rdi.adapters.allegro import AllegroAdapter
from rdi.models.common import DataSource


class TestAllegroAdapter:
    """AllegroAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = AllegroAdapter()
        assert adapter.source == DataSource.ALLEGRO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = AllegroAdapter()
        assert (
            adapter.base_url == "https://raw.githubusercontent.com/simlabor/allegro_hand_ros/main"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = AllegroAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 不会抛出异常。"""
        adapter = AllegroAdapter()
        results = await adapter.search("allegro")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_allegro_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 ALLEGRO 源。"""
    adapter = AllegroAdapter()
    results = await adapter.search("allegro")
    assert len(results) > 0
    assert results[0].source == DataSource.ALLEGRO


@pytest.mark.asyncio
async def test_allegro_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 urdf。"""
    from unittest.mock import AsyncMock, patch

    adapter = AllegroAdapter()
    fake_urdf = b'<robot name="allegro_hand_v4"/>'
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf):
        raw = await adapter.fetch("allegro_hand_v4")
        assert raw.source == DataSource.ALLEGRO
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.size_bytes == len(fake_urdf)
        assert raw.size_bytes > 0
