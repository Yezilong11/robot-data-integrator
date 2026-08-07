# tests/unit/adapters/test_ycb.py
"""YCBAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.ycb import YCBAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestYCBAdapter:
    """YCBAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = YCBAdapter()
        assert adapter.source == DataSource.YCB

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确（C4 修复后默认走 hf-mirror.com）。"""
        adapter = YCBAdapter()
        assert adapter.base_url == "https://hf-mirror.com"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = YCBAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = YCBAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.YCB.value
            )
            results = await adapter.search("mug")
        assert len(results) > 0
        assert results[0].source == DataSource.YCB
        assert "mug" in results[0].item_id
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = YCBAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.YCB.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_primary_success(self) -> None:
        """C4 修订后：mock _request 返回文件树 + _download_bytes 返回数据。

        C4 修订：ai-habitat/ycb 实测为 .glb 而非 .obj，format 字段取实际扩展名。
        """
        adapter = YCBAdapter()
        fake_glb = b"GLB mesh data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "meshes/025_mug/google_16k/textured.glb"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_glb
            ),
        ):
            raw = await adapter.fetch("025_mug")
        assert raw.source == DataSource.YCB
        assert raw.format == "glb"
        assert raw.data == fake_glb
        assert raw.size_bytes == len(fake_glb)
        assert raw.size_bytes > 0
        assert "meshes/025_mug/google_16k/textured.glb" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_no_mesh_raises(self) -> None:
        """C4 修订后：文件树无 mesh 文件时抛 AdapterError。"""
        adapter = YCBAdapter()
        mock_tree = [{"type": "file", "path": "README.md"}]
        with patch.object(
            adapter, "_request", new_callable=AsyncMock, return_value=mock_tree
        ), pytest.raises(AdapterError) as exc_info:
            await adapter.fetch("025_mug")
        assert "No mesh file" in exc_info.value.message
