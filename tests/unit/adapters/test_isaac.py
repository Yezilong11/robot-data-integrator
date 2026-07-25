# tests/unit/adapters/test_isaac.py
"""IsaacSimAdapter 的单元测试。"""

import pytest

from rdi.adapters.isaac import IsaacSimAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestIsaacSimAdapter:
    """IsaacSimAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = IsaacSimAdapter()
        assert adapter.source == DataSource.ISAAC

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = IsaacSimAdapter()
        assert adapter.base_url == "https://docs.isaacsim.omniverse.nvidia.com"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = IsaacSimAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = IsaacSimAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("franka")
        assert exc_info.value.source == "isaac"
