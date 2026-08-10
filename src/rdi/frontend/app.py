"""Gradio 前端应用入口。

提供演示/真实两种运行模式，支持 PDF 上传、数据包审查、人机交互反馈。
"""

from __future__ import annotations

import asyncio
import importlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
OUTPUT_ROOT = ROOT / "data" / "output_packages"
# E3：演示流程产物独立目录，与真实 output_packages 完全隔离
DEMO_ROOT = ROOT / "data" / "demo_packages"


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
        {str(f.get("path", "")).replace("\\", "/") for f in manifest.get("files", []) if f.get("path")}
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


def build_demo_state(goal: str, review_decision: str, feedback: str) -> dict[str, Any]:
    """构造演示流程 state：产物写入独立 DEMO_ROOT 目录并标记 demo=true。

    演示产物只用于 UI 走查，绝不写入真实 ``data/output_packages``，
    也不与真实流程产物混用目录。
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
    return {
        label: ("完成" if name in done else "未开始")
        for name, label in STAGE_LABELS.items()
    }


def run_graph(goal: str, paper_file: Any, local_files_json: str = "") -> tuple[dict[str, Any], str, bool]:
    """真实流程首跑：返回 (state, thread_id, interrupted)。

    E1 分步执行：用 ``graph.stream(..., stream_mode="updates")`` 逐节点推进，
    每完成一个阶段节点即记录到 ``state["stage_progress"]``（节点名按执行顺序）；
    在 human_review（``interrupt_review=True``）触发 ``__interrupt__`` 时停止，
    返回中断态中间结果（供「进度展示」Tab 展示分步状态）。

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
    completed: list[str] = []
    interrupted = False
    for chunk in graph.stream(state, config=config, stream_mode="updates"):
        if "__interrupt__" in chunk:
            interrupted = True
            break
        for node_name in chunk:
            if node_name in STAGE_ORDER and node_name not in completed:
                completed.append(node_name)

    snapshot = graph.get_state(config)
    result = dict(snapshot.values) if snapshot is not None else {}
    if not result:
        return {"errors": [f"Unexpected graph result: {result!r}"]}, thread_id, interrupted
    result["stage_progress"] = completed
    return result, thread_id, interrupted


def resume_workflow(
    review_decision: str, feedback: str
) -> tuple[str, dict[str, Any], dict[str, Any], str, str, Any, Any, Any, str, dict[str, str]]:
    """真实流程第二阶段：用用户决策 resume 已中断的图。"""
    global _pending_thread_id
    if not _pending_thread_id:
        req_headers, _ = build_req_status_table({})
        return (
            "没有待继续的运行，请先点击「运行」。",
            {},
            {"headers": req_headers, "data": []},
            "",
            "",
            [],
            {},
            [],
            "",
            stage_progress_view({}),
        )

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


def _format_result(
    state: dict[str, Any],
    review_decision: str,
    feedback: str,
) -> tuple[str, dict[str, Any], dict[str, Any], str, str, Any, Any, Any, str, dict[str, str]]:
    """把运行结果 state 格式化为前端 10 元组展示数据（run_workflow / resume_workflow 共享）。

    10 元组 = (status, summary, req_status, tree, manifest, validation_issues,
    runtime_check, missing_items, provenance, stage_progress)。
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
    )


def run_workflow(
    mode: str,
    goal: str,
    paper_file: Any,
    local_files_json: str,
) -> tuple[str, dict[str, Any], dict[str, Any], str, str, Any, Any, Any, str, dict[str, str]]:
    if not goal.strip():
        req_headers, _ = build_req_status_table({})
        return (
            "请输入实验目标。",
            {},
            {"headers": req_headers, "data": []},
            "",
            "",
            [],
            {},
            [],
            "",
            stage_progress_view({}),
        )

    try:
        if mode == "真实流程":
            state, _tid, interrupted = run_graph(goal, paper_file, local_files_json)
            if interrupted:
                req_headers, req_rows = build_req_status_table(state)
                return (
                    "已生成中间结果，请到「数据包审查」选择审查决定并点击「继续运行」",
                    summarize_state(state),
                    {"headers": req_headers, "data": req_rows},
                    "",
                    "",
                    to_plain(state.get("validation_issues", [])),
                    to_plain(state.get("runtime_check", {})),
                    to_plain(state.get("missing_items", [])),
                    "\n".join(str(x) for x in to_plain(state.get("provenance", []))),
                    stage_progress_view(state),
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


def build_app() -> Any:
    gr: Any = importlib.import_module("gradio")

    with gr.Blocks(title="Robot Data Integrator") as app:
        gr.Markdown("# Robot Data Integrator")

        with gr.Tab("目标输入"):
            mode = gr.Radio(
                choices=["演示流程", "真实流程"],
                value="演示流程",
                label="运行模式",
            )
            goal = gr.Textbox(label="实验目标", lines=5)
            paper_file = gr.File(label="论文 PDF", file_types=[".pdf"])
            local_files = gr.Textbox(
                label="本地文件注入（JSON：{\"req_id\": \"路径\"}，真实流程可选）",
                lines=2,
            )
            review_decision = gr.Radio(
                choices=["satisfied", "revised", "unsatisfied"],
                value="satisfied",
                label="审查决定（真实流程，运行中断后生效）",
            )
            feedback = gr.Textbox(label="反馈", lines=3)
            run_button = gr.Button("运行", variant="primary")
            resume_button = gr.Button("继续运行")
            status = gr.Textbox(label="状态", interactive=False)

        with gr.Tab("进度展示"):
            progress = gr.JSON(label="state_summary")
            req_status = gr.Dataframe(
                label="数据需求状态",
                headers=["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"],
                interactive=False,
            )
            provenance = gr.Textbox(label="provenance", lines=12, interactive=False)
            stage_progress = gr.JSON(
                label="阶段进度（目标解析 → 数据检索 → 解析转换 → 质量校验 → 整合打包）"
            )

        with gr.Tab("数据包审查"):
            tree = gr.Textbox(label="数据包目录", lines=16, interactive=False)
            manifest = gr.Textbox(label="manifest", lines=18, interactive=False)

        with gr.Tab("校验与缺失项"):
            validation_issues = gr.JSON(label="validation_issues")
            runtime_check = gr.JSON(label="runtime_check（MuJoCo 验证）")
            missing_items = gr.JSON(label="missing_items")

        run_button.click(
            fn=run_workflow,
            inputs=[mode, goal, paper_file, local_files],
            outputs=[
                status,
                progress,
                req_status,
                tree,
                manifest,
                validation_issues,
                runtime_check,
                missing_items,
                provenance,
                stage_progress,
            ],
        )

        resume_button.click(
            fn=resume_workflow,
            inputs=[review_decision, feedback],
            outputs=[
                status,
                progress,
                req_status,
                tree,
                manifest,
                validation_issues,
                runtime_check,
                missing_items,
                provenance,
                stage_progress,
            ],
        )

    return app


def main() -> None:
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost")

    app = build_app()
    app.launch(server_name="127.0.0.1", server_port=7860, show_error=True)


if __name__ == "__main__":
    main()
