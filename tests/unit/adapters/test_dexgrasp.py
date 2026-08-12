# tests/unit/adapters/test_dexgrasp.py
"""DexGraspAdapter 的单元测试。"""

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.dexgrasp import DexGraspAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试互相污染仓库 data/cache/。"""
    monkeypatch.setattr(DexGraspAdapter, "cache_root", lambda self: tmp_path)


class TestDexGraspAdapter:
    """DexGraspAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = DexGraspAdapter()
        assert adapter.source == DataSource.DEXGRASP

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = DexGraspAdapter()
        assert adapter.base_url == "https://huggingface.co/api"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = DexGraspAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = DexGraspAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("grasp")
        assert exc_info.value.source == "dexgrasp"

    @pytest.mark.asyncio
    async def test_dexgrasp_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回数据集列表。"""
        adapter = DexGraspAdapter()
        mock_response = [
            {
                "id": "dexgraspnet/dexgraspnet",
                "downloads": 100,
                "likes": 10,
                "tags": ["grasping"],
            }
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("grasp")
            assert len(results) > 0
            assert results[0].source == DataSource.DEXGRASP
            assert results[0].item_id == "dexgraspnet/dexgraspnet"
            assert results[0].metadata["downloads"] == 100

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_mesh_success(self) -> None:
        """Task 3 修订后：req_type=MESH 返回首个 .obj/.ply/.stl/.dae mesh 文件。"""
        adapter = DexGraspAdapter()
        fake_obj = b"# OBJ mesh data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "meshes/object_000001.obj"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj),
        ):
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.MESH)
            assert raw.source == DataSource.DEXGRASP
            assert raw.item_id == "lhrlhr/DexGraspNet2.0"
            assert raw.format == "obj"
            assert raw.data == fake_obj
            assert raw.size_bytes > 0
            assert "meshes/object_000001.obj" in raw.url

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_grasp_success(self) -> None:
        """Task 3 修订后：req_type=GRASP 返回首个 .npz/.pkl 抓取文件。"""
        adapter = DexGraspAdapter()
        fake_npz = b"\x93NPZ"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasps/0000_grasp.npz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz),
        ):
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.GRASP)
        assert raw.source == DataSource.DEXGRASP
        assert raw.format == "npz"
        assert raw.data == fake_npz
        assert "grasps/0000_grasp.npz" in raw.url
        assert raw.metadata["is_real_grasp"] is True

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_grasp_by_object_name(self) -> None:
        """3.2：GRASP + object_name 命中物体对应的 .pkl 抓取文件，复用本地缓存。"""
        adapter = DexGraspAdapter()
        fake_pkl = b"\x80\x05pkl"
        mock_tree = [
            {"type": "file", "path": "grasps/0000_grasp.pkl"},
            {"type": "file", "path": "grasps/011_banana_grasp.pkl"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_pkl
            ) as mock_dl,
        ):
            raw1 = await adapter.fetch(
                "lhrlhr/DexGraspNet2.0",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
            raw2 = await adapter.fetch(
                "lhrlhr/DexGraspNet2.0",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
        assert "011_banana" in raw1.url
        assert raw1.format == "pkl"
        assert raw1.data == fake_pkl
        assert raw1.metadata["is_real_grasp"] is True
        assert raw2.data == fake_pkl
        # 仅首次触发下载；二次命中本地缓存
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_dataset_returns_metadata(self) -> None:
        """Task 3 修订后：req_type=DATASET 返回 metadata JSON，不下载整个 tar.gz。"""
        adapter = DexGraspAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "dex_grasps_new.tar.gz", "size": 999999999},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
        ):
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.DATASET)
        assert raw.source == DataSource.DEXGRASP
        assert raw.format == "json"
        mock_dl.assert_not_called()
        payload = __import__("json").loads(raw.data)
        assert payload["dataset_id"] == "lhrlhr/DexGraspNet2.0"
        assert any(f["path"] == "dex_grasps_new.tar.gz" for f in payload["file_list"])

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_mesh_returns_metadata_when_no_single_mesh(self) -> None:
        """Task 3 修订后：MESH 请求但仓库只有 tar.gz 归档时返回 metadata JSON。"""
        adapter = DexGraspAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "meshes.tar.gz"},
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree):
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.MESH)
        assert raw.format == "json"
        payload = __import__("json").loads(raw.data)
        assert "mesh" in payload["reason"]

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_grasp_returns_metadata_when_no_single_grasp(self) -> None:
        """Task 3 修订后：GRASP 请求但仓库只有 tar.gz 归档时返回 metadata JSON。"""
        adapter = DexGraspAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasps.tar.gz"},
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree):
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.GRASP)
        assert raw.format == "json"
        payload = __import__("json").loads(raw.data)
        assert "grasp" in payload["reason"]

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_grasp_raw_fallback(self) -> None:
        """Task 13：HF 仓库无单文件时走 DexGraspNet 官方 GitHub raw 单物体 grasp 兜底。"""
        adapter = DexGraspAdapter()
        fake_npy = b"\x93NUMPY"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasps.tar.gz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npy
            ) as mock_dl,
        ):
            raw = await adapter.fetch(
                "lhrlhr/DexGraspNet2.0",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
            # 二次 fetch 命中本地缓存，不重复下载
            await adapter.fetch(
                "lhrlhr/DexGraspNet2.0",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
        assert raw.format == "npy"
        assert raw.data == fake_npy
        assert "raw.githubusercontent.com/PKU-EPIC/DexGraspNet" in raw.url
        assert "ddg-gd_banana_poisson_002.npy" in raw.url
        assert raw.metadata["is_real_grasp"] is True
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_grasp_raw_fallback_fails_silently(self) -> None:
        """Task 13：raw 兜底下载失败时静默降级为 metadata JSON（不抛异常）。"""
        adapter = DexGraspAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "grasps.tar.gz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter,
                "_download_bytes",
                new_callable=AsyncMock,
                side_effect=AdapterError(message="download failed", source="dexgrasp"),
            ),
        ):
            raw = await adapter.fetch(
                "lhrlhr/DexGraspNet2.0",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
        assert raw.format == "json"
        payload = __import__("json").loads(raw.data)
        assert "grasp" in payload["reason"]

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_returns_metadata_when_over_threshold(self) -> None:
        """Task 3 修订：HEAD 预检体积超 max_fetch_bytes 时返回 metadata JSON。"""
        import json as _json

        from rdi.config.settings import settings

        adapter = DexGraspAdapter()
        big_size = settings.max_fetch_bytes + 1
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "grasps/0000_grasp.npz", "size": big_size},
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
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0", req_type=DataReqType.GRASP)
        assert raw.format == "json"
        mock_dl.assert_not_called()
        payload = _json.loads(raw.data)
        assert payload["file_size"] == big_size
        assert payload["file_path"] == "grasps/0000_grasp.npz"
