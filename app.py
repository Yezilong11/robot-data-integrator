from __future__ import annotations

import importlib
import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[4]
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

    result = graph.invoke(
        state,
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
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
) -> tuple[str, dict[str, Any], str, str, Any, Any, str]:
    if not goal.strip():
        return "请输入实验目标。", {}, "", "", [], [], ""

    try:
        if mode == "真实流程":
            state = run_graph(goal, paper_file, review_decision, feedback)
        else:
            state = build_demo_state(goal, review_decision, feedback)

        manifest = to_plain(state.get("experiment_package", {}))
        validation_issues = to_plain(state.get("validation_issues", []))
        missing_items = to_plain(state.get("missing_items", []))
        provenance = to_plain(state.get("provenance", []))

        package_dir = get_package_dir(state)
        tree = package_tree(package_dir) if package_dir else ""

        status = "运行完成"
        if state.get("errors"):
            status = "运行完成，但存在错误"

        return (
            status,
            summarize_state(state),
            tree,
            json.dumps(manifest, ensure_ascii=False, indent=2),
            validation_issues,
            missing_items,
            "\n".join(str(item) for item in provenance),
        )

    except Exception as exc:
        return (
            f"运行失败：{exc}",
            {"errors": [str(exc)]},
            "",
            "",
            [],
            [],
            "",
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
                choices=["satisfied", "revise"],
                value="satisfied",
                label="审查决定",
            )
            feedback = gr.Textbox(label="反馈", lines=3)
            run_button = gr.Button("运行", variant="primary")
            status = gr.Textbox(label="状态", interactive=False)

        with gr.Tab("进度展示"):
            progress = gr.JSON(label="state_summary")
            provenance = gr.Textbox(label="provenance", lines=12, interactive=False)

        with gr.Tab("数据包审查"):
            tree = gr.Textbox(label="数据包目录", lines=16, interactive=False)
            manifest = gr.Textbox(label="manifest", lines=18, interactive=False)

        with gr.Tab("校验与缺失项"):
            validation_issues = gr.JSON(label="validation_issues")
            missing_items = gr.JSON(label="missing_items")

        run_button.click(
            fn=run_workflow,
            inputs=[mode, goal, paper_file, review_decision, feedback],
            outputs=[
                status,
                progress,
                tree,
                manifest,
                validation_issues,
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
