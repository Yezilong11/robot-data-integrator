# tests/unit/adapters/test_registry.py
"""Adapter 注册表单元测试。"""

from rdi.adapters.base import BaseAdapter
from rdi.adapters.registry import ADAPTER_REGISTRY, select_adapter
from rdi.models.common import DataReqType


class TestAdapterRegistry:
    """ADAPTER_REGISTRY 单元测试。"""

    def test_registry_has_all_req_types(self) -> None:
        """正常情况：注册表覆盖所有 DataReqType。"""
        expected_types = list(DataReqType)
        for req_type in expected_types:
            assert req_type in ADAPTER_REGISTRY, f"Missing {req_type} in ADAPTER_REGISTRY"

    def test_paper_primary_is_arxiv(self) -> None:
        """正常情况：PAPER 主源是 ArxivAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.PAPER]
        assert names[0] == "ArxivAdapter"

    def test_code_primary_is_github(self) -> None:
        """正常情况：CODE 主源是 GitHubAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.CODE]
        assert names[0] == "GitHubAdapter"


class TestSelectAdapter:
    """select_adapter 单元测试。"""

    def test_select_paper_returns_arxiv(self) -> None:
        """正常情况：PAPER 返回 ArxivAdapter 类。"""
        from rdi.adapters.arxiv import ArxivAdapter

        adapters = select_adapter(DataReqType.PAPER)
        assert ArxivAdapter in adapters

    def test_select_code_returns_github(self) -> None:
        """正常情况：CODE 返回 GitHubAdapter 类。"""
        from rdi.adapters.github import GitHubAdapter

        adapters = select_adapter(DataReqType.CODE)
        assert GitHubAdapter in adapters

    def test_select_returns_adapter_subclasses(self) -> None:
        """正常情况：返回的都是 BaseAdapter 子类。"""
        for req_type in DataReqType:
            adapters = select_adapter(req_type)
            for adapter_cls in adapters:
                assert issubclass(adapter_cls, BaseAdapter)

    def test_select_sensor_data_returns_github(self) -> None:
        """正常情况：SENSOR_DATA 返回 GitHubAdapter。"""
        from rdi.adapters.github import GitHubAdapter

        adapters = select_adapter(DataReqType.SENSOR_DATA)
        assert GitHubAdapter in adapters
