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
from rdi.exceptions import (
    AdapterCatalogError,
    AdapterNotFoundError,
    AdapterRateLimitError,
)
from rdi.graph.nodes.retrieve_data import node_retrieve_data, node_retrieve_single
from rdi.intelligence.schemas import RetrievalPlan
from rdi.models.common import DataReqType, DataSource, Priority
from rdi.models.goal import DataReq
from rdi.models.retrieval import RawData, RetrievalResult, SearchResult


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


@pytest.fixture(autouse=True)
def mock_plan_retrieval(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """默认把检索策略决策 mock 为降级（返回 None），避免既有用例触发真实 LLM 调用。

    需要验证 LLM 规划生效的用例再自行 monkeypatch 覆盖返回值。
    """
    mock = Mock(return_value=None)
    monkeypatch.setattr("rdi.intelligence.decisions.plan_retrieval", mock)
    return mock


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

    # 返回结构键齐全（② 起新增 retrieval_plan / llm_usage 合并字段）
    assert set(result) == {
        "retrieval_results",
        "provenance",
        "retrieval_errors",
        "retrieval_plan",
        "llm_usage",
    }
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
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])

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


# ─── C1: object_name 从 payload 透传到 adapter.fetch ───


async def test_retrieve_single_passes_object_name_to_fetch(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """C1：payload 带 object_name 时，fetch 以 object_name kwarg 调用（GraspNet 定位物体文件）。"""
    payload = {
        "req_id": "req_004",
        "req_type": "grasp",
        "description": "banana 的抓取标注",
        "keywords": ["banana", "grasp"],
        "object_name": "banana",
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_004"].status == "success"
    mock_adapters.fetch.assert_called_once_with(
        "test-1", req_type=DataReqType("grasp"), object_name="banana"
    )
    # object_name 作为额外 query token 参与 search
    assert "banana" in [call.args[0] for call in mock_adapters.search.call_args_list][0]


async def test_retrieve_single_omits_object_name_when_empty(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """C1：object_name 为空时不传该 kwarg，保持旧行为。"""
    payload = {
        "req_id": "req_005",
        "req_type": "robot_urdf",
        "description": "查找URDF",
        "keywords": [],
        "object_name": "",
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_005"].status == "success"
    mock_adapters.fetch.assert_called_once_with("test-1", req_type=DataReqType("robot_urdf"))


async def test_retrieve_single_fetch_falls_back_without_object_name_kwarg(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C1：fetch 不接受 object_name 的旧 Adapter 降级到 req_type 调用，不抛异常。"""
    calls: list[tuple[Any, ...]] = []

    class LegacyAdapter:
        source = DataSource.GITHUB

        async def search(self, query: str) -> list[SearchResult]:
            return [SearchResult(item_id="old-1", title="Old", source=DataSource.GITHUB)]

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            calls.append((item_id, req_type))
            return RawData(
                source=DataSource.GITHUB,
                item_id=item_id,
                format="json",
                data=b"legacy",
                url="https://example.com/old",
            )

    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [LegacyAdapter]
    )

    payload = {
        "req_id": "req_006",
        "req_type": "grasp",
        "description": "banana 的抓取标注",
        "keywords": [],
        "object_name": "banana",
    }
    result = await node_retrieve_single(payload)

    assert result["retrieval_results"]["req_006"].status == "success"
    # 第一次带 object_name 调用抛 TypeError（签名不支持）→ 降级为 req_type 调用
    assert calls[-1] == ("old-1", DataReqType("grasp"))


# ─── C5: 仅重跑失败 req（retry_req_ids 选择性处理） ───


def _two_req_state(
    retry_req_ids: list[str] | None, keep_result: RetrievalResult | None
) -> dict[str, Any]:
    """构造两个需求的 state：req_keep 有既有结果，req_retry 为失败重跑目标。"""
    state: dict[str, Any] = {
        "data_requirements": [
            DataReq(
                req_id="req_keep",
                req_type=DataReqType.CODE,
                description="已成功的需求",
                priority=Priority.REQUIRED,
                keywords=["keep"],
            ),
            DataReq(
                req_id="req_retry",
                req_type=DataReqType.CODE,
                description="需重跑的需求",
                priority=Priority.REQUIRED,
                keywords=["retry"],
            ),
        ]
    }
    if retry_req_ids is not None:
        state["retry_req_ids"] = retry_req_ids
    if keep_result is not None:
        state["retrieval_results"] = {"req_keep": keep_result}
    return state


async def test_retrieve_data_only_reruns_failed_reqs(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """retry_req_ids 设定时：只重跑失败 req，成功项不重拉、原结果保留。"""
    old_result = RetrievalResult(req_id="req_keep", status="success")
    state = _two_req_state(retry_req_ids=["req_retry"], keep_result=old_result)
    result = await node_retrieve_data(state)

    # req_keep 未重拉（其关键词未进入 search），req_retry 正常检索
    search_queries = [c.args[0] for c in mock_adapters.search.call_args_list]
    assert search_queries, "至少执行了一次检索"
    assert all("keep" not in q for q in search_queries)
    assert any("retry" in q for q in search_queries)
    # 返回结果同时含 req_keep（原值保留）与 req_retry（新结果）
    assert result["retrieval_results"]["req_keep"] is old_result
    assert result["retrieval_results"]["req_retry"].status == "success"
    # provenance 注明沿用不重拉
    assert any("沿用上一轮结果，不重拉 (req_keep)" in p for p in result["provenance"])


async def test_retrieve_data_reruns_all_when_no_retry_req_ids(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """retry_req_ids 为空（首次运行 / validate 重试）：全部重跑，既有结果被新结果覆盖（原行为）。"""
    old_result = RetrievalResult(req_id="req_keep", status="success")
    state = _two_req_state(retry_req_ids=None, keep_result=old_result)
    result = await node_retrieve_data(state)

    search_queries = [c.args[0] for c in mock_adapters.search.call_args_list]
    assert any("keep" in q for q in search_queries)
    assert any("retry" in q for q in search_queries)
    # 两个需求均重新检索：req_keep 原值被覆盖为新结果
    assert result["retrieval_results"]["req_keep"] is not old_result
    assert result["retrieval_results"]["req_keep"].status == "success"
    assert result["retrieval_results"]["req_retry"].status == "success"
    # 全部处理时不产生"沿用"溯源
    assert not any("沿用上一轮结果" in p for p in result["provenance"])


# ─── C2: 硬编码清单外目标可诊断（Task 8） ───


async def test_retrieve_single_catalog_error_yields_missing_with_diagnostics(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """C2：search 对清单外目标抛 AdapterCatalogError 时，missing 的 error_message 携带诊断语义。"""
    mock_adapter = AsyncMock()

    def _search_side_effect(query: str) -> list[SearchResult]:
        raise AdapterCatalogError(
            message="该源仅收录 20 个已知目标，未收录 'banana'（有源但未收录）",
            source="ycb",
        )

    mock_adapter.search.side_effect = _search_side_effect
    mock_cls = Mock(return_value=mock_adapter)
    mock_cls.source = DataSource.YCB
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])

    payload = {
        "req_id": "req_cat",
        "req_type": "grasp",
        "description": "banana 的抓取标注",
        "keywords": ["banana", "grasp"],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_cat"]
    assert retrieval.status == "missing"
    assert "该源仅收录" in retrieval.error_message
    assert "有源但未收录" in retrieval.error_message
    assert "ycb:" in retrieval.error_message
    # 清单外诊断不是连接类失败：不落入 retrieval_errors
    assert result["retrieval_errors"] == []


async def test_retrieve_single_catalog_error_then_query_hit_succeeds(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """C1 不回归：第一个 query 清单外抛 AdapterCatalogError，后续 query（物体名）命中时仍返回 success。"""

    def _search_side_effect(query: str) -> list[SearchResult]:
        if query == "banana grasp":
            raise AdapterCatalogError(
                message="该源仅收录 20 个已知目标，未收录 'banana grasp'（有源但未收录）",
                source="ycb",
            )
        if query == "banana":
            return [SearchResult(item_id="011_banana", title="Banana", source=DataSource.GITHUB)]
        return []

    mock_adapters.search.side_effect = _search_side_effect

    payload = {
        "req_id": "req_cat2",
        "req_type": "grasp",
        "description": "banana 的抓取标注",
        "keywords": ["banana", "grasp"],
        "object_name": "",
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_cat2"]
    assert retrieval.status == "success"
    assert retrieval.data is not None
    # 清单外诊断已累积但成功路径不受影响
    assert result["retrieval_errors"] == []


# ─── D2: 新类型无内置数据源 → 诚实失败（missing + 「该类型暂无内置数据源」） ───


@pytest.mark.parametrize(
    "new_type",
    [
        "camera_calib",
        "teaching_trajectory",
        "robot_config",
        "benchmark_task",
    ],
)
async def test_retrieve_single_new_type_missing_no_builtin_source(
    mock_hermes: Mock, new_type: str
) -> None:
    """D2：无内置 adapter 的新类型请求返回 missing，reason 含「该类型暂无内置数据源」。

    与 C2 的 AdapterCatalogError「有源但未收录」语义区分：这里是无内置数据源
    （未注册任何候选 Adapter），不塞 UNKNOWN、不误报为有源但未收录。
    """
    payload = {
        "req_id": "req_new",
        "req_type": new_type,
        "description": "测试新类型",
        "keywords": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_new"]
    assert retrieval.status == "missing"
    assert "该类型暂无内置数据源" in retrieval.error_message
    # 无源是缺失语义而非连接类错误：不落入 retrieval_errors
    assert result["retrieval_errors"] == []
    # 记录为 missing，且未使用任何源
    call_kwargs = mock_hermes.record_experience.call_args.kwargs
    assert call_kwargs["req_type"] == new_type
    assert call_kwargs["result_status"] == "missing"
    assert call_kwargs["sources_used"] == []


async def test_retrieve_data_new_type_missing_in_parallel(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """D2：并行检索中，无内置源的新类型需求与其他类型共存时各自正确返回。"""
    mock_adapter = AsyncMock()
    mock_adapter.search.return_value = [
        SearchResult(item_id="c-1", title="Code", source=DataSource.GITHUB)
    ]
    mock_adapter.fetch.return_value = RawData(
        source=DataSource.GITHUB,
        item_id="c-1",
        format="json",
        data=b"code",
        url="https://example.com",
    )
    mock_cls = Mock(return_value=mock_adapter)

    def _select(req_type: Any) -> list[Any]:
        if req_type == DataReqType.CODE:
            return [mock_cls]
        return []  # CAMERA_CALIB 等新类型无内置源

    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", _select)

    state: dict[str, Any] = {
        "data_requirements": [
            DataReq(
                req_id="req_known",
                req_type=DataReqType.CODE,
                description="查找代码",
                priority=Priority.REQUIRED,
                keywords=["code"],
            ),
            DataReq(
                req_id="req_calib",
                req_type=DataReqType.CAMERA_CALIB,
                description="标定相机参数",
                priority=Priority.REQUIRED,
                keywords=["标定"],
            ),
        ]
    }
    result = await node_retrieve_data(state)

    assert result["retrieval_results"]["req_known"].status == "success"
    calib = result["retrieval_results"]["req_calib"]
    assert calib.status == "missing"
    assert "该类型暂无内置数据源" in calib.error_message
    # 无源新类型不产生 retrieval_errors
    assert result["retrieval_errors"] == []


# ─── ② 检索策略规划（LLM 决策层） ───


async def test_retrieve_single_uses_llm_plan_queries_and_returns_plan(
    mock_hermes: Mock, mock_adapters: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """② LLM 搜索词置前、确定性 query 兜底在尾部；retrieval_plan/llm_usage 写入返回。"""
    plan = RetrievalPlan(
        queries=["foo bar"],
        preferred_sources=["github"],
        reason="r",
        confidence=0.9,
    )
    monkeypatch.setattr("rdi.intelligence.decisions.plan_retrieval", Mock(return_value=plan))

    def _search_side_effect(query: str) -> list[SearchResult]:
        # LLM 词先尝试（无结果），失败后兜底到确定性 query 并命中
        if query == "foo bar":
            return []
        return [SearchResult(item_id="test-1", title="Test", source=DataSource.GITHUB)]

    mock_adapters.search.side_effect = _search_side_effect

    payload = {
        "req_id": "req_plan",
        "req_type": "code",
        "description": "查找代码",
        "keywords": ["test"],
    }
    result = await node_retrieve_single(payload)

    # LLM 搜索词在最前，确定性 query 兜底在其后
    calls = [c.args[0] for c in mock_adapters.search.call_args_list]
    assert calls == ["foo bar", "test"]
    assert result["retrieval_results"]["req_plan"].status == "success"
    # 返回扩展字段
    assert result["retrieval_plan"]["req_plan"] is plan
    expected = {
        "decision": "retrieval_plan",
        "req_id": "req_plan",
        "status": "ok",
        "model": settings.llm_model,
    }
    assert expected.items() <= result["llm_usage"][0].items()
    assert isinstance(result["llm_usage"][0]["elapsed"], float)
    # 规划成功不产生降级溯源
    assert not any("检索策略 LLM 降级" in p for p in result["provenance"])


async def test_retrieve_single_llm_plan_fallback_keeps_deterministic_behavior(
    mock_hermes: Mock, mock_adapters: AsyncMock
) -> None:
    """② LLM 降级（返回 None）：provenance 记录降级、queries 仍以确定性 query 起步。"""
    payload = {
        "req_id": "req_fb",
        "req_type": "code",
        "description": "查找代码",
        "keywords": ["test"],
    }
    result = await node_retrieve_single(payload)

    assert any("检索策略 LLM 降级" in p for p in result["provenance"])
    calls = [c.args[0] for c in mock_adapters.search.call_args_list]
    assert calls[0] == "test"
    assert result["retrieval_plan"] == {}
    expected = {
        "decision": "retrieval_plan",
        "req_id": "req_fb",
        "status": "fallback",
        "model": settings.llm_model,
    }
    assert expected.items() <= result["llm_usage"][0].items()
    assert isinstance(result["llm_usage"][0]["elapsed"], float)


async def test_retrieve_data_merges_llm_plans_and_usage(
    mock_hermes: Mock, mock_adapters: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """② node_retrieve_data 合并各需求的 retrieval_plan 与 llm_usage。"""
    plan = RetrievalPlan(
        queries=["foo bar"],
        preferred_sources=["github"],
        reason="r",
        confidence=0.9,
    )
    monkeypatch.setattr("rdi.intelligence.decisions.plan_retrieval", Mock(return_value=plan))

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

    assert set(result["retrieval_plan"]) == {"req_p1", "req_p2"}
    assert all(result["retrieval_plan"][rid] is plan for rid in ("req_p1", "req_p2"))
    assert len(result["llm_usage"]) == 2
    assert all(
        u["decision"] == "retrieval_plan" and u["status"] == "ok" for u in result["llm_usage"]
    )


# ─── E6: 单源超时跳过后继候选源 ───


async def test_retrieve_single_source_timeout_falls_back_to_next_source(
    mock_hermes: Mock, monkeypatch: pytest.MonkeyPatch
) -> None:
    """E6: 首个候选源检索超时时，记录 timeout 错误并继续尝试下一个候选源。

    回归场景：GitHub 源（fallback 首选、国内网络慢）占满整个 per_req_timeout
    预算导致 Zenodo 无执行机会（package-20260812-163536 检索超时）。
    修复后每源均分子预算，GitHub 超时即跳过，Zenodo 仍能成功。
    """
    zenodo_mock = AsyncMock()
    zenodo_mock.search.return_value = [
        SearchResult(item_id="zo-1", title="Zenodo", source=DataSource.ZENODO)
    ]
    zenodo_mock.fetch.return_value = RawData(
        source=DataSource.ZENODO,
        item_id="zo-1",
        format="csv",
        data=b"timestamp,fx\n0,0.1\n",
        url="https://zenodo.org/zo-1",
    )

    class SlowGitHubAdapter:
        source = DataSource.GITHUB

        async def search(self, query: str) -> list[SearchResult]:
            await asyncio.sleep(0.5)  # 超过源级预算，模拟 GitHub API 挂起
            raise AssertionError("源级超时应已中断，不应到达这里")

    class FakeZenodoAdapter:
        source = DataSource.ZENODO

        async def search(self, query: str) -> list[SearchResult]:
            return await zenodo_mock.search(query)

        async def fetch(self, item_id: str, req_type: Any | None = None) -> RawData:
            return await zenodo_mock.fetch(item_id, req_type=req_type)

    # GitHub 优先（mock_hermes 默认优先级），但会源级超时；Zenodo 随后成功
    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter",
        lambda req_type: [SlowGitHubAdapter, FakeZenodoAdapter],
    )
    # per_req_timeout=0.05s、2 个源 → source_timeout=0.025s
    monkeypatch.setattr(settings, "per_req_timeout", 0.05)

    payload = {
        "req_id": "req_000",
        "req_type": "sensor_data",
        "description": "force torque sensor time series",
        "keywords": [],
        "fallback_sources": [],
    }
    result = await node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_000"]
    assert retrieval.status == "success"
    assert retrieval.source == DataSource.ZENODO
    # 源级超时被记录为 timeout 错误，但不阻塞后续源
    assert any(e.error_type == "timeout" for e in result["retrieval_errors"])
    zenodo_mock.search.assert_called_once()
