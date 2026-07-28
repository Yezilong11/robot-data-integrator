# tests/unit/adapters/test_franka.py
"""FrankaAdapter 的单元测试。"""

import pytest

from rdi.adapters.franka import FrankaAdapter
from rdi.models.common import DataSource


class TestFrankaAdapter:
    """FrankaAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = FrankaAdapter()
        assert adapter.source == DataSource.FRANKA

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = FrankaAdapter()
        assert (
            adapter.base_url == "https://raw.githubusercontent.com/frankaemika/franka_ros/develop"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = FrankaAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 返回结果。"""
        adapter = FrankaAdapter()
        results = await adapter.search("panda")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_franka_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 FRANKA 源。"""
    adapter = FrankaAdapter()
    results = await adapter.search("panda")
    assert len(results) > 0
    assert results[0].source == DataSource.FRANKA


@pytest.mark.asyncio
async def test_franka_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 urdf。"""
    from unittest.mock import AsyncMock, patch

    adapter = FrankaAdapter()
    fake_urdf = b'<robot name="panda"/>'
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf):
        raw = await adapter.fetch("panda")
        assert raw.source == DataSource.FRANKA
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.size_bytes == len(fake_urdf)
        assert raw.size_bytes > 0
