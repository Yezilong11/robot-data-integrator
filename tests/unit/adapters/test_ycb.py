# tests/unit/adapters/test_ycb.py
"""YCBAdapter 的单元测试。"""

import pytest

from rdi.adapters.ycb import YCBAdapter
from rdi.models.common import DataSource


class TestYCBAdapter:
    """YCBAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = YCBAdapter()
        assert adapter.source == DataSource.YCB

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = YCBAdapter()
        assert adapter.base_url == "https://huggingface.co"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = YCBAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 返回结果。"""
        adapter = YCBAdapter()
        results = await adapter.search("mug")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_ycb_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 YCB 源。"""
    adapter = YCBAdapter()
    results = await adapter.search("mug")
    assert len(results) > 0
    assert results[0].source == DataSource.YCB


@pytest.mark.asyncio
async def test_ycb_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 stl。"""
    from unittest.mock import AsyncMock, patch

    adapter = YCBAdapter()
    fake_stl = b"OBJ mesh data"
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_stl):
        raw = await adapter.fetch("025_mug")
        assert raw.source == DataSource.YCB
        assert raw.format == "stl"
        assert raw.data == fake_stl
        assert raw.size_bytes == len(fake_stl)
        assert raw.size_bytes > 0
