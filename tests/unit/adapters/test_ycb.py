# tests/unit/adapters/test_ycb.py
"""YCBAdapter 的单元测试。"""

import pytest

from rdi.adapters.ycb import YCBAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestYCBAdapter:
    """YCBAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = YCBAdapter()
        assert adapter.source == DataSource.YCB

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = YCBAdapter()
        assert adapter.base_url == "https://rse-lab.cs.washington.edu"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = YCBAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = YCBAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("mug")
        assert exc_info.value.source == "ycb"
