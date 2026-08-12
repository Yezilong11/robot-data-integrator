"""RDI FastAPI 后端：薄封装现有 LangGraph 工作流，供静态前端调用。

竞赛演示场景：单用户，内存任务状态 + 前端轮询进度。
业务逻辑（graph / adapter / skill / intelligence / hermes）零改动，
复用 ``rdi.frontend.app`` 中已有的运行与渲染函数。
"""

from __future__ import annotations

import asyncio
import base64
import json
import threading
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from rdi.frontend import app as fe

STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="Robot Data Integrator API")

# 竞赛演示：同源静态页 + 后端，但保留 CORS 以便调试时前后端分端口
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 内存任务状态：task_id -> {done, stage_progress, result, error}
_TASKS: dict[str, dict[str, Any]] = {}


class RunRequest(BaseModel):
    mode: str = "真实流程"
    goal: str = ""
    paper_pdf: str | None = None  # base64 编码的 PDF 内容（可选）
    local_files: str = ""


class ResumeRequest(BaseModel):
    review_decision: str = "satisfied"
    feedback: str = ""


def _decode_pdf(b64: str | None) -> bytes | None:
    if not b64:
        return None
    try:
        return base64.b64decode(b64)
    except Exception:  # noqa: BLE001
        return None


def _run_pipeline(
    task_id: str, mode: str, goal: str, paper_bytes: bytes | None, local_files_json: str
) -> tuple:
    """真实流程：astream 逐节点执行，边跑边更新 stage_progress（供前端轮询）。"""
    if not goal.strip():
        return fe._empty_result("请输入实验目标。")

    if mode == "演示流程":
        return fe._format_result(fe.build_demo_state(goal, "satisfied", ""), "satisfied", "")

    graph = fe._get_graph_app()
    state: dict[str, Any] = {
        "user_goal": goal,
        "provenance": [],
        "errors": [],
        "interrupt_review": True,
        "run_id": fe._new_run_id(),
    }
    if paper_bytes:
        state["paper_pdf"] = paper_bytes

    local: dict[str, str] = {}
    if local_files_json:
        try:
            local = {str(k): str(v) for k, v in json.loads(local_files_json).items() if k and v}
        except json.JSONDecodeError:
            local = {}
    if local:
        state["local_files"] = local

    thread_id = str(uuid.uuid4())
    fe._pending_thread_id = thread_id
    config = {"configurable": {"thread_id": thread_id}}

    async def _stream() -> tuple[dict[str, Any], bool, dict[str, Any] | None, list[str]]:
        completed: list[str] = []
        interrupted = False
        payload: dict[str, Any] | None = None
        async for chunk in graph.astream(state, config=config, stream_mode="updates"):
            if "__interrupt__" in chunk:
                interrupted = True
                for item in chunk.get("__interrupt__", []):
                    value = getattr(item, "value", None)
                    if isinstance(value, dict):
                        payload = value
                break
            for node_name in chunk:
                if node_name in fe.STAGE_ORDER and node_name not in completed:
                    completed.append(node_name)
                    _TASKS[task_id]["stage_progress"] = list(completed)
        snapshot = graph.get_state(config)
        result = dict(snapshot.values) if snapshot is not None else {}
        return result, interrupted, payload, completed

    result, interrupted, payload, completed = asyncio.run(_stream())
    _TASKS[task_id]["stage_progress"] = list(completed)
    if not result:
        return fe._format_result(
            {"errors": [f"Unexpected graph result: {result!r}"]}, "satisfied", ""
        )
    if payload:
        result["interrupt_payload"] = payload
    result["stage_progress"] = completed

    if interrupted:
        req_headers, req_rows = fe.build_req_status_table(result)
        status = "已生成中间结果，请选择审查决定并点击「继续运行」"
        return (
            status,
            fe.summarize_state(result),
            {"headers": req_headers, "data": req_rows},
            "",
            "",
            fe.to_plain(result.get("validation_issues", [])),
            fe.to_plain(result.get("runtime_check", {})),
            fe.to_plain(result.get("missing_items", [])),
            "\n".join(str(x) for x in fe.to_plain(result.get("provenance", []))),
            fe.stage_progress_view(result),
            fe.build_decision_board(result),
            fe.to_plain(result.get("llm_usage", [])),
            fe.semantic_map_json(result),
            fe.build_status_bar(result, status),
        )
    return fe._format_result(result, "satisfied", "")


def _run_task(task_id: str, req: RunRequest) -> None:
    task = _TASKS[task_id]
    try:
        paper = _decode_pdf(req.paper_pdf)
        result = _run_pipeline(task_id, req.mode, req.goal, paper, req.local_files)
        task["result"] = fe.to_plain(result)
    except Exception as exc:  # noqa: BLE001
        task["error"] = str(exc)
    finally:
        task["done"] = True


@app.post("/api/run")
def api_run(req: RunRequest) -> dict[str, str]:
    task_id = str(uuid.uuid4())
    _TASKS[task_id] = {"done": False, "stage_progress": [], "result": None, "error": None}
    threading.Thread(target=_run_task, args=(task_id, req), daemon=True).start()
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
def api_status(task_id: str) -> dict[str, Any]:
    task = _TASKS.get(task_id)
    if task is None:
        return {"error": "not found"}
    return {
        "done": task["done"],
        "stage_progress": task.get("stage_progress", []),
        "error": task.get("error"),
    }


@app.get("/api/result/{task_id}")
def api_result(task_id: str) -> dict[str, Any]:
    task = _TASKS.get(task_id)
    if task is None:
        return {"error": "not found"}
    return {"done": task["done"], "result": task.get("result"), "error": task.get("error")}


@app.post("/api/resume")
def api_resume(req: ResumeRequest) -> dict[str, Any]:
    result = fe.resume_workflow(req.review_decision, req.feedback)
    return {"result": fe.to_plain(result)}


@app.get("/api/workspace")
def api_workspace() -> dict[str, Any]:
    """返回空 state 的完整工作区 HTML，供前端初始渲染（常驻活动栏 + 三栏）。"""
    return {"html": fe.build_workspace_html({}, "待输入")}


@app.get("/api/package/tree")
def api_package_tree(group: str, package_id: str) -> dict[str, Any]:
    """返回某本地数据包的文件树行 HTML。group: output_packages / demo_packages。"""
    root = fe.OUTPUT_ROOT if group == "output_packages" else fe.DEMO_ROOT
    package_dir = root / package_id
    if not package_dir.is_dir():
        return {"error": "not found"}
    return {"html": "".join(fe._package_file_rows(package_dir))}


# 静态前端（设计稿改造后的 index.html）
if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")


def main() -> None:
    import uvicorn

    uvicorn.run("rdi.server:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
