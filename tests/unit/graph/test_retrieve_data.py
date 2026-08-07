"""retrieve_data 节点的单元测试。

验证节点接入真实 Adapter 后：
1. 查找前调用 ``HermesEngine.inject_experience``；
2. 查找后调用 ``HermesEngine.record_experience``；
3. 返回真实 ``RetrievalResult``（由候选 Adapter 的 search → fetch 链路产生）。
"""

from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from rdi.graph.nodes.retrieve_data import node_retrieve_single
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


@pytest.fixture
def mock_hermes(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """用 Mock 替换懒加载的 HermesEngine 单例。"""
    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.record_experience = Mock()
    hermes.get_source_priority.return_value = ["github"]
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)
    return hermes


@pytest.fixture
def mock_adapters(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """创建 mock Adapter 类，替换 select_adapter 返回真实候选链路。"""
    mock_adapter = AsyncMock()
    mock_adapter.search.return_value = [
        SearchResult(item_id="test-1", title="Test", source=DataSource.GITHUB)
    ]
    mock_adapter.fetch.return_value = RawData(
        source=DataSource.GITHUB,
        item_id="test-1",
        format="json",
        data=b"test data",
        url="https://example.com",
    )
    mock_cls = Mock(return_value=mock_adapter)
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])
    return mock_adapter


async def test_retrieve_single_calls_hermes_inject_and_record(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """验证 inject_experience 与 record_experience 均被正确调用。"""
    payload = {
        "req_id": "req_000",
        "req_type": "code",
        "description": "查找代码",
        "keywords": ["test"],
    }
    result = await node_retrieve_single(payload)

    # 验证 inject_experience 被调用
    mock_hermes.inject_experience.assert_called_once_with("查找代码", "code")

    # 验证 record_experience 被调用
    mock_hermes.record_experience.assert_called_once()
    call_kwargs = mock_hermes.record_experience.call_args.kwargs
    assert call_kwargs["task_desc"] == "查找代码"
    assert call_kwargs["req_type"] == "code"
    assert call_kwargs["result_status"] == "success"
    assert call_kwargs["sources_used"] == ["github"]
    assert call_kwargs["elapsed_seconds"] > 0

    # 验证返回结构正确
    assert "retrieval_results" in result
    assert "req_000" in result["retrieval_results"]
    assert result["retrieval_results"]["req_000"].status == "success"


async def test_retrieve_single_returns_success_result(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """验证节点返回真实 RetrievalResult（由 Adapter search → fetch 产生）。"""
    payload = {
        "req_id": "req_001",
        "req_type": "robot_urdf",
        "description": "查找URDF",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_001"]
    assert retrieval.req_id == "req_001"
    assert retrieval.status == "success"
    assert retrieval.data is not None
    assert retrieval.data.item_id == "test-1"
    assert retrieval.data.source == DataSource.GITHUB
    assert retrieval.source == DataSource.GITHUB
    assert retrieval.search_results[0].item_id == "test-1"
    assert "provenance" in result


async def test_retrieve_single_uses_fallback_sources_order(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """当 DataReq 提供 fallback_sources 时，按该顺序优先尝试源。"""
    github_mock = AsyncMock()
    github_mock.search.return_value = [
        SearchResult(item_id="gh-1", title="GitHub", source=DataSource.GITHUB)
    ]
    github_mock.fetch.return_value = RawData(
        source=DataSource.GITHUB,
        item_id="gh-1",
        format="urdf",
        data=b"github urdf",
        url="https://example.com/gh",
    )

    franka_mock = AsyncMock()
    franka_mock.search.return_value = [
        SearchResult(item_id="fr-1", title="Franka", source=DataSource.FRANKA)
    ]
    franka_mock.fetch.return_value = RawData(
        source=DataSource.FRANKA,
        item_id="fr-1",
        format="urdf",
        data=b"franka urdf",
        url="https://example.com/fr",
    )

    class FakeGitHubAdapter:
        source = DataSource.GITHUB

        async def search(self, query: str) -> list[SearchResult]:
            return await github_mock.search(query)

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            return await github_mock.fetch(item_id, req_type=req_type)

    class FakeFrankaAdapter:
        source = DataSource.FRANKA

        async def search(self, query: str) -> list[SearchResult]:
            return await franka_mock.search(query)

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            return await franka_mock.fetch(item_id, req_type=req_type)

    # registry 默认顺序是 github 优先；fallback 要求 franka 优先
    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter",
        lambda req_type: [FakeGitHubAdapter, FakeFrankaAdapter],
    )

    payload = {
        "req_id": "req_000",
        "req_type": "robot_urdf",
        "description": "Franka URDF",
        "keywords": [],
        "fallback_sources": ["franka", "github"],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_000"]
    assert retrieval.status == "success"
    assert retrieval.source == DataSource.FRANKA
    franka_mock.search.assert_called_once()
    github_mock.search.assert_not_called()
