from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from unittest.mock import Mock

import pytest
import trimesh

from rdi.graph.builder import build_graph
from rdi.graph.nodes import parse_goal
from rdi.models import DataReq, DataReqType, DataSource, GoalSpec, Priority
from rdi.models.retrieval import RawData, RetrievalResult, SearchResult

if TYPE_CHECKING:
    from rdi.graph.state import SystemState


class _FakeLLMClient:
    def __init__(
        self, result: parse_goal._GoalParsingResult | None = None, exc: Exception | None = None
    ) -> None:
        self._result = result
        self._exc = exc
        self.last_prompt: str | None = None
        self.last_system: str | None = None

    def call_structured(self, prompt, schema, system=None):  # type: ignore[no-untyped-def]
        self.last_prompt = prompt
        self.last_system = system
        if self._exc is not None:
            raise self._exc
        return self._result


def _make_goal_parsing_result(req_id: str) -> parse_goal._GoalParsingResult:
    return parse_goal._GoalParsingResult(
        goal=GoalSpec(research_topic="机器人抓取实验", experiment_type="grasping"),
        requirements=[
            DataReq(
                req_id=req_id,
                req_type=DataReqType.MESH,
                description="机器人抓取场景 mesh 数据",
                priority=Priority.REQUIRED,
                keywords=["grasp", "robot", "mesh"],
            )
        ],
    )


def _make_mesh_adapter(mesh_bytes: bytes) -> type:
    class FakeAdapter:
        source = DataSource.GITHUB

        async def search(self, query: str) -> list[SearchResult]:
            return [
                SearchResult(
                    item_id="fake-mesh",
                    title="Fake mesh result",
                    source=DataSource.GITHUB,
                    url="https://example.com/fake-mesh",
                    pdf_url=None,
                    metadata={},
                )
            ]

        async def fetch(self, item_id: str) -> RawData:
            return RawData(
                source=DataSource.GITHUB,
                item_id=item_id,
                format="stl",
                data=mesh_bytes,
                url="https://example.com/fake-mesh",
                retrieved_at=datetime.now(),
                size_bytes=len(mesh_bytes),
            )

    return FakeAdapter


def _patch_full_workflow(monkeypatch: pytest.MonkeyPatch, mesh_bytes: bytes) -> None:
    fake_llm = _FakeLLMClient(result=_make_goal_parsing_result("req_000"))
    monkeypatch.setattr(parse_goal, "_get_llm_client", lambda: fake_llm)

    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.get_source_priority.return_value = [DataSource.GITHUB.value]
    hermes.record_experience = Mock()
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)

    fake_adapter_cls = _make_mesh_adapter(mesh_bytes)
    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.select_adapter",
        lambda req_type: [fake_adapter_cls],
    )

    # LangGraph 节点要求返回 dict 类型；为了在集成 mock 中跳过 fan-out 实际执行，
    # 将 node_retrieve_data 替换为返回空更新的函数，避免 Send 列表导致的 InvalidUpdateError。
    def _fake_node_retrieve_data(state: dict) -> dict:
        # 为每条 data_requirements 构造一个 RetrievalResult，绕过真实 Adapter
        reqs = state.get("data_requirements", [])
        results: dict[str, RetrievalResult] = {}
        for req in reqs:
            raw = RawData(
                source=DataSource.GITHUB,
                item_id="fake-mesh",
                format="stl",
                data=mesh_bytes,
                url="https://example.com/fake-mesh",
                retrieved_at=datetime.now(),
                size_bytes=len(mesh_bytes),
            )
            results[req.req_id] = RetrievalResult(
                req_id=req.req_id,
                status="success",
                data=raw,
                source=raw.source,
                is_fallback=False,
                search_results=[],
                elapsed_seconds=0.1,
            )
        return {
            "retrieval_results": results,
            "provenance": [f"[{datetime.now().isoformat()}] mock retrieve"],
        }

    monkeypatch.setattr(
        "rdi.graph.nodes.retrieve_data.node_retrieve_data", _fake_node_retrieve_data
    )
    # builder 模块在导入时已绑定 node_retrieve_data，需同时替换 builder 中的引用
    monkeypatch.setattr("rdi.graph.builder.node_retrieve_data", _fake_node_retrieve_data)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_parse_goal_to_data_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    """验证 user_goal 能被解析为 data_requirements。"""
    mesh = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    mesh_bytes = mesh.export(file_type="stl")
    _patch_full_workflow(monkeypatch, mesh_bytes)

    graph = build_graph()
    state: SystemState = {
        "user_goal": "我需要一篇关于机器人抓取的论文",
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
    }

    result = await graph.ainvoke(
        state,
        thread_id="test",
        checkpoint_ns="integration",
        checkpoint_id="run",
    )

    assert "data_requirements" in result
    assert len(result["data_requirements"]) > 0
    assert result["experiment_package"].package_info["goal"] == "我需要一篇关于机器人抓取的论文"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_full_workflow_mocks(monkeypatch: pytest.MonkeyPatch) -> None:
    """用 mock 验证全链路结构，不依赖真实 API。"""
    mesh = trimesh.creation.box(extents=(0.1, 0.1, 0.1))
    mesh_bytes = mesh.export(file_type="stl")
    _patch_full_workflow(monkeypatch, mesh_bytes)

    graph = build_graph()
    state: SystemState = {
        "user_goal": "我需要一篇关于机器人抓取的论文",
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
    }

    result = await graph.ainvoke(
        state,
        thread_id="test",
        checkpoint_ns="integration",
        checkpoint_id="run",
    )

    assert "experiment_package" in result
    assert result["experiment_package"].package_info["goal"] == "我需要一篇关于机器人抓取的论文"
    assert result["validation_issues"] == []
    assert result["review_decision"] == "satisfied"
    # 在 mock 场景中关注流水线结果，溯源至少应包含若干条记录
    assert result.get("provenance")
