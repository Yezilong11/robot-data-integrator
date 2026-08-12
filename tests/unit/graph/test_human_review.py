"""human_review 节点单元测试。

覆盖三种决策闭环与循环上限：
- satisfied → 结束（不触发重检索）；
- revised → 调用 LLM 反馈转换、写入 revised_goal / user_goal、路由到 parse_goal；
- unsatisfied → 生成重检索建议、路由到 retrieve_data；
- LLM 不可用时降级使用反馈原文；
- 循环上限：第 4 次进入时强制按 satisfied 结束。
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from rdi.config.settings import settings
from rdi.exceptions import LLMUnavailableError
from rdi.graph.edges import route_after_review
from rdi.graph.nodes import human_review
from rdi.graph.nodes.assemble import node_assemble
from rdi.models import DataReq, DataReqType, MissingItem, Priority, RetrievalError
from rdi.models.common import DataSource

if TYPE_CHECKING:
    from pathlib import Path

    from rdi.graph.state import SystemState


class _FakeLLMClient:
    """模拟 LLMClient，记录调用并可注入异常。"""

    def __init__(self, result: Any = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls: list[tuple[str, Any, str | None]] = []

    def call_structured(self, prompt: str, schema: Any, system: str | None = None) -> Any:
        self.calls.append((prompt, schema, system))
        if self._exc is not None:
            raise self._exc
        return self._result


def _patch_llm(monkeypatch: pytest.MonkeyPatch, fake: _FakeLLMClient) -> None:
    monkeypatch.setattr(human_review, "_get_llm_client", lambda: fake)


def _run(state: SystemState) -> tuple[SystemState, dict[str, Any]]:
    """执行节点并合并更新，返回 (合并后的 state, 节点返回的 update dict)。"""
    update = human_review.node_human_review(state)
    merged: SystemState = dict(state)
    merged.update(update)
    return merged, update


def _base_state(decision: str = "satisfied", **extra: Any) -> SystemState:
    state: SystemState = {
        "user_goal": "用 Franka Panda 在 MuJoCo 中抓取 YCB banana",
        "review_decision": decision,
        "user_feedback": [],
        "review_iteration": 0,
        "retrieval_results": {"req_000": None},
        "provenance": [],
        "errors": [],
    }
    state.update(extra)
    return state


# ─── satisfied ───


def test_satisfied_ends_flow() -> None:
    """satisfied：provenance 记录后结束，不调用 LLM、不写 revised_goal。"""
    state = _base_state("satisfied", user_feedback=["不错"])
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch=pytest.MonkeyPatch(), fake=fake)  # 占位，便于一致性
    merged, update = _run(state)

    assert merged["review_decision"] == "satisfied"
    assert route_after_review(merged) == "satisfied"
    assert "revised_goal" not in update
    assert "user_goal" not in update
    assert any("审查决定为 satisfied" in p for p in merged["provenance"])
    # satisfied 不触发重检索，旧检索结果保留
    assert merged["retrieval_results"] is state["retrieval_results"]
    assert fake.calls == []
    # 纯 satisfied 不追加修订记录
    assert "revision_history" not in update


# ─── revised ───


def test_revised_calls_llm_writes_revised_goal_and_routes_to_parse_goal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """revised：调用反馈转换 LLM，写入 revised_goal / user_goal，路由到 parse_goal。"""
    fake = _FakeLLMClient(
        result=human_review._RevisedGoal(revised_goal="用 UR5 在 PyBullet 中抓取 YCB mug")
    )
    _patch_llm(monkeypatch, fake)

    state = _base_state("revised", user_feedback=["换 UR5 和 PyBullet", "物体换成 mug"])
    merged, update = _run(state)

    assert fake.calls, "revised 分支必须调用 LLM 反馈转换"
    assert merged["review_decision"] == "revised"
    assert route_after_review(merged) == "revised"
    assert update["revised_goal"] == "用 UR5 在 PyBullet 中抓取 YCB mug"
    assert merged["user_goal"] == "用 UR5 在 PyBullet 中抓取 YCB mug"
    # 保留成功检索结果（只重跑失败项，不整体清空）
    assert merged["retrieval_results"] == state["retrieval_results"]
    assert "retrieval_results" not in update
    assert any("回到 parse_goal" in p for p in merged["provenance"])


def test_revised_llm_unavailable_falls_back_to_feedback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """LLM 不可用时降级：直接用用户反馈原文作为修正目标，不崩溃。"""
    fake = _FakeLLMClient(exc=LLMUnavailableError("LLM 服务不可用", model="fake"))
    _patch_llm(monkeypatch, fake)

    state = _base_state("revised", user_feedback=["换成 DexGraspNet 数据"])
    merged, update = _run(state)

    assert merged["review_decision"] == "revised"
    assert "修正要求：换成 DexGraspNet 数据" in update["revised_goal"]
    assert route_after_review(merged) == "revised"
    assert any("用户反馈: 换成 DexGraspNet 数据" in p for p in merged["provenance"])


# ─── unsatisfied ───


def test_unsatisfied_routes_to_retrieve_data(monkeypatch: pytest.MonkeyPatch) -> None:
    """unsatisfied：生成重检索建议写入 revised_goal，路由到 retrieve_data。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)

    state = _base_state("unsatisfied", user_feedback=["数据源不对，要真实 DexGraspNet 数据"])
    merged, update = _run(state)

    assert merged["review_decision"] == "unsatisfied"
    assert route_after_review(merged) == "unsatisfied"
    assert "重检索建议" in update["revised_goal"]
    assert "DexGraspNet" in update["revised_goal"]
    # 保留成功检索结果（只重跑失败项，不整体清空）
    assert merged["retrieval_results"] == state["retrieval_results"]
    assert "retrieval_results" not in update
    # unsatisfied 不调用 LLM（规则生成建议）
    assert fake.calls == []
    assert any("回到 retrieve_data" in p for p in merged["provenance"])


def test_unsatisfied_without_feedback_has_default_advice(monkeypatch: pytest.MonkeyPatch) -> None:
    """unsatisfied 且无反馈时给出默认建议。"""
    _patch_llm(monkeypatch, _FakeLLMClient())
    merged, update = _run(_base_state("unsatisfied"))
    assert "更换数据源" in update["revised_goal"]
    assert merged["review_decision"] == "unsatisfied"


# ─── C5: retry_req_ids（仅重跑失败 req） ───


def _failed_state(decision: str) -> SystemState:
    """构造含失败项的 state：missing_items 与 retrieval_errors 中 req_001 重复（验证去重）。"""
    return _base_state(
        decision,
        missing_items=[
            MissingItem(
                req_id="req_001",
                req_type=DataReqType.MESH,
                description="banana mesh",
                reason="未找到",
            )
        ],
        retrieval_errors=[
            RetrievalError(
                req_id="req_001",
                source=DataSource.GITHUB,
                error_type="not_found",
                error_message="404",
            ),
            RetrievalError(
                req_id="req_002",
                source=DataSource.GITHUB,
                error_type="timeout",
                error_message="超时",
            ),
        ],
    )


def test_unsatisfied_sets_retry_req_ids_dedup_and_keeps_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """unsatisfied：retry_req_ids 从 missing_items + retrieval_errors 收集并去重；不再清空 retrieval_results。"""
    _patch_llm(monkeypatch, _FakeLLMClient())
    state = _failed_state("unsatisfied")
    merged, update = _run(state)

    # 去重：req_001 同时在 missing_items 与 retrieval_errors 中，只出现一次
    assert update["retry_req_ids"] == ["req_001", "req_002"]
    # 不再清空检索结果：update 不含 retrieval_results 键，原值保留
    assert "retrieval_results" not in update
    assert merged["retrieval_results"] == state["retrieval_results"]
    # provenance 注明仅重跑失败 req
    assert any("仅重跑失败 req: req_001, req_002" in p for p in merged["provenance"])


def test_revised_sets_retry_req_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """revised：同样写入 retry_req_ids（仅重跑失败 req），成功项保留。"""
    fake = _FakeLLMClient(
        result=human_review._RevisedGoal(revised_goal="用 UR5 在 PyBullet 中抓取 mug")
    )
    _patch_llm(monkeypatch, fake)
    state = _failed_state("revised")
    merged, update = _run(state)

    assert update["retry_req_ids"] == ["req_001", "req_002"]
    assert "retrieval_results" not in update
    assert merged["retrieval_results"] == state["retrieval_results"]
    assert any("仅重跑失败 req: req_001, req_002" in p for p in merged["provenance"])


def test_satisfied_does_not_set_retry_req_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """satisfied：不触发重跑，不产生 retry_req_ids。"""
    _patch_llm(monkeypatch, _FakeLLMClient())
    merged, update = _run(_failed_state("satisfied"))

    assert merged["review_decision"] == "satisfied"
    assert "retry_req_ids" not in update
    assert "retrieval_results" not in update


# ─── 循环上限 ───


@pytest.mark.parametrize("iteration", [3, 4])
def test_loop_cap_force_ends_on_4th_review(iteration: int, monkeypatch: pytest.MonkeyPatch) -> None:
    """review_iteration 达到上限（>=3，即第 4 次进入）时：即使 review_decision 为 revised 也强制按 satisfied 结束。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)

    state = _base_state("revised", review_iteration=iteration, user_feedback=["再来一次"])
    merged, update = _run(state)

    assert merged["review_decision"] == "satisfied"
    assert route_after_review(merged) == "satisfied"
    assert "revised_goal" not in update
    assert any("强制结束" in p for p in merged["provenance"])
    # 强制结束时不再调用 LLM
    assert fake.calls == []


def test_loop_cap_not_reached_still_allows_revision(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """未超过上限（review_iteration=2，第 3 轮）仍允许修订。"""
    fake = _FakeLLMClient(result=human_review._RevisedGoal(revised_goal="修正目标"))
    _patch_llm(monkeypatch, fake)

    merged, _ = _run(_base_state("revised", review_iteration=2, user_feedback=["微调"]))

    assert merged["review_decision"] == "revised"
    assert merged["revised_goal"] == "修正目标"
    assert fake.calls


# ─── 边界 ───


def test_unknown_decision_treated_as_satisfied(monkeypatch: pytest.MonkeyPatch) -> None:
    """未知 decision 防御性视为 satisfied。"""
    _patch_llm(monkeypatch, _FakeLLMClient())
    merged, update = _run(_base_state("whatever"))
    assert merged["review_decision"] == "satisfied"
    assert route_after_review(merged) == "satisfied"
    assert "revised_goal" not in update


def test_missing_decision_defaults_to_satisfied(monkeypatch: pytest.MonkeyPatch) -> None:
    """state 无 review_decision 时默认 satisfied。"""
    _patch_llm(monkeypatch, _FakeLLMClient())
    state: SystemState = {"user_goal": "目标", "provenance": []}
    merged, _ = _run(state)
    assert merged["review_decision"] == "satisfied"
    assert route_after_review(merged) == "satisfied"


# ─── revision_history ───


def test_revised_records_revision_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """revised：revision_history 追加一条字段齐全的记录，update 返回完整列表。"""
    fake = _FakeLLMClient(
        result=human_review._RevisedGoal(revised_goal="用 UR5 在 PyBullet 中抓取 YCB mug")
    )
    _patch_llm(monkeypatch, fake)

    state = _base_state("revised", user_feedback=["换 UR5 和 PyBullet", "物体换成 mug"])
    merged, update = _run(state)

    history = merged["revision_history"]
    assert len(history) == 1
    record = history[0]
    assert record["revision"] == 1
    assert record["decision"] == "revised"
    assert record["feedback"] == ["换 UR5 和 PyBullet", "物体换成 mug"]
    assert record["revised_goal"] == "用 UR5 在 PyBullet 中抓取 YCB mug"
    assert record["timestamp"]  # ISO 时间戳非空
    # 节点返回完整 revision_history（旧列表 + 新记录），而非仅新记录
    assert update["revision_history"] == history


def test_revision_history_appends_to_existing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """已有修订记录时：revision 序号接续，旧记录原样保留。"""
    fake = _FakeLLMClient(result=human_review._RevisedGoal(revised_goal="v2 目标"))
    _patch_llm(monkeypatch, fake)

    existing = [
        {
            "revision": 1,
            "decision": "revised",
            "feedback": ["第一轮"],
            "revised_goal": "v1 目标",
            "timestamp": "2026-07-23T12:00:00",
        }
    ]
    state = _base_state("revised", user_feedback=["第二轮"], revision_history=existing)
    merged, _ = _run(state)

    history = merged["revision_history"]
    assert len(history) == 2
    assert history[0] == existing[0]
    assert history[1]["revision"] == 2
    assert history[1]["decision"] == "revised"
    assert history[1]["feedback"] == ["第二轮"]


def test_unsatisfied_records_revision_history(monkeypatch: pytest.MonkeyPatch) -> None:
    """unsatisfied：revision_history 追加一条记录，revised_goal 为重检索建议。"""
    _patch_llm(monkeypatch, _FakeLLMClient())

    state = _base_state("unsatisfied", user_feedback=["数据源不对，要真实 DexGraspNet 数据"])
    merged, update = _run(state)

    history = merged["revision_history"]
    assert len(history) == 1
    record = history[0]
    assert record["revision"] == 1
    assert record["decision"] == "unsatisfied"
    assert record["feedback"] == ["数据源不对，要真实 DexGraspNet 数据"]
    assert "重检索建议" in record["revised_goal"]
    assert record["timestamp"]
    assert update["revision_history"] == history


def test_loop_cap_records_forced_revision(monkeypatch: pytest.MonkeyPatch) -> None:
    """循环上限强制结束时仍记录一次修订（decision=satisfied (forced)），便于追溯。"""
    _patch_llm(monkeypatch, _FakeLLMClient())

    state = _base_state("revised", review_iteration=4, user_feedback=["再来一次"])
    merged, update = _run(state)

    assert merged["review_decision"] == "satisfied"
    history = merged["revision_history"]
    assert len(history) == 1
    record = history[0]
    assert record["revision"] == 1
    assert record["decision"] == "satisfied (forced)"
    assert record["feedback"] == ["再来一次"]
    assert record["revised_goal"] == state["user_goal"]  # 未应用的反馈，保留当前生效目标
    assert record["timestamp"]


# ─── interrupt 真实流程 ───


def test_interrupt_review_waits_for_resume_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    """interrupt_review=True 时调用 interrupt 等待用户决策，且不读 state.review_decision。"""
    fake = _FakeLLMClient()
    _patch_llm(monkeypatch, fake)
    calls: list[Any] = []

    def _fake_interrupt(payload: Any) -> dict[str, Any]:
        calls.append(payload)
        return {"decision": "satisfied", "feedback": ["x"]}

    monkeypatch.setattr(human_review, "interrupt", _fake_interrupt)

    # state.review_decision 预置为 revised，但 interrupt 返回 satisfied →
    # 节点必须以 interrupt 的返回值为准继续
    state = _base_state("revised", interrupt_review=True, user_feedback=["预置反馈"])
    merged, update = _run(state)

    assert len(calls) == 1
    payload = calls[0]
    assert "请审查当前数据包" in payload["message"]
    assert "req_ids" in payload
    assert merged["review_decision"] == "satisfied"
    assert route_after_review(merged) == "satisfied"
    # 反馈来自 interrupt 返回的 resume 值，而非 state.user_feedback
    assert any("用户反馈: x" in p for p in merged["provenance"])
    assert not any("预置反馈" in p for p in merged["provenance"])
    assert "user_goal" not in update  # satisfied 分支不写 user_goal
    assert fake.calls == []  # 未走 revised，不调用 LLM


def test_interrupt_review_uses_requirements_for_req_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """interrupt 的 payload.req_ids 从 data_requirements 提取（兼容 pydantic 对象与 dict）。"""
    calls: list[Any] = []
    monkeypatch.setattr(
        human_review,
        "interrupt",
        lambda payload: calls.append(payload) or {"decision": "satisfied", "feedback": []},
    )

    req = DataReq(
        req_id="req_001",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state = _base_state(
        "satisfied",
        interrupt_review=True,
        data_requirements=[req, {"req_id": "req_002"}],
    )
    _run(state)

    assert calls[0]["req_ids"] == ["req_001", "req_002"]


# ─── unsatisfied 反馈写回 data_requirements ───


def test_unsatisfied_writes_feedback_to_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    """unsatisfied：反馈写回 data_requirements（description/keywords），review_iteration 自增。"""
    _patch_llm(monkeypatch, _FakeLLMClient())

    req = DataReq(
        req_id="req_001",
        req_type=DataReqType.MESH,
        description="banana mesh",
        priority=Priority.REQUIRED,
        keywords=["banana"],
    )
    state = _base_state(
        "unsatisfied",
        user_feedback=["要真实 DexGraspNet 数据"],
        data_requirements=[req],
    )
    merged, update = _run(state)

    assert "data_requirements" in update
    new_reqs = update["data_requirements"]
    assert len(new_reqs) == 1
    assert new_reqs[0] is not req  # 返回新对象，不就地修改
    assert "用户反馈: 要真实 DexGraspNet 数据" in new_reqs[0].description
    assert "要真实 DexGraspNet 数据" in new_reqs[0].keywords
    assert req.description == "banana mesh"  # 原需求未被修改
    assert req.keywords == ["banana"]
    assert merged["review_iteration"] == 1  # review_iteration 自增
    assert any("反馈已写入 data_requirements" in p for p in merged["provenance"])


def test_unsatisfied_empty_feedback_keeps_requirements(monkeypatch: pytest.MonkeyPatch) -> None:
    """unsatisfied 且无反馈：data_requirements 仍返回新列表（无空反馈污染 keywords）。"""
    _patch_llm(monkeypatch, _FakeLLMClient())

    req = DataReq(
        req_id="req_001",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
        keywords=["banana"],
    )
    merged, update = _run(_base_state("unsatisfied", data_requirements=[req]))

    new_reqs = update["data_requirements"]
    assert new_reqs[0].keywords == ["banana"]
    assert merged["review_iteration"] == 1


# ─── 端到端：human_review(revised) → assemble ───


def test_revision_history_reaches_manifest(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """端到端：revised 后走 assemble，manifest.revision_history 非空且字段完整。"""
    fake = _FakeLLMClient(
        result=human_review._RevisedGoal(revised_goal="用 UR5 在 PyBullet 中抓取 mug")
    )
    _patch_llm(monkeypatch, fake)
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))

    state = _base_state("revised", user_feedback=["换 UR5"])
    merged, _ = _run(state)

    out = node_assemble(merged)
    pkg = out["experiment_package"]
    assert pkg.revision_history
    assert pkg.revision_history == merged["revision_history"]
    assert pkg.revision_history[0]["decision"] == "revised"
    assert pkg.revision_history[0]["revised_goal"] == "用 UR5 在 PyBullet 中抓取 mug"
