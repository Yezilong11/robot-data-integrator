# tests/unit/adapters/test_franka.py
"""FrankaAdapter 的单元测试。"""

import pytest

from rdi.adapters.franka import FrankaAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestFrankaAdapter:
    """FrankaAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = FrankaAdapter()
        assert adapter.source == DataSource.FRANKA

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = FrankaAdapter()
        assert adapter.base_url == "https://franka.de"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = FrankaAdapter()
        assert adapter.semaphore._value == 5

    def test_fetch_urdf_method_exists(self) -> None:
        """正常情况：fetch_urdf 辅助方法存在。"""
        adapter = FrankaAdapter()
        assert hasattr(adapter, "fetch_urdf")
        assert callable(adapter.fetch_urdf)

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = FrankaAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("panda")
        assert exc_info.value.source == "franka"
