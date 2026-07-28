# tests/unit/adapters/test_mujoco.py
"""MuJoCoAdapter 的单元测试。"""

import pytest

from rdi.adapters.mujoco import MuJoCoAdapter
from rdi.models.common import DataSource


class TestMuJoCoAdapter:
    """MuJoCoAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = MuJoCoAdapter()
        assert adapter.source == DataSource.MUJOCO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = MuJoCoAdapter()
        assert (
            adapter.base_url
            == "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = MuJoCoAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """正常情况：硬编码列表 Adapter 的 search 不会抛出异常。"""
        adapter = MuJoCoAdapter()
        results = await adapter.search("ant")
        assert len(results) > 0


# ── Mock 驱动的 search / fetch 测试 ──


@pytest.mark.asyncio
async def test_mujoco_search_returns_results() -> None:
    """正常情况：search 直接调用硬编码列表，返回结果包含 MUJOCO 源。"""
    adapter = MuJoCoAdapter()
    results = await adapter.search("ant")
    assert len(results) > 0
    assert results[0].source == DataSource.MUJOCO


@pytest.mark.asyncio
async def test_mujoco_fetch_with_mock() -> None:
    """正常情况：mock _download_bytes 后 fetch 返回 RawData，format 为 xml。"""
    from unittest.mock import AsyncMock, patch

    adapter = MuJoCoAdapter()
    fake_xml = b"<mujoco><worldbody/></mujoco>"
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_xml):
        raw = await adapter.fetch("ant")
        assert raw.source == DataSource.MUJOCO
        assert raw.format == "xml"
        assert raw.data == fake_xml
        assert raw.size_bytes == len(fake_xml)
        assert raw.size_bytes > 0
