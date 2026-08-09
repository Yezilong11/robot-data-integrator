# tests/unit/adapters/test_ycb.py
"""YCBAdapter 的单元测试。"""

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import trimesh

from rdi.adapters.ycb import YCBAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource

SAMPLE_MESH_DIR = Path(__file__).parents[1] / "skills" / "sample_data" / "mesh"


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试互相污染仓库 data/cache/。"""
    monkeypatch.setattr(YCBAdapter, "cache_root", lambda self: tmp_path)


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
    async def test_fetch_prefers_obj(self) -> None:
        """Task 3 修订：优先拉取 .obj/.stl，format 取实际扩展名。"""
        adapter = YCBAdapter()
        fake_obj = b"# OBJ mesh data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "meshes/025_mug/google_16k/textured.glb"},
            {"type": "file", "path": "meshes/025_mug/google_16k/nontextured.stl"},
            {"type": "file", "path": "meshes/025_mug/google_16k/textured.obj"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj),
        ):
            raw = await adapter.fetch("025_mug")
        assert raw.source == DataSource.YCB
        assert raw.format == "obj"
        assert raw.data == fake_obj
        assert raw.size_bytes == len(fake_obj)
        assert raw.size_bytes > 0
        assert "meshes/025_mug/google_16k/textured.obj" in raw.url

    @pytest.mark.asyncio
    async def test_fetch_falls_back_to_glb(self) -> None:
        """Task 3 修订：无 obj/stl 时兼容 .glb/.gltf 兜底。"""
        adapter = YCBAdapter()
        fake_glb = b"GLB mesh data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "meshes/025_mug/google_16k/textured.glb"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_glb),
        ):
            raw = await adapter.fetch("025_mug")
        assert raw.format == "glb"
        assert raw.data == fake_glb

    @pytest.mark.asyncio
    async def test_fetch_minus_one_suffix_fallback(self) -> None:
        """Task 3 修订：{item_id} 不存在时尝试 {item_id}-1 兜底。"""
        adapter = YCBAdapter()
        fake_stl = b"STL mesh data"
        mock_tree_minus_one = [
            {"type": "file", "path": "005_tomato_soup_can-1/google_16k/nontextured.stl"},
        ]

        async def fake_request(method: str, path: str) -> list:
            if "005_tomato_soup_can-1" in path:
                return mock_tree_minus_one
            raise AdapterError(message="not found", source=DataSource.YCB.value, status_code=404)

        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, side_effect=fake_request),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_stl),
        ):
            raw = await adapter.fetch("005_tomato_soup_can")
        assert raw.format == "stl"
        assert raw.data == fake_stl

    @pytest.mark.asyncio
    async def test_fetch_no_mesh_raises(self) -> None:
        """Task 3 修订后：文件树无 mesh 文件时抛 AdapterError。"""
        adapter = YCBAdapter()
        mock_tree = [{"type": "file", "path": "README.md"}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            pytest.raises(AdapterError) as exc_info,
        ):
            await adapter.fetch("025_mug")
        assert "No mesh file" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_fetch_returns_trimesh_loadable_obj(self) -> None:
        """Task 3 验证：返回的 .obj 字节可被 trimesh.load 加载。"""
        adapter = YCBAdapter()
        real_obj = (SAMPLE_MESH_DIR / "triangle.obj").read_bytes()
        mock_tree = [
            {"type": "file", "path": "025_mug/google_16k/textured.obj"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=real_obj),
        ):
            raw = await adapter.fetch("025_mug")
        assert raw.format == "obj"
        mesh = trimesh.load(io.BytesIO(raw.data), file_type="obj")
        assert len(mesh.vertices) == 3
        assert len(mesh.faces) == 1

    @pytest.mark.asyncio
    async def test_fetch_prefers_local_cache(self, tmp_path, monkeypatch) -> None:
        """首次 fetch 触发下载并落盘；二次 fetch 命中缓存不再触发网络。"""
        adapter = YCBAdapter()
        monkeypatch.setattr(adapter, "cache_root", lambda: tmp_path)
        fake_obj = b"# OBJ mesh data"
        mock_tree = [
            {"type": "file", "path": "meshes/025_mug/google_16k/textured.obj"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj
            ) as mock_dl,
        ):
            raw1 = await adapter.fetch("025_mug")
            raw2 = await adapter.fetch("025_mug")
        assert raw1.data == fake_obj
        assert raw2.data == fake_obj
        assert raw1.format == "obj"
        # 仅首次触发下载；二次命中本地缓存
        mock_dl.assert_awaited_once()
        cache_file = tmp_path / "025_mug.obj"
        assert cache_file.is_file()
        assert cache_file.read_bytes() == fake_obj

    @pytest.mark.asyncio
    async def test_fetch_grasp_annotation_available(self) -> None:
        """3.3：GRASP 且标注源可用时返回 .mat 抓取标注。"""
        adapter = YCBAdapter()
        fake_mat = b"MATLAB annotation data"
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_mat
        ):
            raw = await adapter.fetch("011_banana", req_type=DataReqType.GRASP)
        assert raw.source == DataSource.YCB
        assert raw.format == "mat"
        assert raw.data == fake_mat
        assert raw.metadata["grasp_annotation_available"] is True
        assert raw.metadata["is_real_grasp"] is True

    @pytest.mark.asyncio
    async def test_fetch_grasp_annotation_unavailable_falls_back_to_mesh(self) -> None:
        """3.3：GRASP 但标注源不可用（下载失败）时静默降级为 mesh，不回归。"""
        adapter = YCBAdapter()
        fake_obj = b"# OBJ mesh data"
        mock_tree = [
            {"type": "file", "path": "meshes/011_banana/google_16k/textured.obj"},
        ]
        with (
            patch.object(
                adapter,
                "_download_bytes",
                new_callable=AsyncMock,
                side_effect=[
                    AdapterError(
                        message="annotation download failed", source=DataSource.YCB.value
                    ),
                    fake_obj,
                ],
            ),
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
        ):
            raw = await adapter.fetch("011_banana", req_type=DataReqType.GRASP)
        assert raw.format == "obj"
        assert raw.data == fake_obj
        assert raw.metadata["grasp_annotation_available"] is False
