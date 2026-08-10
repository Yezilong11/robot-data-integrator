"""retrieve_data 节点的单元测试。

验证节点接入真实 Adapter 后：
1. 查找前调用 ``HermesEngine.inject_experience``；
2. 查找后调用 ``HermesEngine.record_experience``；
3. 返回真实 ``RetrievalResult``（由候选 Adapter 的 search → fetch 链路产生）。
"""

import asyncio
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest

from rdi.config.settings import settings
from rdi.exceptions import AdapterNotFoundError, AdapterRateLimitError
from rdi.graph.nodes.retrieve_data import node_retrieve_data, node_retrieve_single
from rdi.models.common import DataReqType, DataSource, Priority
from rdi.models.goal import DataReq
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


async def test_retrieve_single_uses_keywords_for_search_query(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """C2-fix: 有 keywords 时优先用 keywords 拼接作为 search query，而不是中文 description。"""
    payload = {
        "req_id": "req_001",
        "req_type": "robot_urdf",
        "description": "Franka Panda 机器人的 URDF 描述文件",
        "keywords": ["Franka", "Panda", "URDF"],
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_001"].status == "success"
    # search 应该用英文关键词，而不是中文长描述
    mock_adapters.search.assert_called_once_with("Franka Panda URDF")


async def test_retrieve_single_falls_back_to_description_when_keywords_empty(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """keywords 为空时，应回退到 description 作为 search query。"""
    payload = {
        "req_id": "req_002",
        "req_type": "robot_urdf",
        "description": "查找URDF",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_002"].status == "success"
    mock_adapters.search.assert_called_once_with("查找URDF")


async def test_retrieve_single_returns_success_result(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """验证节点返回真实 RetrievalResult（由 Adapter search → fetch 产生）。"""
    payload = {
        "req_id": "req_003",
        "req_type": "robot_urdf",
        "description": "查找URDF",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_003"]
    assert retrieval.req_id == "req_003"
    assert retrieval.status == "success"
    assert retrieval.data is not None
    assert retrieval.data.item_id == "test-1"
    assert retrieval.data.source == DataSource.GITHUB
    assert retrieval.source == DataSource.GITHUB
    assert retrieval.search_results[0].item_id == "test-1"
    assert "provenance" in result


async def test_retrieve_single_augments_sim_config_with_context_keywords(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """sim_config 查找时，应将机器人/物体名称等上下文关键词加入 search query。"""

    def _search_side_effect(query: str) -> list[SearchResult]:
        # 仅当组合查询命中上下文关键词时才返回结果，验证 augment 生效
        if "Franka" in query and "Panda" in query:
            return [
                SearchResult(item_id="scene-1", title="Franka MuJoCo", source=DataSource.GITHUB)
            ]
        return []

    mock_adapters.search.side_effect = _search_side_effect

    payload = {
        "req_id": "req_sim",
        "req_type": "sim_config",
        "description": "MuJoCo 仿真环境",
        "keywords": ["MuJoCo"],
        "context_keywords": ["Franka", "Panda", "hand"],
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_sim"].status == "success"
    calls = [call.args[0] for call in mock_adapters.search.call_args_list]
    # 应依次尝试：完整 query、组合上下文 query、原始 keyword、上下文 keyword
    assert calls[0] == "MuJoCo"
    assert "MuJoCo" in calls[1] and "Franka" in calls[1] and "Panda" in calls[1]
    assert any("Franka" in c and "Panda" in c for c in calls)


async def test_retrieve_single_records_rate_limit_error(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adapter fetch 抛 AdapterRateLimitError(429) 时，retrieval_errors 记录 error_type=rate_limit。"""
    mock_adapter = AsyncMock()
    mock_adapter.search.return_value = [
        SearchResult(item_id="rl-1", title="RL", source=DataSource.GITHUB)
    ]
    mock_adapter.fetch.side_effect = AdapterRateLimitError(
        "rate limited", source="github", status_code=429
    )
    mock_cls = Mock(return_value=mock_adapter)
    mock_cls.source = DataSource.GITHUB
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])

    payload = {
        "req_id": "req_rl",
        "req_type": "code",
        "description": "查找代码",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_rl"]
    assert retrieval.status == "error"
    errors = result["retrieval_errors"]
    assert len(errors) == 1
    assert errors[0].req_id == "req_rl"
    assert errors[0].source == DataSource.GITHUB
    assert errors[0].error_type == "rate_limit"
    assert "github:rate_limit" in retrieval.error_message


async def test_retrieve_single_records_not_found_error(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Adapter fetch 抛 AdapterNotFoundError(404) 时，retrieval_errors 记录 error_type=not_found。"""
    mock_adapter = AsyncMock()
    mock_adapter.search.return_value = [
        SearchResult(item_id="nf-1", title="NF", source=DataSource.GITHUB)
    ]
    mock_adapter.fetch.side_effect = AdapterNotFoundError(
        "not found", source="github", status_code=404
    )
    mock_cls = Mock(return_value=mock_adapter)
    mock_cls.source = DataSource.GITHUB
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])

    payload = {
        "req_id": "req_nf",
        "req_type": "code",
        "description": "查找代码",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_nf"]
    assert retrieval.status == "error"
    errors = result["retrieval_errors"]
    assert len(errors) == 1
    assert errors[0].error_type == "not_found"
    assert errors[0].error_message
    assert "github:not_found" in retrieval.error_message


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


async def test_retrieve_single_uses_hermes_priority_for_all_candidates(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hermes 动态优先级对全部候选源生效：注册表顺序 github 在前，但 Hermes 认为 ieee 更可靠时应先尝试 ieee。"""
    github_mock = AsyncMock()
    github_mock.search.return_value = [
        SearchResult(item_id="gh-1", title="GitHub", source=DataSource.GITHUB)
    ]
    github_mock.fetch.return_value = RawData(
        source=DataSource.GITHUB,
        item_id="gh-1",
        format="code",
        data=b"github code",
        url="https://example.com/gh",
    )

    ieee_mock = AsyncMock()
    ieee_mock.search.return_value = [
        SearchResult(item_id="ieee-1", title="IEEE", source=DataSource.IEEE)
    ]
    ieee_mock.fetch.return_value = RawData(
        source=DataSource.IEEE,
        item_id="ieee-1",
        format="code",
        data=b"ieee code",
        url="https://example.com/ieee",
    )

    class FakeGitHubAdapter:
        source = DataSource.GITHUB

        async def search(self, query: str) -> list[SearchResult]:
            return await github_mock.search(query)

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            return await github_mock.fetch(item_id, req_type=req_type)

    class FakeIEEEAdapter:
        source = DataSource.IEEE

        async def search(self, query: str) -> list[SearchResult]:
            return await ieee_mock.search(query)

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            return await ieee_mock.fetch(item_id, req_type=req_type)

    # 注册表顺序 github 优先，但 Hermes 历史成功率认为 ieee 更可靠
    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter",
        lambda req_type: [FakeGitHubAdapter, FakeIEEEAdapter],
    )
    mock_hermes.get_source_priority.return_value = ["ieee", "github"]

    payload = {
        "req_id": "req_000",
        "req_type": "code",
        "description": "查找代码",
        "keywords": [],
        "fallback_sources": [],
    }
    result = await node_retrieve_single(payload)

    # req_type 与候选源均传给 Hermes
    mock_hermes.get_source_priority.assert_called_once()
    assert mock_hermes.get_source_priority.call_args.args[0] == "code"
    retrieval = result["retrieval_results"]["req_000"]
    assert retrieval.status == "success"
    assert retrieval.source == DataSource.IEEE
    ieee_mock.search.assert_called_once()
    github_mock.search.assert_not_called()


# ─── Task 7：node_retrieve_data 并行检索 + 独立超时预算 ───


async def test_retrieve_data_parallel_merges_all_reqs(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """并行汇总：多个需求并行执行后 retrieval_results 全部存在、errors 合并、返回键齐全。"""
    state: dict[str, Any] = {
        "data_requirements": [
            DataReq(
                req_id="req_p1",
                req_type=DataReqType.CODE,
                description="查找抓取代码",
                priority=Priority.REQUIRED,
                keywords=["grasp"],
            ),
            DataReq(
                req_id="req_p2",
                req_type=DataReqType.PAPER,
                description="查找抓取论文",
                priority=Priority.REQUIRED,
                keywords=["grasp"],
            ),
        ]
    }
    result = await node_retrieve_data(state)

    # 返回结构键齐全
    assert set(result) == {"retrieval_results", "provenance", "retrieval_errors"}
    # 两个需求的检索结果都存在（gather 保持输入顺序，与 requirements 一致）
    assert set(result["retrieval_results"]) == {"req_p1", "req_p2"}
    assert result["retrieval_results"]["req_p1"].status == "success"
    assert result["retrieval_results"]["req_p2"].status == "success"
    # 无失败时 errors 为空、provenance 每个需求至少一条
    assert result["retrieval_errors"] == []
    assert len(result["provenance"]) >= 2


async def test_retrieve_data_per_req_timeout_does_not_block_others(
    mock_hermes: Mock, mock_adapters: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单需求超时不阻塞整体：慢需求记为 timeout 失败，其他需求正常返回。"""
    # 把超时预算压到极小值，制造慢需求必然超时的场景
    monkeypatch.setattr(settings, "per_req_timeout", 0.05)
    # 重新注册带真实 source 的候选 adapter：超时错误的 source 需要真实 DataSource 值
    mock_cls = Mock(return_value=mock_adapters)
    mock_cls.source = DataSource.GITHUB
    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls]
    )

    original_single = node_retrieve_single

    async def _slow_single(payload: dict[str, Any]) -> dict[str, Any]:
        if payload["req_id"] == "req_slow":
            await asyncio.sleep(0.2)  # 远超 0.05s 超时预算
        return await original_single(payload)

    # patch 模块内引用：node_retrieve_data 经 _retrieve_single_with_timeout 调用它
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.node_retrieve_single", _slow_single)

    state: dict[str, Any] = {
        "data_requirements": [
            DataReq(
                req_id="req_slow",
                req_type=DataReqType.CODE,
                description="慢需求",
                priority=Priority.REQUIRED,
                keywords=[],
            ),
            DataReq(
                req_id="req_fast",
                req_type=DataReqType.CODE,
                description="快需求",
                priority=Priority.REQUIRED,
                keywords=["fast"],
            ),
        ]
    }
    result = await node_retrieve_data(state)  # 整体不抛异常

    # 慢需求：timeout 型失败，不阻塞整体
    slow = result["retrieval_results"]["req_slow"]
    assert slow.status == "error"
    assert "超时" in slow.error_message
    # 快需求：不受影响，正常成功
    fast = result["retrieval_results"]["req_fast"]
    assert fast.status == "success"
    # retrieval_errors 含 timeout 类型记录
    timeout_errors = [
        e
        for e in result["retrieval_errors"]
        if e.req_id == "req_slow" and e.error_type == "timeout"
    ]
    assert len(timeout_errors) == 1
    assert "超时" in timeout_errors[0].error_message
