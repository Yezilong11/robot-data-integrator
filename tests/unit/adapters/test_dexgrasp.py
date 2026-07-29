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
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = DexGraspAdapter()
        fake_npz = b"\x93NPZ"
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_npz
        ):
            raw = await adapter.fetch("dexgraspnet/dexgraspnet")
            assert raw.source == DataSource.DEXGRASP
            assert raw.item_id == "dexgraspnet/dexgraspnet"
            assert raw.format == "npz"
            assert raw.size_bytes > 0
