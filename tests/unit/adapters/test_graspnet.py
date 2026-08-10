# tests/unit/adapters/test_graspnet.py
"""GraspNetAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.graspnet import _FALLBACK_DATASETS, GraspNetAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataReqType, DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试互相污染仓库 data/cache/。"""
    monkeypatch.setattr(GraspNetAdapter, "cache_root", lambda self: tmp_path)


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
    async def test_search_fallback_no_match_raises_catalog_error(self) -> None:
        """路径 B 无匹配时抛 AdapterCatalogError（有源但未收录，不静默空）。"""
        adapter = GraspNetAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.GRASPNET.value
            )
            with pytest.raises(AdapterCatalogError) as exc_info:
                await adapter.search("zzznomatchxyz")
        assert "仅收录" in exc_info.value.message
        assert "有源但未收录" in exc_info.value.message
        assert f"仅收录 {len(_FALLBACK_DATASETS)}" in exc_info.value.message

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
        assert raw.metadata["is_real_grasp"] is True

    @pytest.mark.asyncio
    async def test_fetch_grasp_by_object_name(self) -> None:
        """3.1：GRASP + object_name="banana" 命中 grasp_label/ 下 011_banana 的真实 npz。"""
        adapter = GraspNetAdapter()
        fake_npz = b"\x93NPZ"
        mock_tree = [
            {"type": "file", "path": "grasp_label/0000_labels.npz"},
            {"type": "file", "path": "grasp_label/011_banana_0_labels.npz"},
            {"type": "file", "path": "grasp_label/003_cracker_box_0_labels.npz"},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz),
        ):
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
        assert "011_banana" in raw.url
        assert raw.metadata["is_real_grasp"] is True

    @pytest.mark.asyncio
    async def test_fetch_grasp_object_name_falls_back_to_first(self) -> None:
        """3.1：物体名未命中（未知物体）时回退首个 .npz，不回归。"""
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
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion",
                req_type=DataReqType.GRASP,
                object_name="zzz_unknown_object",
            )
        assert "0000_labels.npz" in raw.url
        assert raw.metadata["is_real_grasp"] is True

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

    @pytest.mark.asyncio
    async def test_fetch_prefers_local_cache(self, tmp_path, monkeypatch) -> None:
        """首次 fetch 触发下载并落盘；二次 fetch 命中缓存不再触发网络。"""
        adapter = GraspNetAdapter()
        monkeypatch.setattr(adapter, "cache_root", lambda: tmp_path)
        fake_npz = b"\x93NPZ"
        mock_tree = [{"type": "file", "path": "grasp_label/0000_labels.npz"}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz
            ) as mock_dl,
        ):
            raw1 = await adapter.fetch(
                "DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP
            )
            raw2 = await adapter.fetch(
                "DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP
            )
        assert raw1.data == fake_npz
        assert raw2.data == fake_npz
        assert raw1.format == "npz"
        # 仅首次触发下载；二次命中本地缓存
        mock_dl.assert_awaited_once()
        # 缓存文件名 = 清洗后的 item_id + 文件路径
        cache_file = tmp_path / "DravenALG_GraspNet-1Billion_grasp_label_0000_labels.npz"
        assert cache_file.is_file()
        assert cache_file.read_bytes() == fake_npz

    # ─── P0-4: 未下载大文件引用 RawReference ───

    def test_build_metadata_sets_reference(self) -> None:
        """P0-4：_build_metadata 构造 RawReference，url/file_size/reason 正确。"""
        adapter = GraspNetAdapter()
        raw = adapter._build_metadata(
            "DravenALG/GraspNet-1Billion",
            [],
            reason="数据集为超大归档",
            file_path="models.tar",
            file_url=(
                "https://hf-mirror.com/datasets/DravenALG/GraspNet-1Billion/"
                "resolve/main/models.tar"
            ),
            file_size=999999999,
        )
        assert raw.reference is not None
        assert raw.reference.url.endswith("resolve/main/models.tar")
        assert raw.reference.download_hint == raw.reference.url
        assert raw.reference.file_size == 999999999
        assert "超大归档" in raw.reference.reason

    def test_build_metadata_reference_default_url(self) -> None:
        """P0-4：无 file_url 时 reference.url 回退 HF 数据集主页。"""
        adapter = GraspNetAdapter()
        raw = adapter._build_metadata("DravenALG/GraspNet-1Billion", [])
        assert raw.reference is not None
        assert raw.reference.url == "https://huggingface.co/datasets/DravenALG/GraspNet-1Billion"
        assert raw.reference.file_size == 0
        assert "未自动下载" in raw.reference.reason

    @pytest.mark.asyncio
    async def test_fetch_downloaded_file_keeps_reference_none(self) -> None:
        """P0-4：正常下载的分支不设置 reference（保持 None）。"""
        adapter = GraspNetAdapter()
        fake_npz = b"\x93NPZ"
        mock_tree = [{"type": "file", "path": "grasp_label/0000_labels.npz"}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz),
        ):
            raw = await adapter.fetch("DravenALG/GraspNet-1Billion", req_type=DataReqType.GRASP)
        assert raw.format == "npz"
        assert raw.reference is None


class TestGraspNetAdapterLocalDatasets:
    """D3：来源级本地数据集挂载（settings.local_datasets）测试。

    本地目录即 HF repo 根镜像；命中返回 source=LOCAL，不发起任何网络请求。
    """

    @pytest.mark.asyncio
    async def test_fetch_local_grasp_by_object_name_hit_no_network(
        self, tmp_path, monkeypatch
    ) -> None:
        """GRASP 按 object_name 本地命中 grasp_label 下 .npz：无网络请求。"""
        local_root = tmp_path / "dataset"
        grasp_dir = local_root / "grasp_label"
        grasp_dir.mkdir(parents=True)
        (grasp_dir / "011_banana_0_labels.npz").write_bytes(b"npz-data")
        monkeypatch.setattr(settings, "local_datasets", {"graspnet": str(local_root)})
        adapter = GraspNetAdapter()
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request,
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
            patch.object(adapter, "_head_content_length", new_callable=AsyncMock) as mock_head,
        ):
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion",
                req_type=DataReqType.GRASP,
                object_name="banana",
            )
        assert raw.source == DataSource.LOCAL
        assert raw.format == "npz"
        assert raw.data == b"npz-data"
        assert raw.url.startswith("local://graspnet/")
        assert raw.metadata.get("is_real_grasp") is True
        mock_request.assert_not_awaited()
        mock_dl.assert_not_awaited()
        mock_head.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_grasp_by_object_id_hit(self, tmp_path, monkeypatch) -> None:
        """GRASP 按 item_id（GraspNet object id）本地命中。"""
        local_root = tmp_path / "dataset"
        grasp_dir = local_root / "grasp_label"
        grasp_dir.mkdir(parents=True)
        (grasp_dir / "011_banana_0_labels.npz").write_bytes(b"npz-data")
        monkeypatch.setattr(settings, "local_datasets", {"graspnet": str(local_root)})
        adapter = GraspNetAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            raw = await adapter.fetch("011_banana", req_type=DataReqType.GRASP)
        assert raw.source == DataSource.LOCAL
        assert raw.format == "npz"
        assert raw.data == b"npz-data"
        mock_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_mesh_hit(self, tmp_path, monkeypatch) -> None:
        """MESH 本地命中：按扩展名定位 mesh 文件。"""
        local_root = tmp_path / "dataset"
        mesh_dir = local_root / "models" / "banana"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "textured.obj").write_bytes(b"obj-data")
        monkeypatch.setattr(settings, "local_datasets", {"graspnet": str(local_root)})
        adapter = GraspNetAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion", req_type=DataReqType.MESH
            )
        assert raw.source == DataSource.LOCAL
        assert raw.format == "obj"
        assert raw.data == b"obj-data"
        assert raw.url.startswith("local://graspnet/")
        mock_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_miss_falls_back_to_network(self, tmp_path, monkeypatch) -> None:
        """本地挂载无匹配文件时走网络（行为与未配置一致）。"""
        local_root = tmp_path / "dataset"
        local_root.mkdir()  # 挂载存在但为空
        monkeypatch.setattr(settings, "local_datasets", {"graspnet": str(local_root)})
        adapter = GraspNetAdapter()
        fake_obj = b"obj-data"
        mock_tree = [{"type": "file", "path": "models/banana/textured.obj"}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj),
        ):
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion", req_type=DataReqType.MESH
            )
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "obj"
        assert raw.data == fake_obj

    @pytest.mark.asyncio
    async def test_fetch_local_dataset_type_still_network(self, tmp_path, monkeypatch) -> None:
        """DATASET 类型不参与本地单文件命中，仍走网络 metadata。"""
        local_root = tmp_path / "dataset"
        mesh_dir = local_root / "models" / "banana"
        mesh_dir.mkdir(parents=True)
        (mesh_dir / "textured.obj").write_bytes(b"obj-data")
        monkeypatch.setattr(settings, "local_datasets", {"graspnet": str(local_root)})
        adapter = GraspNetAdapter()
        mock_tree = [{"type": "file", "path": "models/banana/textured.obj", "size": 8}]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree):
            raw = await adapter.fetch(
                "DravenALG/GraspNet-1Billion", req_type=DataReqType.DATASET
            )
        assert raw.source == DataSource.GRASPNET
        assert raw.format == "json"
