# tests/unit/adapters/test_dexgrasp.py
"""DexGraspAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.dexgrasp import DexGraspAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


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
    async def test_dexgrasp_fetch_with_mock(self) -> None:
        """C2 修订后：mock _request 返回文件树 + _download_bytes 返回数据。

        C2 修订：lhrlhr/DexGraspNet2.0 实测为 .tar.gz 归档，format 字段为 tar.gz。
        E1 修复后 fetch 先 HEAD 预检体积；mock _head_content_length 返回 None
        （大小未知）→ 走原下载流程。
        """
        adapter = DexGraspAdapter()
        fake_targz = b"\x1f\x8btar.gz data"
        mock_tree = [
            {"type": "file", "path": "README.md"},
            {"type": "file", "path": "dex_grasps_new.tar.gz", "size": 12345},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=None
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_targz
            ),
        ):
            raw = await adapter.fetch("dexgraspnet/dexgraspnet")
            assert raw.source == DataSource.DEXGRASP
            assert raw.item_id == "dexgraspnet/dexgraspnet"
            assert raw.format == "tar.gz"
            assert raw.size_bytes > 0
            assert "dex_grasps_new.tar.gz" in raw.url

    @pytest.mark.asyncio
    async def test_dexgrasp_fetch_returns_metadata_when_over_threshold(self) -> None:
        """C2+E1 修复：HEAD 预检体积超 max_fetch_bytes 时返回 metadata JSON。

        验证：不调用 _download_bytes；返回 format=json，含 url/size_bytes/file_list。
        """
        import json as _json

        from rdi.config.settings import settings

        adapter = DexGraspAdapter()
        big_size = settings.max_fetch_bytes + 1
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "dex_grasps_new.tar.gz", "size": big_size},
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
            raw = await adapter.fetch("lhrlhr/DexGraspNet2.0")
        assert raw.format == "json"
        assert raw.size_bytes == big_size
        mock_dl.assert_not_called()
        payload = _json.loads(raw.data)
        assert payload["size_bytes"] == big_size
        assert payload["file_path"] == "dex_grasps_new.tar.gz"
        assert payload["dataset_id"] == "lhrlhr/DexGraspNet2.0"
        assert any(f["path"] == "dex_grasps_new.tar.gz" for f in payload["file_list"])
