# src/rdi/graph/nodes/human_review.py
"""用户审查节点。

支持三种决策闭环：
- ``satisfied``：用户满意，记录 provenance 后结束（不触发重检索）；
- ``revised``：调用 LLM 把 ``user_feedback`` 转换为修正后的目标描述，
  写入 ``revised_goal`` 并同步更新 ``user_goal``（parse_goal 读取 user_goal
  重新解析），流程经条件边回到 ``parse_goal``；
- ``unsatisfied``：生成更具体的重检索建议（更换数据源 / 更精确关键词）
  写入 ``revised_goal``，流程经条件边回到 ``retrieve_data``。

循环上限：使用独立于 validate 的 ``review_iteration``（前端注入，validate 的
``validate_iteration`` 只统计检索-校验回退轮次，两者解耦），超过
``_MAX_REVIEW_ROUNDS`` 时强制按 satisfied 结束并记录 warning。
每次循环（revised / unsatisfied）清空旧的 ``retrieval_results``，避免状态污染。
"""

from datetime import datetime
from typing import Any

from langgraph.types import interrupt
from pydantic import BaseModel, Field

from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.graph.state import SystemState
from rdi.intelligence import LLMClient
from rdi.logging import get_logger

logger = get_logger(__name__)

# human_review 修订循环上限：最多允许 _MAX_REVIEW_ROUNDS 轮修订，
# 第 _MAX_REVIEW_ROUNDS + 1 次进入时强制按 satisfied 结束。
_MAX_REVIEW_ROUNDS = 3

_VALID_DECISIONS = frozenset({"satisfied", "revised", "unsatisfied"})


class _RevisedGoal(BaseModel):
    """LLM 反馈转换的输出结构（内部使用）。"""

    revised_goal: str = Field(description="整合用户反馈后的修正目标描述")


_FEEDBACK_SYSTEM_PROMPT = """你是机器人操作与抓取领域的数据整合助手。用户对上一版数据包不满意，给出了反馈意见。请把原始目标与用户反馈整合为一份修正后的目标描述，供目标解析节点重新拆解数据需求。

# 规则
- 只修改或补充用户反馈中要求的部分（如更换机器人、物体、仿真器、数据源，或补充关键词），不得改变原始目标中用户未提及的部分。
- 输出必须为严格 JSON：{"revised_goal": "修正后的完整目标描述"}
- 禁止输出 markdown 代码块标记或任何解释性文字。"""


# 模块级懒加载 LLMClient 单例，便于测试 monkeypatch
_llm_client: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    """返回缓存的 LLMClient 单例；首次调用时创建。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def _convert_feedback_to_goal(original_goal: str, feedback: list[str]) -> str:
    """调用 LLM 把用户反馈转换为修正后的目标描述。

    LLM 不可用 / 返回格式解析失败时降级：把反馈原文拼接到目标描述后，
    保证流程继续而不是崩溃。

    Args:
        original_goal: 上一轮目标描述（state.user_goal 或已存在的 revised_goal）。
        feedback: 用户反馈列表。

    Returns:
        修正后的目标描述字符串。
    """
    feedback_text = "\n".join(f"- {m}" for m in feedback) if feedback else "（无具体反馈）"
    prompt = (
        f"原始目标：\n{original_goal}\n\n用户反馈：\n{feedback_text}\n\n"
        "请根据以上输入输出修正后的目标描述（严格 JSON）。"
    )
    try:
        result = _get_llm_client().call_structured(
            prompt=prompt,
            schema=_RevisedGoal,
            system=_FEEDBACK_SYSTEM_PROMPT,
        )
        return result.revised_goal.strip()
    except (LLMUnavailableError, LLMParseError) as e:
        # 降级：直接用用户反馈原文作为修正目标，不崩溃
        logger.warning(
            "human_review.llm_fallback",
            error_type=type(e).__name__,
            reason=str(e),
        )
        fallback = "；".join(feedback)
        return f"{original_goal}。修正要求：{fallback}" if fallback else original_goal


def _build_retrieval_advice(feedback: list[str]) -> str:
    """把用户反馈整理为更具体的重检索建议（更换数据源 / 更精确关键词）。"""
    if not feedback:
        return "请更换数据源或使用更精确的关键词后重新检索"
    return "重检索建议（更换数据源/更精确关键词）：" + "；".join(feedback)


def _failed_req_ids(state: SystemState) -> list[str]:
    """从 ``missing_items`` 与 ``retrieval_errors`` 收集去重后的失败 req_id 列表。

    missing_items 项可能是 MissingItem 或 dict（checkpoint 重建失败时退回 dict），
    retrieval_errors 同理可能是 RetrievalError 或 dict；统一取 ``req_id`` 字段。
    """
    ids: list[str] = []
    seen: set[str] = set()
    for item in state.get("missing_items", []):
        rid = item.get("req_id") if isinstance(item, dict) else getattr(item, "req_id", None)
        if rid is not None and str(rid) not in seen:
            seen.add(str(rid))
            ids.append(str(rid))
    for error in state.get("retrieval_errors", []):
        rid = error.get("req_id") if isinstance(error, dict) else getattr(error, "req_id", None)
        if rid is not None and str(rid) not in seen:
            seen.add(str(rid))
            ids.append(str(rid))
    return ids


def _apply_feedback_to_requirements(requirements: list[Any], feedback: list[str]) -> list[Any]:
    """把用户反馈写回 data_requirements：description 追加反馈文本，keywords 追加非空反馈项。

    对每条 DataReq 用 ``model_copy(deep=True)`` 复制后修改，返回新列表（不就地改动原需求）。
    """
    updated: list[Any] = []
    for req in requirements:
        if isinstance(req, dict):
            # 兜底：state 来自 checkpoint 且 pydantic 重建失败时退回 dict
            new_req = dict(req)
            new_req["description"] = new_req.get("description", "") + "\n用户反馈: " + "; ".join(feedback)
            new_req["keywords"] = [*(new_req.get("keywords") or []), *(m for m in feedback if m)]
        else:
            new_req = req.model_copy(deep=True)
            new_req.description = new_req.description + "\n用户反馈: " + "; ".join(feedback)
            new_req.keywords = [*new_req.keywords, *(m for m in feedback if m)]
        updated.append(new_req)
    return updated


def node_human_review(state: SystemState) -> dict[str, Any]:
    """用户审查节点：根据 ``review_decision`` 走三种分支。

    ``interrupt_review=True`` 时（真实流程）先调用 ``interrupt()`` 等待用户
    决策后再走分支；否则读取 state 中预置的 ``review_decision``（单跑/演示）。

    返回 dict 仅更新本节点负责的字段，LangGraph 会将其合并回全局 state：
    - satisfied：``review_decision`` / ``provenance``；
    - revised：额外更新 ``revised_goal`` / ``user_goal`` / ``review_iteration``，
      并写入 ``retry_req_ids``（仅重跑失败 req，成功项沿用）；
    - unsatisfied：额外更新 ``revised_goal`` / ``data_requirements``（反馈写回
      需求）/ ``review_iteration``，并写入 ``retry_req_ids``。

    除纯 satisfied 外（revised / unsatisfied / 强制结束），向 ``revision_history``
    追加一条修订记录（revision 序号、decision、feedback、revised_goal、timestamp），
    供 assemble 节点写入 manifest；返回完整旧列表 + 新记录。

    Args:
        state: 当前全局状态（含前端传入的 review_decision / user_feedback；
            interrupt_review=True 时改为调用 interrupt 等待用户决策）。

    Returns:
        更新 state 的字段（部分更新 dict）。
    """
    now = datetime.now().isoformat()
    if state.get("interrupt_review"):
        # 真实流程：等待用户决策（interrupt 返回 resume 值）
        req_ids = []
        for r in state.get("data_requirements") or []:
            rid = r.get("req_id") if isinstance(r, dict) else getattr(r, "req_id", None)
            if rid is not None:
                req_ids.append(str(rid))
        resume = interrupt(
            {
                "message": "请审查当前数据包，选择 satisfied / revised / unsatisfied",
                "req_ids": req_ids,
            }
        )
        decision = str((resume or {}).get("decision", "satisfied"))
        feedback = (
            [str(m) for m in (resume or {}).get("feedback", [])]
            if (resume or {}).get("feedback")
            else []
        )
    else:
        decision = state.get("review_decision", "satisfied")
        feedback = state.get("user_feedback", [])
    original_goal = state.get("revised_goal") or state.get("user_goal", "")
    revision_history = state.get("revision_history", [])

    # 信任边界：外部传入的 decision 归一化为三值之一
    if decision not in _VALID_DECISIONS:
        logger.warning("human_review.unknown_decision", decision=decision)
        decision = "satisfied"

    # 循环上限：review_iteration 独立于 validate 的 validate_iteration，
    # 仅统计用户审查/修订轮次；超过 _MAX_REVIEW_ROUNDS 轮后强制结束
    iteration = state.get("review_iteration", 0)
    forced = decision != "satisfied" and iteration >= _MAX_REVIEW_ROUNDS
    if forced:
        logger.warning(
            "human_review.forced_end",
            iteration=iteration,
            max_rounds=_MAX_REVIEW_ROUNDS,
        )
        decision = "satisfied"

    provenance = [f"[{now}] human_review: 审查决定为 {decision}"]
    update: dict[str, Any] = {"review_decision": decision}

    if decision == "satisfied":
        if forced:
            provenance.append(
                f"[{now}] human_review: 修订轮次超过上限 {_MAX_REVIEW_ROUNDS}，强制结束"
            )
            # 强制结束作为一次修订记录（decision=satisfied (forced)），便于追溯：
            # 用户本轮反馈未被应用，保留 revised_goal 为当前生效目标。
            update["revision_history"] = [
                *revision_history,
                {
                    "revision": len(revision_history) + 1,
                    "decision": "satisfied (forced)",
                    "feedback": feedback,
                    "revised_goal": original_goal,
                    "timestamp": now,
                },
            ]
        for message in feedback:
            provenance.append(f"[{now}] human_review: 用户反馈: {message}")
    elif decision == "revised":
        revised_goal = _convert_feedback_to_goal(original_goal, feedback)
        update["revised_goal"] = revised_goal
        update["user_goal"] = revised_goal  # parse_goal 读取 user_goal 重新解析
        failed_ids = _failed_req_ids(state)
        update["retry_req_ids"] = failed_ids  # 仅重跑失败 req，成功项沿用不重拉
        update["review_iteration"] = iteration + 1
        update["revision_history"] = [
            *revision_history,
            {
                "revision": len(revision_history) + 1,
                "decision": "revised",
                "feedback": feedback,
                "revised_goal": revised_goal,
                "timestamp": now,
            },
        ]
        if failed_ids:
            provenance.append(f"[{now}] human_review: 仅重跑失败 req: {', '.join(failed_ids)}")
        provenance.append(
            f"[{now}] human_review: 用户选择修订，反馈已转换为修正目标，回到 parse_goal 重新解析"
        )
        for message in feedback:
            provenance.append(f"[{now}] human_review: 用户反馈: {message}")
    elif decision == "unsatisfied":
        advice = _build_retrieval_advice(feedback)
        update["revised_goal"] = advice  # 保留重检索建议文本供追溯
        update["data_requirements"] = _apply_feedback_to_requirements(
            state.get("data_requirements", []), feedback
        )
        failed_ids = _failed_req_ids(state)
        update["retry_req_ids"] = failed_ids  # 仅重跑失败 req，成功项沿用不重拉
        update["review_iteration"] = iteration + 1
        update["revision_history"] = [
            *revision_history,
            {
                "revision": len(revision_history) + 1,
                "decision": "unsatisfied",
                "feedback": feedback,
                "revised_goal": advice,
                "timestamp": now,
            },
        ]
        if failed_ids:
            provenance.append(f"[{now}] human_review: 仅重跑失败 req: {', '.join(failed_ids)}")
        provenance.append(
            f"[{now}] human_review: 用户不满意，反馈已写入 data_requirements，回到 retrieve_data 按新需求重检索"
        )
        for message in feedback:
            provenance.append(f"[{now}] human_review: 用户反馈: {message}")

    update["provenance"] = provenance
    logger.info(
        "human_review.decision",
        decision=decision,
        iteration=iteration,
        forced=forced,
        feedback_count=len(feedback),
    )
    return update
