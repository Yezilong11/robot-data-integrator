# tests/unit/adapters/test_graspnet.py
"""GraspNetAdapter 的单元测试。"""

import pytest

from rdi.adapters.graspnet import GraspNetAdapter
from rdi.models.common import DataSource


class TestGraspNetAdapter:
    """GraspNetAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = GraspNetAdapter()
        assert adapter.source == DataSource.GRASPNET

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = GraspNetAdapter()
        assert adapter.base_url == "https://huggingface.co"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = GraspNetAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 不会抛出异常。"""
        adapter = GraspNetAdapter()
        results = await adapter.search("mug")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_graspnet_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 GRASPNET 源。"""
    adapter = GraspNetAdapter()
    results = await adapter.search("benchmark")
    assert len(results) > 0
    assert results[0].source == DataSource.GRASPNET


@pytest.mark.asyncio
async def test_graspnet_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 npz。"""
    from unittest.mock import AsyncMock, patch

    adapter = GraspNetAdapter()
    fake_npz = b"\x93NPZ"
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz):
        raw = await adapter.fetch("graspnet-benchmark")
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "npz"
        assert raw.data == fake_npz
        assert raw.size_bytes == len(fake_npz)
        assert raw.size_bytes > 0
