# tests/unit/adapters/test_graspnet.py
"""GraspNetAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.graspnet import GraspNetAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource


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
    async def test_fetch_mesh_success(self) -> None:
        """Task 3 修订后：req_type=MESH 返回首个 .obj/.ply/.stl/.dae mesh 文件。"""
        adapter = GraspNetAdapter()
        fake_obj = b"# OBJ mesh data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "models/object_000001.obj"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj),
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.MESH)
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "obj"
        assert raw.data == fake_obj
        assert raw.size_bytes == len(fake_obj)
        assert raw.size_bytes > 0
        assert "models/object_000001.obj" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_grasp_success(self) -> None:
        """Task 3 修订后：req_type=GRASP 返回首个 .npz/.pkl 抓取文件。"""
        adapter = GraspNetAdapter()
        fake_npz = b"\x93NPZ"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasp_label/0000_labels.npz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz),
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP)
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "npz"
        assert raw.data == fake_npz
        assert "grasp_label/0000_labels.npz" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_dataset_returns_metadata(self) -> None:
        """Task 3 修订后：req_type=DATASET 返回 metadata JSON，不下载整个 tar。"""
        adapter = GraspNetAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "rect_labels.tar.gz", "size": 999999999},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.DATASET)
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "json"
        mock_dl.assert_not_called()
        payload = __import__("json").loads(raw.data)
        assert payload["dataset_id"] == "DravenALG/GraspNet-1Billion"
        assert any(f["path"] == "rect_labels.tar.gz" for f in payload["file_list"])

    @pytest.mark.asyncio
    async def test_fetch_mesh_returns_metadata_when_no_single_mesh(self) -> None:
        """Task 3 修订后：MESH 请求但仓库只有 tar 归档时返回 metadata JSON。"""
        adapter = GraspNetAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "models.tar"},
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.MESH)
        assert raw.format == "json"
        payload = __import__("json").loads(raw.data)
        assert "mesh" in payload["reason"]

    @pytest.mark.asyncio
    async def test_fetch_grasp_returns_metadata_when_no_single_grasp(self) -> None:
        """Task 3 修订后：GRASP 请求但仓库只有 tar/hdf5 时返回 metadata JSON。"""
        adapter = GraspNetAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasp_label.tar"},
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP)
        assert raw.format == "json"
        payload = __import__("json").loads(raw.data)
        assert "grasp" in payload["reason"]

    @pytest.mark.asyncio
    async def test_fetch_returns_metadata_when_over_threshold(self) -> None:
        """Task 3 修订：HEAD 预检体积超 max_fetch_bytes 时返回 metadata JSON。"""
        import json as _json

        from rdi.config.settings import settings

        adapter = GraspNetAdapter()
        big_size = settings.max_fetch_bytes + 1
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "grasp_label/0000_labels.npz", "size": big_size},
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
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP)
        assert raw.format == "json"
        mock_dl.assert_not_called()
        payload = _json.loads(raw.data)
        assert payload["file_size"] == big_size
        assert payload["file_path"] == "grasp_label/0000_labels.npz"
