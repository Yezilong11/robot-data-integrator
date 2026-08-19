# tests/unit/adapters/test_google_scanned.py
"""GoogleScannedAdapter 的单元测试。"""

import io
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import trimesh

from rdi.adapters.google_scanned import GoogleScannedAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource

SAMPLE_MESH_DIR = Path(__file__).parents[1] / "skills" / "sample_data" / "mesh"


class TestGoogleScannedAdapter:
    """GoogleScannedAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = GoogleScannedAdapter()
        assert adapter.source == DataSource.GOOGLE_SCANNED

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = GoogleScannedAdapter()
        assert adapter.base_url == "https://fuel.gazebosim.org/1.0/GoogleResearch"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = GoogleScannedAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = GoogleScannedAdapter()
        adapter.max_retry = 1
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=AdapterError("fail", source="google_scanned"),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("mug")
            assert exc_info.value.source == "google_scanned"

    @pytest.mark.asyncio
    async def test_google_scanned_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回模型列表。"""
        adapter = GoogleScannedAdapter()
        mock_response = [
            {
                "name": "Mug",
                "displayName": "Coffee Mug",
                "links": {"self": "https://fuel.gazebosim.org/1.0/GoogleResearch/models/Mug"},
                "description": "A coffee mug",
                "tags": ["kitchen"],
                "version": 1,
            }
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("mug")
            assert len(results) > 0
            assert results[0].source == DataSource.GOOGLE_SCANNED
            assert results[0].item_id == "Mug"
            assert results[0].title == "Coffee Mug"

    @pytest.mark.asyncio
    async def test_google_scanned_fetch_single_mesh(self) -> None:
        """Task 3 修订后：fetch 从文件树中只下载单个 mesh，format 为 obj。"""
        adapter = GoogleScannedAdapter()
        fake_obj = b"# OBJ mesh data"
        file_tree_info = {
            "file_tree": [
                {"path": "/meshes/cup.obj"},
                {"path": "/model.sdf"},
            ]
        }
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=file_tree_info),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_obj),
        ):
            raw = await adapter.fetch("ACE_Coffee_Mug")
            assert raw.source == DataSource.GOOGLE_SCANNED
            assert raw.item_id == "ACE_Coffee_Mug"
            assert raw.format == "obj"
            assert raw.data == fake_obj
            assert raw.size_bytes > 0
            assert raw.url.endswith("/meshes/cup.obj")

    @pytest.mark.asyncio
    async def test_google_scanned_fetch_metadata_when_no_mesh(self) -> None:
        """D3 修复：文件树无支持格式时抛 AdapterError（携带 zip 引用），让检索循环继续下一候选源。"""
        adapter = GoogleScannedAdapter()
        file_tree_info = {
            "file_tree": [
                {"path": "/model.sdf"},
                {"path": "/textures/foo.png"},
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=file_tree_info):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.fetch("ACE_Coffee_Mug")
        assert "zip 供手动下载" in exc_info.value.message
        assert "ACE_Coffee_Mug.zip" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_google_scanned_fetch_metadata_when_download_fails(self) -> None:
        """D3 修复：单个 mesh 下载失败时抛 AdapterError（携带 zip 引用），不返回误导性的 metadata JSON。"""
        adapter = GoogleScannedAdapter()
        file_tree_info = {
            "file_tree": [
                {"path": "/meshes/cup.obj"},
            ]
        }
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=file_tree_info),
            patch.object(
                adapter,
                "_download_bytes",
                new_callable=AsyncMock,
                side_effect=AdapterError("timeout", source="google_scanned"),
            ),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.fetch("ACE_Coffee_Mug")
        assert "mesh 文件下载失败" in exc_info.value.message
        assert "zip 供手动下载" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_google_scanned_fetch_returns_trimesh_loadable_obj(self) -> None:
        """Task 3 验证：返回的单个 mesh 字节可被 trimesh.load 加载。"""
        adapter = GoogleScannedAdapter()
        real_obj = (SAMPLE_MESH_DIR / "triangle.obj").read_bytes()
        file_tree_info = {
            "file_tree": [
                {"path": "/meshes/cup.obj"},
                {"path": "/model.sdf"},
            ]
        }
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=file_tree_info),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock, return_value=real_obj),
        ):
            raw = await adapter.fetch("ACE_Coffee_Mug")
        assert raw.format == "obj"
        mesh = trimesh.load(io.BytesIO(raw.data), file_type="obj")
        assert len(mesh.vertices) == 3
        assert len(mesh.faces) == 1

    @pytest.mark.asyncio
    async def test_google_scanned_metadata_fallback_sets_reference(self) -> None:
        """D3 修复：文件树获取失败时抛 AdapterError，错误信息携带 zip 下载地址供手动获取。

        不再返回 metadata JSON（原实现会让 MeshSkill 解析失败且检索循环误判"成功"），
        zip 引用通过异常 message 带出。
        """
        adapter = GoogleScannedAdapter()
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=AdapterError("network down", source="google_scanned"),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.fetch("ACE_Coffee_Mug")
        assert "zip 供手动下载" in exc_info.value.message
        assert ".zip" in exc_info.value.message
