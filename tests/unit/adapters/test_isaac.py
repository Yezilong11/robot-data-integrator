# tests/unit/adapters/test_isaac.py
"""IsaacSimAdapter 的单元测试。"""

import pytest

from rdi.adapters.isaac import IsaacSimAdapter
from rdi.models.common import DataSource


class TestIsaacSimAdapter:
    """IsaacSimAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = IsaacSimAdapter()
        assert adapter.source == DataSource.ISAAC

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = IsaacSimAdapter()
        assert (
            adapter.base_url == "https://raw.githubusercontent.com/NVIDIA-Omniverse/IsaacSim/main"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = IsaacSimAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 返回结果。"""
        adapter = IsaacSimAdapter()
        results = await adapter.search("franka")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_isaac_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 ISAAC 源。"""
    adapter = IsaacSimAdapter()
    results = await adapter.search("franka")
    assert len(results) > 0
    assert results[0].source == DataSource.ISAAC


@pytest.mark.asyncio
async def test_isaac_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 usd。"""
    from unittest.mock import AsyncMock, patch

    adapter = IsaacSimAdapter()
    fake_usd = b"# USD data"
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_usd):
        raw = await adapter.fetch("franka_cabinet")
        assert raw.source == DataSource.ISAAC
        assert raw.format == "usd"
        assert raw.data == fake_usd
        assert raw.size_bytes == len(fake_usd)
        assert raw.size_bytes > 0
