"""B↔C 第一次联调集成测试：验证 retrieve_data 节点接入真实 Adapter 的完整链路。"""

from unittest.mock import AsyncMock, Mock

import pytest

from rdi.exceptions import AdapterError
from rdi.graph.nodes.retrieve_data import node_retrieve_single
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


@pytest.fixture
def mock_hermes(monkeypatch):
    """用 Mock 替换懒加载的 HermesEngine 单例。"""
    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.record_experience = Mock()
    hermes.get_source_priority.return_value = ["github", "huggingface"]
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)
    return hermes


def make_mock_adapter(search_result=None, fetch_data=None, search_error=None, fetch_error=None):
    """创建 mock Adapter 实例。"""
    adapter = AsyncMock()
    if search_error:
        adapter.search.side_effect = search_error
    else:
        adapter.search.return_value = search_result or []
    if fetch_error:
        adapter.fetch.side_effect = fetch_error
    else:
        adapter.fetch.return_value = fetch_data
    return adapter


def make_mock_cls(adapter_instance, source=DataSource.GITHUB):
    """创建 mock Adapter 类（节点访问 cls.source.value，需在类上设 source）。"""
    cls = Mock(return_value=adapter_instance)
    cls.source = source
    return cls


def _search_result(item_id="repo/test", source=DataSource.GITHUB):
    return SearchResult(item_id=item_id, title="Test Repo", source=source)


def _raw_data(item_id="repo/test", source=DataSource.GITHUB):
    return RawData(source=source, item_id=item_id, format="zip", data=b"fake-bytes")


def _payload():
    return {
        "req_id": "req_001",
        "req_type": "code",
        "description": "查找代码",
        "keywords": ["test"],
    }


class TestRetrieveSingleSuccess:
    async def test_primary_source_success(self, mock_hermes, monkeypatch):
        """主源成功：search 返回结果，fetch 成功。"""
        adapter = make_mock_adapter(
            search_result=[_search_result()],
            fetch_data=_raw_data(),
        )
        cls = make_mock_cls(adapter, source=DataSource.GITHUB)
        monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [cls])

        result = await node_retrieve_single(_payload())

        retrieval = result["retrieval_results"]["req_001"]
        assert retrieval.status == "success"
        assert retrieval.is_fallback is False
        assert retrieval.data is not None


class TestRetrieveSingleFallback:
    async def test_primary_fail_fallback_success(self, mock_hermes, monkeypatch):
        """主源失败，fallback 成功。"""
        primary = make_mock_adapter(search_error=AdapterError("fail", source="github"))
        fallback_adapter = make_mock_adapter(
            search_result=[_search_result(item_id="hf/model", source=DataSource.HUGGINGFACE)],
            fetch_data=_raw_data(item_id="hf/model", source=DataSource.HUGGINGFACE),
        )
        primary_cls = make_mock_cls(primary, source=DataSource.GITHUB)
        fallback_cls = make_mock_cls(fallback_adapter, source=DataSource.HUGGINGFACE)
        monkeypatch.setattr(
            "rdi.graph.nodes.retrieve_data.select_adapter",
            lambda req_type: [primary_cls, fallback_cls],
        )

        result = await node_retrieve_single(_payload())

        retrieval = result["retrieval_results"]["req_001"]
        assert retrieval.status == "success"
        assert retrieval.is_fallback is True


class TestRetrieveSingleAllFail:
    async def test_all_adapters_fail(self, mock_hermes, monkeypatch):
        """全部 Adapter 失败。"""
        a1 = make_mock_adapter(search_error=AdapterError("fail1", source="github"))
        a2 = make_mock_adapter(search_error=AdapterError("fail2", source="huggingface"))
        c1 = make_mock_cls(a1, source=DataSource.GITHUB)
        c2 = make_mock_cls(a2, source=DataSource.HUGGINGFACE)
        monkeypatch.setattr(
            "rdi.graph.nodes.retrieve_data.select_adapter",
            lambda req_type: [c1, c2],
        )

        result = await node_retrieve_single(_payload())

        retrieval = result["retrieval_results"]["req_001"]
        assert retrieval.status == "error"
        assert retrieval.error_message != ""


class TestRetrieveSingleNoResults:
    async def test_no_search_results(self, mock_hermes, monkeypatch):
        """无搜索结果。"""
        a1 = make_mock_adapter(search_result=[])
        a2 = make_mock_adapter(search_result=[])
        c1 = make_mock_cls(a1, source=DataSource.GITHUB)
        c2 = make_mock_cls(a2, source=DataSource.HUGGINGFACE)
        monkeypatch.setattr(
            "rdi.graph.nodes.retrieve_data.select_adapter",
            lambda req_type: [c1, c2],
        )

        result = await node_retrieve_single(_payload())

        retrieval = result["retrieval_results"]["req_001"]
        assert retrieval.status == "missing"
