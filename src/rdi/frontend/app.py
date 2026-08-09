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
    created_at = datetime.now().isoformat(timespec="seconds")
    package_id = f"package-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    package_dir = OUTPUT_ROOT / package_id
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
    created_at = datetime.now().isoformat(timespec="seconds")
    package_id = f"fallback-package-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    package_dir = OUTPUT_ROOT / package_id
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
        f"{created_at} backend failed before returning experiment_package",
        f"{created_at} frontend generated fallback package",
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
            "status": "fallback_failed",
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


def run_graph(goal: str, paper_file: Any, review_decision: str, feedback: str) -> dict[str, Any]:
    builder = importlib.import_module("rdi.graph.builder")
    graph = builder.build_graph()

    state: dict[str, Any] = {
        "user_goal": goal,
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
        "review_decision": review_decision,
        "user_feedback": [feedback] if feedback.strip() else [],
    }

    pdf_bytes = read_uploaded_pdf(paper_file)
    if pdf_bytes is not None:
        state["paper_pdf"] = pdf_bytes

    result = asyncio.run(
        graph.ainvoke(
            state,
            config={"configurable": {"thread_id": str(uuid.uuid4())}},
        )
    )

    if isinstance(result, dict):
        return result

    return {"errors": [f"Unexpected graph result: {result!r}"]}


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "user_goal": state.get("user_goal"),
        "iteration_count": state.get("iteration_count"),
        "data_requirements": to_plain(state.get("data_requirements", [])),
        "retrieval_errors": to_plain(state.get("retrieval_errors", [])),
        "errors": to_plain(state.get("errors", [])),
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


def run_workflow(
    mode: str,
    goal: str,
    paper_file: Any,
    review_decision: str,
    feedback: str,
) -> tuple[str, dict[str, Any], dict[str, Any], str, str, Any, Any, Any, str]:
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
        )

    try:
        if mode == "真实流程":
            state = run_graph(goal, paper_file, review_decision, feedback)
        else:
            state = build_demo_state(goal, review_decision, feedback)
        if not state.get("experiment_package"):
            errors = to_plain(state.get("errors", []))
            if isinstance(errors, list) and errors:
                error_message = "; ".join(str(item) for item in errors)
            else:
                error_message = "Backend returned no experiment_package."
            state = build_failure_state(goal, paper_file, review_decision, feedback, error_message)
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

        status = "运行完成"
        if state.get("errors"):
            status = "运行完成，但存在错误"

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
        )

    except Exception as exc:
        state = build_failure_state(goal, paper_file, review_decision, feedback, str(exc))
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

        req_headers, req_rows = build_req_status_table(state)
        return (
            "运行失败，已生成前端兜底数据包",
            summarize_state(state),
            {"headers": req_headers, "data": req_rows},
            tree,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            validation_issues,
            runtime_check,
            missing_items,
            "\n".join(str(item) for item in provenance),
        )


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
            review_decision = gr.Radio(
                choices=["satisfied", "revised", "unsatisfied"],
                value="satisfied",
                label="审查决定",
            )
            feedback = gr.Textbox(label="反馈", lines=3)
            run_button = gr.Button("运行", variant="primary")
            status = gr.Textbox(label="状态", interactive=False)

        with gr.Tab("进度展示"):
            progress = gr.JSON(label="state_summary")
            req_status = gr.Dataframe(
                label="数据需求状态",
                headers=["req_id", "req_type", "状态", "数据源", "是否 fallback", "失败原因"],
                interactive=False,
            )
            provenance = gr.Textbox(label="provenance", lines=12, interactive=False)

        with gr.Tab("数据包审查"):
            tree = gr.Textbox(label="数据包目录", lines=16, interactive=False)
            manifest = gr.Textbox(label="manifest", lines=18, interactive=False)

        with gr.Tab("校验与缺失项"):
            validation_issues = gr.JSON(label="validation_issues")
            runtime_check = gr.JSON(label="runtime_check（MuJoCo 验证）")
            missing_items = gr.JSON(label="missing_items")

        run_button.click(
            fn=run_workflow,
            inputs=[mode, goal, paper_file, review_decision, feedback],
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
