# tests/unit/adapters/test_zenodo.py
"""ZenodoAdapter 的单元测试。"""

import pytest

from rdi.adapters.zenodo import ZenodoAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestZenodoAdapter:
    """ZenodoAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = ZenodoAdapter()
        assert adapter.source == DataSource.ZENODO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = ZenodoAdapter()
        assert adapter.base_url == "https://zenodo.org/api"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = ZenodoAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = ZenodoAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasp dataset")
        assert exc_info.value.source == "zenodo"
