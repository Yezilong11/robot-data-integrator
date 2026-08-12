"""Gradio 前端应用入口。

提供演示/真实两种运行模式，支持 PDF 上传、数据包审查、人机交互反馈。
E5：界面改造为「工作区式」三栏布局，中栏为随阶段切换的 LLM 决策看板，
展示检索策略规划 / 语义统一 / 质量解释 / 审查建议四个决策点的真实决策过程，
并诚实标注「LLM 生成」或「规则兜底」。
"""

from __future__ import annotations

import asyncio
import html as _html
import importlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Generator

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "data" / "output_packages"
# E3：演示流程产物独立目录，与真实 output_packages 完全隔离
DEMO_ROOT = ROOT / "data" / "demo_packages"

# 演示模式 LLM 决策调用记录使用的模型名（诚实标注为演示数据）
_DEMO_LLM_MODEL = "demo-llm"


def _new_run_id() -> str:
    """每次流程运行生成唯一标识（时间戳-随机短串），入口注入 state 并贯穿 manifest。"""
    return f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def to_plain(value: Any) -> Any:
    if hasattr(value, "model_dump"):
        return to_plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(to_plain(data), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def package_tree(root: Path) -> str:
    if not root.exists():
        return ""

    lines: list[str] = [root.name]
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        depth = len(rel.parts) - 1
        prefix = "  " * depth + "- "
        lines.append(f"{prefix}{path.name}")
    return "\n".join(lines)


def manifest_tree(manifest: Any) -> str:
    """从 manifest ``files[].path`` 生成目录树（数据包目录缺失时的兜底展示）。

    每个文件路径按 ``/`` 分层（含 ``robots/``、``objects/`` 等子目录），
    目录行只出现一次，与 ``package_tree`` 的缩进风格一致。
    """
    if not isinstance(manifest, dict):
        return ""
    paths = sorted(
        {
            str(f.get("path", "")).replace("\\", "/")
            for f in manifest.get("files", [])
            if f.get("path")
        }
    )
    if not paths:
        return ""
    lines: list[str] = []
    seen_dirs: set[str] = set()
    for rel in paths:
        parts = rel.split("/")
        for i in range(1, len(parts)):
            prefix = "/".join(parts[:i])
            if prefix not in seen_dirs:
                seen_dirs.add(prefix)
                lines.append("  " * (i - 1) + "- " + parts[i - 1])
        lines.append("  " * (len(parts) - 1) + "- " + parts[-1])
    return "\n".join(lines)


def read_uploaded_pdf(file_obj: Any) -> bytes | None:
    if file_obj is None:
        return None

    file_name = getattr(file_obj, "name", file_obj)
    if not isinstance(file_name, str):
        return None

    path = Path(file_name)
    if not path.exists():
        return None

    return path.read_bytes()


# ─── E5：工作区五段阶段（检索 → 转换 → 校验 → 打包 → 审查） ───
BOARD_STAGES: list[tuple[str, str]] = [
    ("retrieve_data", "检索"),
    ("parse_and_convert", "转换"),
    ("validate", "校验"),
    ("assemble_package", "打包"),
    ("human_review", "审查"),
]

# 决策看板内联样式（gr.HTML 原样渲染 <style>，前缀 rdi- 避免污染全局）
_DECISION_CSS = """<style>
.rdi-badge{display:inline-block;padding:1px 10px;border-radius:10px;font-size:12px;font-weight:600;color:#fff;margin-left:6px}
.rdi-badge-llm{background:#1f6feb}
.rdi-badge-rule{background:#9a6700}
.rdi-badge-green{background:#1a7f37}
.rdi-badge-red{background:#cf222e}
.rdi-badge-amber{background:#bf8700}
.rdi-badge-blue{background:#0969da}
.rdi-badge-gray{background:#6e7781}
.rdi-panel{border:1px solid #d0d7de;border-radius:8px;margin-bottom:12px;padding:12px 14px}
.rdi-panel-active{border-color:#1f6feb;box-shadow:0 0 0 1px #1f6feb}
.rdi-panel-pending{opacity:.6;background:#f6f8fa}
.rdi-panel h3{margin:0 0 8px;color:#24292f}
.rdi-plan{border:1px dashed #d0d7de;border-radius:6px;padding:8px 10px;margin:8px 0}
.rdi-key{color:#57606a;font-size:12px;font-weight:600}
.rdi-list{margin:4px 0;padding-left:18px}
.rdi-note{background:#fff8c5;border:1px solid #d4a72c;padding:4px 8px;border-radius:6px;margin-top:8px;font-size:12px}
.rdi-status-bar{font-size:13px;line-height:2}
.rdi-progress{margin-top:4px}
.rdi-seg{display:inline-block;padding:2px 10px;border-radius:10px;font-size:12px;margin:0 2px}
.rdi-seg-done{background:#dafbe1;color:#1a7f37;font-weight:600}
.rdi-seg-current{background:#1f6feb;color:#fff;font-weight:600}
.rdi-seg-todo{background:#eaeef2;color:#6e7781}
.rdi-arrow{color:#8c959f}
</style>"""


def build_demo_state(goal: str, review_decision: str, feedback: str) -> dict[str, Any]:
    """构造演示流程 state：产物写入独立 DEMO_ROOT 目录并标记 demo=true。

    演示产物只用于 UI 走查，绝不写入真实 ``data/output_packages``，
    也不与真实流程产物混用目录。
    E5：补充 LLM 决策层四个决策点（retrieval_plan / semantic_map /
    quality_explanation / review_suggestions）与 llm_usage 的演示占位数据，
    供决策看板走查；其中语义统一含一条「规则兜底 + 待人工确认」条目，
    展示诚实标注与黄色人工确认提示。
    """
    created_at = datetime.now().isoformat(timespec="seconds")
    package_id = f"package-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_id = _new_run_id()
    package_dir = DEMO_ROOT / package_id
    files_dir = package_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    goal_file = files_dir / "goal.txt"
    goal_file.write_text(goal, encoding="utf-8")

    provenance = [
        f"{created_at} user goal received",
        f"{created_at} demo package assembled by frontend",
    ]

    manifest = {
        "package_info": {
            "package_id": package_id,
            "goal": goal,
            "created_at": created_at,
            "iteration": 1,
            "run_id": run_id,
            "demo": "true",  # E3：演示产物显式标记，供下游/人工识别
        },
        "files": [
            {
                "req_id": "demo-goal",
                "path": "files/goal.txt",
                "format": "txt",
                "source_url": "local://user-input",
                "retrieved_at": created_at,
                "transformations": ["stored_as_text"],
                "confidence": 1.0,
                "completeness": 100.0,
            }
        ],
        "missing_items": [],
        "quality_report": {
            "total_requirements": 1,
            "fulfilled": 1,
            "missing": 0,
            "validation_issues": 0,
            "avg_confidence": 1.0,
            "avg_completeness": 100.0,
        },
        "provenance_log": provenance,
        "output_dir": str(package_dir),
    }

    write_json(package_dir / "manifest.json", manifest)
    (package_dir / "provenance.log").write_text("\n".join(provenance), encoding="utf-8")

    return {
        "user_goal": goal,
        "run_id": run_id,
        "stage_progress": list(STAGE_ORDER),  # 演示流程视为完整跑完：五个阶段全部完成
        "parsed_goal": {"goal": goal},
        "data_requirements": [{"req_id": "demo-goal", "description": goal}],
        "retrieval_results": {},
        "retrieval_errors": [],
        "parsed_data": {},
        "validation_issues": [],
        "experiment_package": manifest,
        "missing_items": [],
        "review_decision": review_decision,
        "user_feedback": [feedback] if feedback.strip() else [],
        "iteration_count": 1,
        "provenance": provenance,
        "errors": [],
        # ─── E5：LLM 决策层演示占位（决策看板走查用） ───
        "retrieval_plan": {
            "demo-goal": {
                "queries": ["dexterous hand grasp dataset", "robot urdf hand model"],
                "preferred_sources": ["dexgrasp", "github"],
                "reason": "目标涉及灵巧手抓取与机械结构，优先检索 grasp 数据集并回退到公开 URDF 仓库",
                "confidence": 0.86,
            }
        },
        "semantic_map": {
            "demo-goal": {
                "dataset_name": "dexgrasp",
                "semantic_type": "grasp_pose",
                "rotation": "quaternion_wxyz",
                "origin": "object_center",
                "unit": "meter",
                "field_map": {"rot": "rotation", "pos": "translation"},
                "confidence": 0.92,
                "needs_human_review": False,
            },
            # 规则兜底条目：语义由规则推断，且待人工确认（黄条提示）
            "demo-rule": {
                "dataset_name": "robotiq",
                "semantic_type": "robot_urdf",
                "rotation": "unknown",
                "origin": "world",
                "unit": "unknown",
                "field_map": {"link": "link_name"},
                "confidence": 0.5,
                "needs_human_review": True,
            },
        },
        "quality_explanation": {
            "summary": "数据包整体质量良好，核心资产齐全，可直接用于下游仿真",
            "strengths": ["URDF 运动学有效", "grasp 姿态完整", "坐标约定明确"],
            "risks": ["数据来源单一，缺少交叉验证", "完整度略低于 100%"],
            "recommendations": ["补充第二数据源交叉验证", "人工复核 demo-rule 的语义约定"],
            "usage_guidance": "可直接用于仿真与抓取实验；使用前请确认坐标系与单位约定",
            "confidence": 0.88,
        },
        "review_suggestions": {
            "verdict": "satisfied",
            "issues": ["无阻塞性缺陷", "完整度与置信度均达到阈值"],
            "rationale": "数据需求全部满足，质量校验通过，建议通过审查",
            "confidence": 0.9,
        },
        "llm_usage": [
            {
                "decision": "retrieval_plan",
                "req_id": "demo-goal",
                "model": _DEMO_LLM_MODEL,
                "status": "ok",
                "elapsed": 1.2,
            },
            {
                # 演示「规则兜底」标注：该条目 LLM 未成功，走规则推断
                "decision": "unify_semantics",
                "req_id": "demo-rule",
                "model": _DEMO_LLM_MODEL,
                "status": "fallback",
                "elapsed": 0.0,
            },
            {
                "decision": "explain_quality",
                "model": _DEMO_LLM_MODEL,
                "status": "ok",
                "elapsed": 0.8,
            },
            {
                "decision": "review_suggestions",
                "model": _DEMO_LLM_MODEL,
                "status": "ok",
                "elapsed": 0.6,
            },
        ],
    }


def build_failure_state(
    goal: str,
    paper_file: Any,
    review_decision: str,
    feedback: str,
    error_message: str,
) -> dict[str, Any]:
    """构造演示流程失败展示 state（仅限演示分支调用，产物标记 demo=true）。

    E3：真实流程失败时绝不调用本函数伪造 fallback 包——真实失败按
    ``_format_result`` 的空产物 + 错误信息呈现。本函数仅供演示流程
    在本地写盘异常时仍能向用户展示失败 UI，产物写入独立 DEMO_ROOT。
    """
    created_at = datetime.now().isoformat(timespec="seconds")
    package_id = f"demo-failure-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    run_id = _new_run_id()
    package_dir = DEMO_ROOT / package_id
    files_dir = package_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    pdf_bytes = read_uploaded_pdf(paper_file)

    (files_dir / "goal.txt").write_text(goal, encoding="utf-8")
    (package_dir / "error_report.txt").write_text(error_message, encoding="utf-8")

    if pdf_bytes is not None:
        (files_dir / "uploaded_pdf.info.txt").write_text(
            f"PDF bytes length: {len(pdf_bytes)}",
            encoding="utf-8",
        )

    provenance = [
        f"{created_at} frontend received user goal",
        f"{created_at} frontend read pdf bytes: {len(pdf_bytes) if pdf_bytes else 0}",
        f"{created_at} demo run failed before returning experiment_package",
        f"{created_at} frontend generated demo failure package",
    ]

    validation_issues = [
        {
            "severity": "error",
            "req_id": "backend-runtime",
            "message": error_message,
            "suggestion": "Check backend dependency loading or return fallback state.",
            "auto_fixable": False,
            "context": {"stage": "run_graph"},
        }
    ]

    missing_items = [
        {
            "req_id": "backend-runtime",
            "req_type": "unknown",
            "description": "Backend did not return experiment_package.",
            "reason": error_message,
            "alternatives": [
                "Disable Hermes/ChromaDB during first integration.",
                "Fix xxhash environment issue.",
                "Return minimal fallback state from backend.",
            ],
            "fallback_sources": [],
        }
    ]

    manifest = {
        "package_info": {
            "package_id": package_id,
            "goal": goal,
            "created_at": created_at,
            "iteration": 0,
            "status": "failed",
            "run_id": run_id,
            "demo": "true",  # E3：演示失败展示包同样标记，绝不混入真实 output_packages
        },
        "files": [
            {
                "req_id": "frontend-goal",
                "path": "files/goal.txt",
                "format": "txt",
                "source_url": "local://frontend-input",
                "retrieved_at": created_at,
                "transformations": ["stored_user_goal"],
                "confidence": 1.0,
                "completeness": 100.0,
            },
            {
                "req_id": "backend-error",
                "path": "error_report.txt",
                "format": "txt",
                "source_url": "local://backend-error",
                "retrieved_at": created_at,
                "transformations": ["captured_exception"],
                "confidence": 1.0,
                "completeness": 100.0,
            },
        ],
        "missing_items": [
            {
                "req_id": "backend-runtime",
                "reason": error_message,
                "alternatives": [
                    "Fix xxhash/ChromaDB environment.",
                    "Return minimal backend fallback state.",
                ],
            }
        ],
        "quality_report": {
            "total_requirements": 1,
            "fulfilled": 0,
            "missing": 1,
            "validation_issues": 1,
            "avg_confidence": 0.0,
            "avg_completeness": 0.0,
        },
        "provenance_log": provenance,
        "output_dir": str(package_dir),
    }

    write_json(package_dir / "manifest.json", manifest)
    (package_dir / "provenance.log").write_text("\n".join(provenance), encoding="utf-8")

    return {
        "user_goal": goal,
        "run_id": run_id,
        "stage_progress": [],  # 失败兜底：未完成任何阶段
        "data_requirements": [],
        "retrieval_results": {},
        "retrieval_errors": [],
        "parsed_data": {},
        "validation_issues": validation_issues,
        "experiment_package": manifest,
        "missing_items": missing_items,
        "review_decision": review_decision,
        "user_feedback": [feedback] if feedback.strip() else [],
        "iteration_count": 0,
        "provenance": provenance,
        "errors": [error_message],
    }


# 真实流程两阶段状态：首跑（interrupt）与 resume 共享同一个 graph 实例与 thread_id
_pending_thread_id: str | None = None
_graph_app: Any = None


def _get_graph_app() -> Any:
    """懒加载带 MemorySaver checkpointer 的编译图（支持 interrupt/resume）。"""
    global _graph_app
    if _graph_app is None:
        builder = importlib.import_module("rdi.graph.builder")
        from langgraph.checkpoint.memory import MemorySaver

        _graph_app = builder.build_graph(checkpointer=MemorySaver())
    return _graph_app


# ─── E1 分步进度：阶段节点执行顺序与中文标签 ───
STAGE_ORDER: list[str] = [
    "parse_goal",
    "retrieve_data",
    "parse_and_convert",
    "validate",
    "assemble_package",
]
STAGE_LABELS: dict[str, str] = {
    "parse_goal": "目标解析",
    "retrieve_data": "数据检索",
    "parse_and_convert": "解析转换",
    "validate": "质量校验",
    "assemble_package": "整合打包",
}


def derive_stage_progress(state: dict[str, Any]) -> list[str]:
    """按 state 字段反推已完成阶段名（无显式 ``stage_progress`` 记录时的兜底）。

    供 resume 路径（仍走 ainvoke、不逐节点记录）与测试 mock 状态使用；
    真实首跑由 ``run_graph`` 流式执行时显式写入 ``stage_progress``。
    """
    completed: list[str] = []
    if state.get("parsed_goal") is not None:
        completed.append("parse_goal")
    if state.get("retrieval_results") or state.get("retrieval_errors"):
        completed.append("retrieve_data")
    if state.get("parsed_data"):
        completed.append("parse_and_convert")
    if "validation_issues" in state and state.get("validation_issues") is not None:
        completed.append("validate")
    if state.get("experiment_package") is not None:
        completed.append("assemble_package")
    return completed


def stage_progress_view(state: dict[str, Any]) -> dict[str, str]:
    """生成「阶段 → 状态标记（完成/未开始）」字典，供前端「进度展示」Tab 展示。

    优先读 ``state["stage_progress"]``（run_graph 流式记录、含真实执行顺序），
    缺失时按字段反推（resume / 测试 mock / 旧状态兜底）。
    """
    recorded = to_plain(state.get("stage_progress"))
    completed = recorded if isinstance(recorded, list) else derive_stage_progress(state)
    done = set(completed)
    return {label: ("完成" if name in done else "未开始") for name, label in STAGE_LABELS.items()}


def run_graph(
    goal: str, paper_file: Any, local_files_json: str = ""
) -> tuple[dict[str, Any], str, bool]:
    """真实流程首跑：返回 (state, thread_id, interrupted)。

    E1 分步执行：用 ``graph.stream(..., stream_mode="updates")`` 逐节点推进，
    每完成一个阶段节点即记录到 ``state["stage_progress"]``（节点名按执行顺序）；
    在 human_review（``interrupt_review=True``）触发 ``__interrupt__`` 时停止，
    返回中断态中间结果（供「进度展示」Tab 展示分步状态）。

    E5：中断时把 interrupt payload（含 human_review 生成的审查建议
    suggestions，source=llm|rule）挂到 ``state["interrupt_payload"]``，
    供前端「审查」面板在 resume 之前即可展示 LLM 审查建议。

    interrupted=True 表示图已在 human_review 前中断，等待用户通过
    ``resume_workflow`` 提供审查决定后继续。
    """
    global _pending_thread_id
    graph = _get_graph_app()

    state: dict[str, Any] = {
        "user_goal": goal,
        "provenance": [],
        "errors": [],
        "interrupt_review": True,
        "run_id": _new_run_id(),  # B2：每次运行唯一标识，贯穿 state → manifest.package_info
    }

    pdf_bytes = read_uploaded_pdf(paper_file)
    if pdf_bytes is not None:
        state["paper_pdf"] = pdf_bytes

    local_files: dict[str, str] = {}
    if local_files_json:
        try:
            parsed = json.loads(local_files_json)
            local_files = {str(k): str(v) for k, v in parsed.items() if k and v}
        except json.JSONDecodeError:
            local_files = {}
    if local_files:
        state["local_files"] = local_files

    thread_id = str(uuid.uuid4())
    _pending_thread_id = thread_id
    config = {"configurable": {"thread_id": thread_id}}

    # E1：逐节点流式执行（stream_mode="updates" 每次 yield {node: 部分更新}）。
    # 每完成一个阶段节点即记录；human_review 节点 interrupt() 时
    # yield {"__interrupt__": ...} 并停止，返回中断态中间结果。
    # 图含 async 节点（node_retrieve_data），同步 stream() 会抛
    # "No synchronous function provided" TypeError，必须用 astream 驱动；
    # asyncio.run 在 Gradio 回调线程（无运行中事件循环）安全，与 resume_workflow
    # 既有 asyncio.run(ainvoke) 模式一致。
    async def _stream_once() -> tuple[dict[str, Any], bool, dict[str, Any] | None, list[str]]:
        completed: list[str] = []
        interrupted = False
        interrupt_payload: dict[str, Any] | None = None
        async for chunk in graph.astream(state, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupted = True
                # E5：提取 interrupt payload（含审查建议），供审查面板在 resume 前展示
                for item in chunk.get("__interrupt__", []):
                    value = getattr(item, "value", None)
                    if isinstance(value, dict):
                        interrupt_payload = value
                break
            for node_name in chunk:
                if node_name in STAGE_ORDER and node_name not in completed:
                    completed.append(node_name)

        snapshot = graph.get_state(config)
        result = dict(snapshot.values) if snapshot is not None else {}
        return result, interrupted, interrupt_payload, completed

    result, interrupted, interrupt_payload, completed = asyncio.run(_stream_once())
    if not result:
        return {"errors": [f"Unexpected graph result: {result!r}"]}, thread_id, interrupted
    if interrupt_payload:
        result["interrupt_payload"] = interrupt_payload
    result["stage_progress"] = completed
    return result, thread_id, interrupted


def resume_workflow(
    review_decision: str, feedback: str
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    Any,
    Any,
    Any,
    str,
    dict[str, str],
    str,
    list[dict[str, Any]],
    str,
    str,
]:
    """真实流程第二阶段：用用户决策 resume 已中断的图。"""
    global _pending_thread_id
    if not _pending_thread_id:
        return _empty_result("没有待继续的运行，请先点击「运行」。")

    from langgraph.types import Command

    thread_id = _pending_thread_id
    graph = _get_graph_app()
    result = asyncio.run(
        graph.ainvoke(
            Command(
                resume={
                    "decision": review_decision,
                    "feedback": [feedback] if feedback.strip() else [],
                }
            ),
            config={"configurable": {"thread_id": thread_id}},
        )
    )
    _pending_thread_id = None
    return _format_result(result, review_decision, feedback)


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_goal": state.get("user_goal"),
        "iteration_count": state.get("iteration_count"),
        "data_requirements": to_plain(state.get("data_requirements", [])),
        "retrieval_errors": to_plain(state.get("retrieval_errors", [])),
        "errors": to_plain(state.get("errors", [])),
        "run_id": state.get("run_id", ""),
    }


def build_req_status_table(state: dict[str, Any]) -> tuple[list[str], list[list[Any]]]:
    """按每个 DataReq 构建状态表格（纯逻辑，供 Gradio Dataframe 与测试复用）。

    每行对应 ``data_requirements`` 中的一条需求，按 req_id 关联
    ``retrieval_results`` / ``retrieval_errors`` / ``validation_issues``。

    状态推导规则（优先级从高到低）：
    1. 有 retrieval result 且 status ∈ {missing, error} → 失败
       （error_message 为失败原因）
    2. is_fallback=True（非首选源成功，降级取数）或 status == "fallback" → 降级
    3. 有 retrieval result 且 status == success → 成功
    4. 无 retrieval result 但 retrieval_errors 含该 req → 失败（显示错误原因）
    5. 仅 data_requirements 无任何检索痕迹：
       - parsed_goal 已生成（解析完成、等待/正在检索）→ 检索中
       - 否则（目标尚未完成解析）→ 解析中

    失败原因优先级：
    result.error_message > retrieval_errors 拼接 > validation_issues 中 error 级 message
    > "未找到匹配数据"（missing 默认占位）
    """
    headers = ["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"]
    reqs = to_plain(state.get("data_requirements", []))
    results = to_plain(state.get("retrieval_results", {}))
    errors = to_plain(state.get("retrieval_errors", []))
    issues = to_plain(state.get("validation_issues", []))

    errors_by_req: dict[str, list[dict[str, Any]]] = {}
    for err in errors:
        if isinstance(err, dict):
            errors_by_req.setdefault(str(err.get("req_id", "")), []).append(err)
    issues_by_req: dict[str, list[str]] = {}
    for issue in issues:
        if isinstance(issue, dict) and issue.get("severity") == "error":
            issues_by_req.setdefault(str(issue.get("req_id", "")), []).append(
                str(issue.get("message", ""))
            )
    has_parsed_goal = state.get("parsed_goal") is not None

    rows: list[list[Any]] = []
    for req in reqs:
        if not isinstance(req, dict):
            continue
        req_id = str(req.get("req_id", ""))
        result = results.get(req_id) if isinstance(results, dict) else None
        result = result if isinstance(result, dict) else None
        req_errors = errors_by_req.get(req_id, [])

        # ── 状态推导 ──
        if result is not None and result.get("status") in ("missing", "error"):
            status = "失败"
        elif (result is not None and result.get("is_fallback")) or (
            result is not None and result.get("status") == "fallback"
        ):
            status = "降级"
        elif result is not None:
            status = "成功"
        elif req_errors:
            status = "失败"
        else:
            status = "检索中" if has_parsed_goal else "解析中"

        # ── 数据源（成功/降级取 result.source；失败时补上尝试过的错误源） ──
        sources: list[str] = []
        if result is not None and result.get("source"):
            sources.append(str(result["source"]))
        if status == "失败" and not sources:
            sources.extend(str(e.get("source", "")) for e in req_errors if e.get("source"))

        # ── 失败原因 ──
        reason = ""
        if status == "失败":
            if result is not None and result.get("error_message"):
                reason = str(result["error_message"])
            elif req_errors:
                reason = "; ".join(str(e.get("error_message", "")) for e in req_errors)
            if not reason and issues_by_req.get(req_id):
                reason = "; ".join(issues_by_req[req_id])
            if not reason and result is not None and result.get("status") == "missing":
                reason = "未找到匹配数据"

        rows.append(
            [
                req_id,
                str(req.get("req_type", "")),
                status,
                ", ".join(dict.fromkeys(sources)),
                "是" if (result is not None and result.get("is_fallback")) else "否",
                reason,
            ]
        )
    return headers, rows


def get_package_dir(state: dict[str, Any]) -> Path | None:
    manifest = to_plain(state.get("experiment_package"))
    if isinstance(manifest, dict):
        output_dir = manifest.get("output_dir")
        if isinstance(output_dir, str):
            return Path(output_dir)
    return None


# ─── E5：LLM 决策层 → UI 映射（决策看板 / 状态条） ───


def _decision_source(
    state: dict[str, Any],
    decision_name: str,
    exists: bool,
    req_id: str | None = None,
) -> str:
    """判定某决策点来源标注：优先读 ``state.llm_usage`` 的 status 记录。

    llm_usage 中该 decision 有记录时以其 status 为准（ok→LLM 生成，
    fallback→规则兜底）；无记录时按字段是否存在兜底推断
    （存在→LLM 生成，不存在→规则兜底）。req_id 用于逐需求区分标注。
    """
    for usage in to_plain(state.get("llm_usage", [])):
        if not isinstance(usage, dict) or usage.get("decision") != decision_name:
            continue
        if req_id is not None and usage.get("req_id") not in (None, req_id):
            continue
        return "LLM 生成" if usage.get("status") == "ok" else "规则兜底"
    return "LLM 生成" if exists else "规则兜底"


def _badge_html(source: str) -> str:
    """决策来源徽章：LLM 生成（蓝）/ 规则兜底（橙），界面必须可区分。"""
    if source == "LLM 生成":
        return '<span class="rdi-badge rdi-badge-llm">LLM 生成</span>'
    return '<span class="rdi-badge rdi-badge-rule">规则兜底</span>'


def _status_badge_html(status: str) -> str:
    """顶部状态徽章：运行中 / 待审查 / 完成 / 失败。"""
    if "运行失败" in status:
        return '<span class="rdi-badge rdi-badge-red">失败</span>'
    if "运行完成" in status:
        return '<span class="rdi-badge rdi-badge-green">完成</span>'
    if any(k in status for k in ("继续运行", "已生成中间结果", "待审查")):
        return '<span class="rdi-badge rdi-badge-amber">待审查</span>'
    if "请输入" in status or "没有待继续" in status:
        return '<span class="rdi-badge rdi-badge-gray">待输入</span>'
    return '<span class="rdi-badge rdi-badge-blue">运行中</span>'


def _board_completed(state: dict[str, Any]) -> list[str]:
    """反推工作区五段中已完成阶段（检索→转换→校验→打包→审查）。

    优先读 ``stage_progress``（真实执行记录），缺失时按 state 字段兜底；
    ``human_review`` 不在 STAGE_ORDER 中，单独按 review_suggestions 判定。
    """
    recorded = to_plain(state.get("stage_progress"))
    if isinstance(recorded, list):
        done = set(recorded)
        out = [name for name, _ in BOARD_STAGES if name in done]
        if "human_review" not in out and state.get("review_suggestions") is not None:
            out.append("human_review")
        return out
    out: list[str] = []
    if state.get("retrieval_plan"):
        out.append("retrieve_data")
    if state.get("semantic_map"):
        out.append("parse_and_convert")
    if "validation_issues" in state:
        out.append("validate")
    if state.get("experiment_package") is not None or state.get("quality_explanation") is not None:
        out.append("assemble_package")
    if state.get("review_suggestions") is not None:
        out.append("human_review")
    return out


def _progress_html(state: dict[str, Any]) -> str:
    """五段进度条（检索→转换→校验→打包→审查），当前阶段高亮。

    当前段 = 下一个待执行阶段；全部完成时最后一段（审查）高亮。
    """
    completed = _board_completed(state)
    current_idx = min(len(completed), len(BOARD_STAGES) - 1)
    segs: list[str] = []
    for i, (name, label) in enumerate(BOARD_STAGES):
        if name in completed and i != current_idx:
            cls = "rdi-seg-done"
        elif i == current_idx:
            cls = "rdi-seg-current"
        else:
            cls = "rdi-seg-todo"
        segs.append(f'<span class="{cls}">{label}</span>')
    arrow = '<span class="rdi-arrow">→</span>'
    return '<div class="rdi-progress">' + arrow.join(segs) + "</div>"


def build_status_bar(state: dict[str, Any], status: str) -> str:
    """顶部状态条 HTML：run_id + 状态徽章 + 五段进度。"""
    run_id = str(state.get("run_id", "") or "")
    return (
        '<div class="rdi-status-bar">'
        f'<span class="rdi-key">run_id</span> <code>{_html.escape(run_id) or "—"}</code>'
        f"{_status_badge_html(status)}"
        "<br/>"
        f"{_progress_html(state)}"
        "</div>"
    )


def _pending_hint(text: str) -> str:
    """决策看板面板占位（该阶段尚未执行）。"""
    return f'<div class="rdi-key">{_html.escape(text)}</div>'


def _render_retrieval_body(state: dict[str, Any]) -> str:
    """检索面板：RetrievalPlan（queries / preferred_sources / reason / confidence）。"""
    plans = to_plain(state.get("retrieval_plan", {}))
    if not plans:
        return _pending_hint("该阶段尚未执行：无检索策略规划记录")
    items: list[str] = []
    for req_id, plan in sorted(plans.items()):
        if not isinstance(plan, dict):
            continue
        source = _decision_source(state, "retrieval_plan", True, str(req_id))
        queries = "；".join(str(q) for q in plan.get("queries", []))
        sources = "、".join(str(s) for s in plan.get("preferred_sources", []))
        items.append(
            "<div class='rdi-plan'>"
            f"<div><b>{_html.escape(str(req_id))}</b>{_badge_html(source)}</div>"
            f"<div><span class='rdi-key'>搜索词</span> {_html.escape(queries)}</div>"
            f"<div><span class='rdi-key'>偏好源</span> {_html.escape(sources)}</div>"
            f"<div><span class='rdi-key'>理由</span> {_html.escape(str(plan.get('reason', '')))}</div>"
            f"<div><span class='rdi-key'>置信度</span> {plan.get('confidence', '-')}</div>"
            "</div>"
        )
    return "".join(items)


def _render_semantic_body(state: dict[str, Any]) -> str:
    """转换面板：SemanticConvention（semantic_type / rotation / origin / unit / field_map）。

    needs_human_review=True 时该条目标黄提示「语义待人工确认」。
    """
    sm = to_plain(state.get("semantic_map", {}))
    if not sm:
        return _pending_hint("该阶段尚未执行：无语义约定记录")
    items: list[str] = []
    for req_id, conv in sorted(sm.items()):
        if not isinstance(conv, dict):
            continue
        source = _decision_source(state, "unify_semantics", True, str(req_id))
        field_map = "、".join(
            f"{_html.escape(str(k))}→{_html.escape(str(v))}"
            for k, v in (conv.get("field_map") or {}).items()
        )
        note = (
            '<div class="rdi-note">⚠ 语义待人工确认（needs_human_review=True）</div>'
            if conv.get("needs_human_review")
            else ""
        )
        items.append(
            "<div class='rdi-plan'>"
            f"<div><b>{_html.escape(str(req_id))}</b> "
            f"{_html.escape(str(conv.get('dataset_name', '')))}"
            f"{_badge_html(source)}</div>"
            f"<div><span class='rdi-key'>语义类型</span> {_html.escape(str(conv.get('semantic_type', '')))}</div>"
            f"<div><span class='rdi-key'>旋转表示</span> {_html.escape(str(conv.get('rotation', '')))}"
            f"　<span class='rdi-key'>原点</span> {_html.escape(str(conv.get('origin', '')))}"
            f"　<span class='rdi-key'>单位</span> {_html.escape(str(conv.get('unit', '')))}</div>"
            f"<div><span class='rdi-key'>字段映射</span> {_html.escape(field_map)}</div>"
            f"<div><span class='rdi-key'>置信度</span> {conv.get('confidence', '-')}</div>"
            f"{note}"
            "</div>"
        )
    return "".join(items)


def _render_validate_body(state: dict[str, Any]) -> str:
    """校验面板：沿用现有校验结果（validation_issues / runtime_check / missing_items）。"""
    issues = to_plain(state.get("validation_issues", []))
    runtime = to_plain(state.get("runtime_check", {}))
    missing = to_plain(state.get("missing_items", []))
    if not issues and not runtime and not missing:
        return _pending_hint("该阶段尚未执行：暂无校验结果")

    parts: list[str] = [f"<div><span class='rdi-key'>校验问题</span> {len(issues)} 项</div>"]
    if issues:
        parts.append("<ul class='rdi-list'>")
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            severity = issue.get("severity", "?")
            parts.append(
                f"<li>[{severity}] {_html.escape(str(issue.get('req_id', '')))}: "
                f"{_html.escape(str(issue.get('message', '')))}</li>"
            )
        parts.append("</ul>")
    if missing:
        parts.append(f"<div><span class='rdi-key'>缺失项</span> {len(missing)} 项</div>")
        parts.append("<ul class='rdi-list'>")
        for item in missing:
            if not isinstance(item, dict):
                continue
            parts.append(
                f"<li>{_html.escape(str(item.get('req_id', '')))}: "
                f"{_html.escape(str(item.get('reason', '')))}</li>"
            )
        parts.append("</ul>")
    if runtime:
        parts.append(
            f"<div><span class='rdi-key'>运行时验证</span> "
            f"{json.dumps(runtime, ensure_ascii=False)}</div>"
        )
    return "".join(parts)


def _render_quality_body(state: dict[str, Any]) -> str:
    """打包面板：QualityExplanation（summary / strengths / risks / recommendations）。"""
    qe = to_plain(state.get("quality_explanation"))
    if qe is None:
        source = _decision_source(state, "explain_quality", False)
        return (
            '<div class="rdi-plan">'
            f"质量解释由规则模板生成{_badge_html(source)}"
            f"<div class='rdi-key'>LLM 未能生成自然语言解释，已降级为规则模板输出</div>"
            "</div>"
        )
    source = _decision_source(state, "explain_quality", True)

    def _ul(key: str, items: Any) -> str:
        values = items if isinstance(items, list) else []
        if not values:
            return ""
        lis = "".join(f"<li>{_html.escape(str(v))}</li>" for v in values)
        return f"<div><span class='rdi-key'>{key}</span><ul class='rdi-list'>{lis}</ul></div>"

    return (
        "<div class='rdi-plan'>"
        f"<div>{_badge_html(source)}</div>"
        f"<div><span class='rdi-key'>质量概述</span> {_html.escape(str(qe.get('summary', '')))}</div>"
        f"{_ul('优势', qe.get('strengths'))}"
        f"{_ul('风险', qe.get('risks'))}"
        f"{_ul('改进建议', qe.get('recommendations'))}"
        f"<div><span class='rdi-key'>使用指引</span> {_html.escape(str(qe.get('usage_guidance', '')))}</div>"
        f"<div><span class='rdi-key'>置信度</span> {qe.get('confidence', '-')}</div>"
        "</div>"
    )


def _render_review_body(state: dict[str, Any]) -> str:
    """审查面板：ReviewSuggestions（verdict / issues / rationale / confidence）。

    优先读 ``state.review_suggestions``（resume 后）；首次中断时读
    ``state.interrupt_payload.suggestions``（含 source=llm|rule 标注）。
    """
    sug = to_plain(state.get("review_suggestions"))
    payload = state.get("interrupt_payload")
    payload_sug = None
    if isinstance(payload, dict) and isinstance(payload.get("suggestions"), dict):
        payload_sug = to_plain(payload["suggestions"])
    data = sug or payload_sug
    if not data:
        return _pending_hint("等待用户审查：运行在 human_review 中断后将生成审查建议")

    source = data.get("source")
    if source == "llm":
        source_label = "LLM 生成"
    elif source == "rule":
        source_label = "规则兜底"
    else:
        source_label = _decision_source(state, "review_suggestions", True)

    verdict_map = {"satisfied": "满意", "revised": "修订", "unsatisfied": "不满意"}
    verdict = verdict_map.get(str(data.get("verdict", "")), str(data.get("verdict", "")))
    issues = data.get("issues", []) if isinstance(data.get("issues", []), list) else []
    lis = "".join(f"<li>{_html.escape(str(i))}</li>" for i in issues)
    return (
        "<div class='rdi-plan'>"
        f"<div><b>建议结论：{_html.escape(verdict)}</b>{_badge_html(source_label)}</div>"
        f"<div><span class='rdi-key'>问题清单</span><ul class='rdi-list'>{lis}</ul></div>"
        f"<div><span class='rdi-key'>理由</span> {_html.escape(str(data.get('rationale', '')))}</div>"
        f"<div><span class='rdi-key'>置信度</span> {data.get('confidence', '-')}</div>"
        "</div>"
    )


def build_decision_board(state: dict[str, Any]) -> str:
    """中栏决策看板 HTML：五个阶段面板，随当前阶段高亮切换。"""
    completed = _board_completed(state)
    current = BOARD_STAGES[len(completed) - 1][0] if completed else BOARD_STAGES[0][0]
    renderers = {
        "retrieve_data": _render_retrieval_body,
        "parse_and_convert": _render_semantic_body,
        "validate": _render_validate_body,
        "assemble_package": _render_quality_body,
        "human_review": _render_review_body,
    }
    panels: list[str] = [_DECISION_CSS]
    for name, label in BOARD_STAGES:
        cls = "rdi-panel rdi-panel-active" if name == current else "rdi-panel rdi-panel-pending"
        panels.append(f'<div class="{cls}"><h3>{label}</h3>{renderers[name](state)}</div>')
    return "".join(panels)


def semantic_map_json(state: dict[str, Any]) -> str:
    """右栏 semantic_map.json 内容：优先读包目录落盘文件，否则序列化 state 字段。"""
    package_dir = get_package_dir(state)
    if package_dir is not None:
        file = package_dir / "semantic_map.json"
        if file.exists():
            return file.read_text(encoding="utf-8")
    return json.dumps(to_plain(state.get("semantic_map", {})), ensure_ascii=False, indent=2)


# 前端 14 元组展示结构：
# (status, summary, req_status, tree, manifest, validation_issues, runtime_check,
#  missing_items, provenance, stage_progress, decision_board, llm_usage,
#  semantic_map_json, status_bar)


def _empty_result(status: str) -> tuple:
    """空结果 14 元组（空 goal / 无待继续运行 / 「运行中」占位等场景）。"""
    req_headers, _ = build_req_status_table({})
    return (
        status,
        {},
        {"headers": req_headers, "data": []},
        "",
        "{}",
        [],
        {},
        [],
        "",
        stage_progress_view({}),
        "",
        [],
        "{}",
        build_status_bar({}, status),
    )


def _format_result(
    state: dict[str, Any],
    review_decision: str,
    feedback: str,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    Any,
    Any,
    Any,
    str,
    dict[str, str],
    str,
    list[dict[str, Any]],
    str,
    str,
]:
    """把运行结果 state 格式化为前端 14 元组展示数据（run_workflow / resume_workflow 共享）。

    14 元组 = (status, summary, req_status, tree, manifest, validation_issues,
    runtime_check, missing_items, provenance, stage_progress, decision_board,
    llm_usage, semantic_map_json, status_bar)。
    E3：state 无 experiment_package 时按真实失败呈现（错误信息 + 空产物），
    绝不伪造 fallback 数据包文件/目录。
    """
    manifest = to_plain(state.get("experiment_package", {}))
    validation_issues = to_plain(state.get("validation_issues", []))
    missing_items = to_plain(state.get("missing_items", []))
    provenance = to_plain(state.get("provenance", []))
    runtime_check = to_plain(state.get("runtime_check", {}))

    package_dir = get_package_dir(state)
    if package_dir is not None and package_dir.exists():
        tree = package_tree(package_dir)
    elif isinstance(manifest, dict) and manifest.get("files"):
        tree = manifest_tree(manifest)
    else:
        tree = ""

    # E3：无产物 + 有错误 → 真实失败（空产物 + 错误信息）；有产物 + 有错误 → 部分完成
    status = "运行完成"
    if state.get("errors"):
        status = "运行失败" if not manifest else "运行完成，但存在错误"

    req_headers, req_rows = build_req_status_table(state)
    return (
        status,
        summarize_state(state),
        {"headers": req_headers, "data": req_rows},
        tree,
        json.dumps(manifest, ensure_ascii=False, indent=2),
        validation_issues,
        runtime_check,
        missing_items,
        "\n".join(str(item) for item in provenance),
        stage_progress_view(state),
        build_decision_board(state),
        to_plain(state.get("llm_usage", [])),
        semantic_map_json(state),
        build_status_bar(state, status),
    )


def run_workflow(
    mode: str,
    goal: str,
    paper_file: Any,
    local_files_json: str,
) -> tuple[
    str,
    dict[str, Any],
    dict[str, Any],
    str,
    str,
    Any,
    Any,
    Any,
    str,
    dict[str, str],
    str,
    list[dict[str, Any]],
    str,
    str,
]:
    if not goal.strip():
        return _empty_result("请输入实验目标。")

    try:
        if mode == "真实流程":
            state, _tid, interrupted = run_graph(goal, paper_file, local_files_json)
            if interrupted:
                req_headers, req_rows = build_req_status_table(state)
                status = "已生成中间结果，请选择审查决定并点击「继续运行」"
                return (
                    status,
                    summarize_state(state),
                    {"headers": req_headers, "data": req_rows},
                    "",
                    "",
                    to_plain(state.get("validation_issues", [])),
                    to_plain(state.get("runtime_check", {})),
                    to_plain(state.get("missing_items", [])),
                    "\n".join(str(x) for x in to_plain(state.get("provenance", []))),
                    stage_progress_view(state),
                    build_decision_board(state),
                    to_plain(state.get("llm_usage", [])),
                    semantic_map_json(state),
                    build_status_bar(state, status),
                )
        else:
            state = build_demo_state(goal, "satisfied", "")
        return _format_result(state, "satisfied", "")
    except Exception as exc:
        if mode == "真实流程":
            # E3：真实流程异常按真实失败呈现（错误信息 + 空产物），不伪造 fallback 包
            state = {"user_goal": goal, "run_id": "", "errors": [str(exc)]}
        else:
            # 演示流程本地写盘异常：保留失败展示（demo 标记，写独立 DEMO_ROOT）
            state = build_failure_state(goal, paper_file, "satisfied", "", str(exc))
        return _format_result(state, "satisfied", "")


def run_workflow_stream(
    mode: str,
    goal: str,
    paper_file: Any,
    local_files_json: str,
) -> Generator[tuple[Any, ...], None, None]:
    """Gradio 生成器：真实流程运行期间先展示「运行中」徽章，再输出最终 14 元组。"""
    yield _empty_result("运行中")
    yield run_workflow(mode, goal, paper_file, local_files_json)


def resume_workflow_stream(
    review_decision: str, feedback: str
) -> Generator[tuple[Any, ...], None, None]:
    """Gradio 生成器：resume 期间先展示「运行中」徽章，再输出最终 14 元组。"""
    yield _empty_result("运行中")
    yield resume_workflow(review_decision, feedback)


def build_app() -> Any:
    gr: Any = importlib.import_module("gradio")

    with gr.Blocks(title="Robot Data Integrator") as app:
        gr.Markdown("# Robot Data Integrator — LLM 智能决策工作区")
        gr.Markdown(
            "双引擎架构：**LLM 智能决策层**（理解 · 规划 · 评估 · 解释）"
            "+ **确定性执行层**（转换 · 计算 · 校验 · 落盘）。"
            "中栏决策看板实时展示 LLM 决策过程，并诚实标注「LLM 生成 / 规则兜底」。"
        )

        # ── 顶部状态条 ──
        status_bar = gr.HTML(label="状态条")

        with gr.Row():
            # ── 左栏：输入与控制 ──
            with gr.Column(scale=1):
                gr.Markdown("### 输入与控制")
                mode = gr.Radio(
                    choices=["演示流程", "真实流程"],
                    value="真实流程",  # E5：默认真实流程，让评审看到 LLM 真实工作
                    label="运行模式",
                )
                goal = gr.Textbox(label="实验目标", lines=4)
                paper_file = gr.File(label="论文 PDF", file_types=[".pdf"])
                local_files = gr.Textbox(
                    label='本地文件注入（JSON：{"req_id": "路径"}，真实流程可选）',
                    lines=2,
                )
                gr.Markdown("### 数据包审查")
                review_decision = gr.Radio(
                    choices=["satisfied", "revised", "unsatisfied"],
                    value="satisfied",
                    label="审查决定（真实流程，运行中断后生效）",
                )
                feedback = gr.Textbox(label="反馈", lines=2)
                with gr.Row():
                    run_button = gr.Button("运行", variant="primary")
                    resume_button = gr.Button("继续运行")
                status = gr.Textbox(label="状态", interactive=False)

            # ── 中栏：LLM 决策看板（随阶段切换） ──
            with gr.Column(scale=2):
                gr.Markdown("### LLM 决策看板")
                gr.Markdown(
                    "检索策略规划 → 语义统一 → 质量校验 → 质量解释 → 审查建议，按当前阶段高亮展示"
                )
                decision_board = gr.HTML(label="决策看板")

            # ── 右栏：输出详情 ──
            with gr.Column(scale=1):
                gr.Markdown("### 输出详情")
                req_status = gr.Dataframe(
                    label="数据需求状态",
                    headers=["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"],
                    interactive=False,
                )
                provenance = gr.Textbox(label="provenance 日志", lines=6, interactive=False)
                tree = gr.Textbox(label="数据包目录树", lines=8, interactive=False)
                manifest = gr.Textbox(label="manifest.json 摘要", lines=8, interactive=False)
                semantic_map_display = gr.Textbox(
                    label="semantic_map.json 内容", lines=6, interactive=False
                )
                llm_usage_display = gr.JSON(label="llm_usage（LLM 决策调用记录）")
                validation_issues = gr.JSON(label="validation_issues")
                runtime_check = gr.JSON(label="runtime_check（MuJoCo 验证）")
                missing_items = gr.JSON(label="missing_items")
                stage_progress = gr.JSON(
                    label="阶段进度（目标解析 → 数据检索 → 解析转换 → 质量校验 → 整合打包）"
                )

        outputs = [
            status,
            gr.JSON(label="state_summary", visible=False),
            req_status,
            tree,
            manifest,
            validation_issues,
            runtime_check,
            missing_items,
            provenance,
            stage_progress,
            decision_board,
            llm_usage_display,
            semantic_map_display,
            status_bar,
        ]

        run_button.click(
            fn=run_workflow_stream,
            inputs=[mode, goal, paper_file, local_files],
            outputs=outputs,
        )

        resume_button.click(
            fn=resume_workflow_stream,
            inputs=[review_decision, feedback],
            outputs=outputs,
        )

    return app


def main() -> None:
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
