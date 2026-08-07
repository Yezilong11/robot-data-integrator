# tests/unit/adapters/test_graspnet.py
"""GraspNetAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.graspnet import GraspNetAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestGraspNetAdapter:
    """GraspNetAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = GraspNetAdapter()
        assert adapter.source == DataSource.GRASPNET

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确（C3 修复后默认走 hf-mirror.com）。"""
        adapter = GraspNetAdapter()
        assert adapter.base_url == "https://hf-mirror.com"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = GraspNetAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = GraspNetAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.GRASPNET.value
            )
            results = await adapter.search("graspnet")
        assert len(results) > 0
        assert results[0].source == DataSource.GRASPNET
        assert "graspnet" in results[0].item_id.lower()
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = GraspNetAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.GRASPNET.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_primary_success(self) -> None:
        """C3 修复后：mock _request 返回文件树 + _download_bytes 返回数据。

        E1 修复后 fetch 先 HEAD 预检体积；mock _head_content_length 返回 None
        （大小未知）→ 走原下载流程。
        """
        adapter = GraspNetAdapter()
        fake_npz = b"\x93NPZ"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "data/grasp_data.npz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz),
        ):
            raw = await adapter.fetch("graspnet-benchmark")
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "npz"
        assert raw.data == fake_npz
        assert raw.size_bytes == len(fake_npz)
        assert raw.size_bytes > 0
        assert "data/grasp_data.npz" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_matches_tar_gz(self) -> None:
        """E1 修订：target_exts 含 .tar.gz，优先匹配 .tar.gz 而非 .tar。

        构造含 .tar.gz 与 .tar 的文件树，验证选中 .tar.gz 且 format=tar.gz。
        """
        adapter = GraspNetAdapter()
        fake_bytes = b"tar.gz!"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "rect_labels.tar.gz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ),
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion")
        assert raw.format == "tar.gz"
        assert "rect_labels.tar.gz" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_returns_metadata_when_over_threshold(self) -> None:
        """C3+E1 修复：HEAD 预检体积超 max_fetch_bytes 时返回 metadata JSON。

        验证：不调用 _download_bytes；返回 format=json，含 url/size_bytes/file_list。
        """
        import json as _json

        from rdi.config.settings import settings

        adapter = GraspNetAdapter()
        big_size = settings.max_fetch_bytes + 1
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "rect_labels.tar", "size": big_size},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter,
                "_head_content_length",
                new_callable=AsyncMock,
                return_value=big_size,
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion")
        assert raw.format == "json"
        assert raw.size_bytes == big_size
        mock_dl.assert_not_called()
        payload = _json.loads(raw.data)
        assert payload["size_bytes"] == big_size
        assert payload["file_path"] == "rect_labels.tar"
        assert payload["dataset_id"] == "DravenALG/GraspNet-1Billion"
        assert any(f["path"] == "rect_labels.tar" for f in payload["file_list"])

    @pytest.mark.asyncio
    async def test_fetch_no_npz_raises(self) -> None:
        """C3 修复后：文件树无数据文件时抛 AdapterError。"""
        adapter = GraspNetAdapter()
        mock_tree = [{"type": "file", "path": "README.md"}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            pytest.raises(AdapterError) as exc_info,
        ):
            await adapter.fetch("graspnet-benchmark")
        assert "No data file" in exc_info.value.message
