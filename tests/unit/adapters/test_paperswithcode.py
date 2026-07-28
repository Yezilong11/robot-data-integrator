# tests/unit/adapters/test_paperswithcode.py
"""PapersWithCodeAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.paperswithcode import PapersWithCodeAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestPapersWithCodeAdapter:
    """PapersWithCodeAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.source == DataSource.PAPERSWITHCODE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.base_url == "https://paperswithcode.com/api/v1"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = PapersWithCodeAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "paperswithcode"

    @pytest.mark.asyncio
    async def test_paperswithcode_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回论文列表。"""
        adapter = PapersWithCodeAdapter()
        mock_response = {
            "results": [
                {
                    "paper": {
                        "id": "graspnet",
                        "title": "GraspNet",
                        "url": "https://paperswithcode.com/paper/graspnet",
                        "repository": {
                            "url": "https://github.com/test",
                            "framework": "pytorch",
                        },
                    }
                }
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("graspnet")
            assert len(results) > 0
            assert results[0].source == DataSource.PAPERSWITHCODE
            assert results[0].item_id == "graspnet"
            assert results[0].title == "GraspNet"
            assert results[0].metadata["code_url"] == "https://github.com/test"

    @pytest.mark.asyncio
    async def test_paperswithcode_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = PapersWithCodeAdapter()
        paper_data = {"id": "graspnet", "title": "GraspNet"}
        implementations_data = {"results": []}
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=[paper_data, implementations_data],
        ):
            raw = await adapter.fetch("graspnet")
            assert raw.source == DataSource.PAPERSWITHCODE
            assert raw.item_id == "graspnet"
            assert raw.format == "json"
            assert raw.size_bytes > 0
