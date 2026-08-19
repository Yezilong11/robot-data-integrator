"""前端渲染与运行逻辑库（FastAPI 静态前端复用）。

提供演示/真实两种运行模式的工作流封装（``run_graph`` / ``resume_workflow``）
与工作区 HTML 渲染函数（``build_workspace_html`` 及各 ``render_*``）。
原 Gradio 前端 UI 已废弃，仅保留本模块的纯逻辑函数供 ``rdi.server`` 调用。
"""

from __future__ import annotations

import asyncio
import html as _html
import importlib
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

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
        try:
            return to_plain(value.model_dump(mode="json"))
        except Exception:
            # 二进制 bytes（如 URDF/STL 资产）在 mode="json" 下 pydantic 按 utf-8
            # 解码失败，回退 mode="python" 后由 bytes 分支转为占位描述。
            try:
                return to_plain(value.model_dump(mode="python"))
            except Exception:
                return str(value)
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    if isinstance(value, list | tuple | set):
        return [to_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, bytes):
        return f"<bytes len={len(value)}>"
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

# 工作区内联样式（原样渲染 <style>，前缀 rdi- 避免污染全局）
_DECISION_CSS = """<style>
:root{
  --bg:#0d1117;--bg-sidebar:#010409;--bg-panel:#161b22;--bg-elevated:#161b22;
  --bg-input:#0d1117;--border:#30363d;--border-soft:#21262d;--text:#e6edf3;
  --text-dim:#8b949e;--text-faint:#6e7681;--accent:#f78166;
  --accent-soft:rgba(247,129,102,.12);--accent-glow:rgba(247,129,102,.38);
  --llm:#f78166;--rule:#d29922;--done:#3fb950;--done-soft:rgba(63,185,80,.15);
  --warn:#d29922;--error:#f85149;
  --font-ui:"IBM Plex Sans","PingFang SC","Microsoft YaHei",system-ui,sans-serif;
  --font-mono:"IBM Plex Mono",ui-monospace,"SFMono-Regular",Consolas,monospace;
}
.rdi-app{height:100%;display:flex;flex-direction:column;background:var(--bg);color:var(--text);font-family:var(--font-ui);font-size:14px}
.rdi-app *{box-sizing:border-box;margin:0;padding:0}
/* 标题栏 */
.rdi-titlebar{height:48px;display:flex;align-items:center;gap:14px;padding:0 16px;background:var(--bg-sidebar);border-bottom:1px solid var(--border);flex-shrink:0}
.rdi-brand{display:flex;align-items:center;gap:10px;font-weight:600}
.rdi-logo{width:26px;height:26px;border-radius:7px;background:linear-gradient(135deg,#f78166,#d29922);display:grid;place-items:center;color:#0d1117;font-size:13px;font-weight:700}
.rdi-brand .rdi-sub{color:var(--text-faint);font-weight:400;font-size:12px}
.rdi-spacer{flex:1}
.rdi-chip{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;font-size:12px;font-family:var(--font-mono);border:1px solid var(--border);color:var(--text-dim)}
.rdi-chip .rdi-dot{width:7px;height:7px;border-radius:50%;background:var(--done)}
.rdi-badge{display:inline-flex;align-items:center;gap:6px;padding:4px 11px;border-radius:999px;font-size:12px;font-weight:600;font-family:var(--font-mono)}
.rdi-badge-ok{background:var(--done-soft);color:var(--done);border:1px solid rgba(63,185,80,.3)}
.rdi-badge-llm{background:var(--accent-soft);color:var(--llm);border:1px solid rgba(247,129,102,.35)}
.rdi-badge-llm::before{content:"";width:6px;height:6px;border-radius:50%;background:var(--llm)}
.rdi-badge-rule{background:rgba(210,153,34,.14);color:var(--rule);border:1px solid rgba(210,153,34,.3)}
.rdi-badge-red{background:rgba(248,81,73,.14);color:var(--error);border:1px solid rgba(248,81,73,.3)}
.rdi-badge-gray{background:var(--bg-elevated);color:var(--text-faint);border:1px solid var(--border)}
/* 主工作区 */
.rdi-workspace{flex:1;display:flex;min-height:0}
.rdi-activitybar{width:52px;background:var(--bg-sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;align-items:center;padding-top:8px;gap:4px;flex-shrink:0}
.rdi-act{width:40px;height:40px;border-radius:9px;display:grid;place-items:center;color:var(--text-faint);cursor:pointer;position:relative;font-size:18px;transition:.15s;user-select:none}
.rdi-act:hover{color:var(--text-dim)}
.rdi-act.active{color:var(--accent);background:var(--bg-elevated)}
.rdi-act.active::before{content:"";position:absolute;left:-6px;top:8px;bottom:8px;width:2px;border-radius:2px;background:var(--accent)}
.rdi-actbar-spacer{flex:1}
.rdi-activity-action{width:40px;height:40px;border-radius:9px;display:grid;place-items:center;color:var(--text-faint);cursor:pointer;font-size:18px;transition:.15s;user-select:none}
.rdi-activity-action:hover{color:var(--accent)}
/* 左栏面板 */
.rdi-sidebar{width:270px;min-width:180px;max-width:460px;background:var(--bg-sidebar);border-right:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.rdi-resizer{width:5px;cursor:col-resize;flex-shrink:0;position:relative;z-index:6;background:transparent}
.rdi-resizer::before{content:"";position:absolute;left:2px;top:0;bottom:0;width:1px;background:var(--border)}
.rdi-resizer:hover{background:var(--accent-soft)}
.rdi-resizer:hover::before{background:var(--accent)}
.rdi-panel-head{height:38px;display:flex;align-items:center;justify-content:space-between;padding:0 14px;font-size:11px;font-weight:600;letter-spacing:.6px;color:var(--text-dim);text-transform:uppercase;border-bottom:1px solid var(--border);flex-shrink:0}
.rdi-panel-actions{display:flex;gap:6px}
.rdi-panel-actions span{cursor:pointer;color:var(--text-faint);font-size:14px}
.rdi-panel-actions span:hover{color:var(--text-dim)}
.rdi-panel-body{flex:1;overflow:auto;padding:8px 0;font-family:var(--font-mono);font-size:12.5px;color:var(--text-dim)}
.rdi-panel-body pre{white-space:pre-wrap;word-break:break-all;font-family:var(--font-mono);font-size:12px;line-height:1.7;color:var(--text-dim);padding:8px 12px}
/* 文件树 */
.rdi-tree{font-family:var(--font-mono);font-size:12.5px;line-height:1.9}
.rdi-tree-row{display:flex;align-items:center;gap:6px;padding:2px 10px;white-space:nowrap;color:var(--text-dim);cursor:pointer;position:relative}
.rdi-tree-row:hover{background:var(--bg-elevated);color:var(--text)}
.rdi-tree-row.active{background:var(--bg-elevated);color:var(--text)}
.rdi-tree-row.active::before{content:"";position:absolute;left:0;top:0;bottom:0;width:2px;background:var(--accent)}
.rdi-tree-indent{flex-shrink:0}
.rdi-tree-chev{width:12px;text-align:center;color:var(--text-faint);flex-shrink:0;font-size:10px}
.rdi-tree-ico{width:16px;text-align:center;flex-shrink:0}
.rdi-file-txt{color:#8b949e}
.rdi-file-json{color:#d29922}
.rdi-file-md{color:#f78166}
.rdi-file-urdf{color:#a371f7}
.rdi-file-grasp{color:#3fb950}
.rdi-tree-name{overflow:hidden;text-overflow:ellipsis}
.rdi-tree-meta{margin-left:auto;font-size:11px;color:var(--text-faint)}
.rdi-tree-folder{font-weight:500}
.rdi-pkg-children{padding-left:24px}
/* 中栏 */
.rdi-main{flex:1;display:flex;flex-direction:column;min-width:0;background:var(--bg)}
.rdi-main-scroll{flex:1;overflow:auto;padding:20px 26px;display:flex;flex-direction:column;gap:16px}
.rdi-section-title{font-size:11px;font-weight:600;letter-spacing:.8px;color:var(--text-faint);text-transform:uppercase;display:flex;align-items:center;gap:8px;flex-shrink:0}
.rdi-section-title::after{content:"";flex:1;height:1px;background:var(--border)}
/* 灯带 */
.rdi-wf-rail{display:flex;position:relative;padding:12px 4px 2px;flex-shrink:0}
.rdi-wf-rail::before{content:"";position:absolute;top:19px;left:8px;right:8px;height:2px;background:var(--border);border-radius:2px}
.rdi-wf-stop{flex:1;display:flex;flex-direction:column;align-items:center;gap:8px;position:relative;z-index:1}
.rdi-wf-dot{width:14px;height:14px;border-radius:50%;border:2px solid var(--border);background:var(--bg);transition:.3s}
.rdi-wf-label{font-size:12px;color:var(--text-faint)}
.rdi-wf-done .rdi-wf-dot{background:var(--accent);border-color:var(--accent);box-shadow:0 0 8px var(--accent-glow)}
.rdi-wf-done .rdi-wf-label{color:var(--accent)}
.rdi-wf-current .rdi-wf-dot{background:var(--accent);border-color:#fff;box-shadow:0 0 0 5px var(--accent-glow),0 0 20px var(--accent-glow);animation:rdiPulse 1.5s ease-in-out infinite}
.rdi-wf-current .rdi-wf-label{color:var(--accent);font-weight:600}
@keyframes rdiPulse{0%,100%{box-shadow:0 0 0 4px var(--accent-glow),0 0 16px var(--accent-glow)}50%{box-shadow:0 0 0 8px rgba(247,129,102,.16),0 0 26px var(--accent-glow)}}
/* LLM 分析 */
.rdi-think{flex:1;min-height:180px;background:var(--bg-panel);border:1px solid var(--border);border-radius:12px;padding:20px 22px;display:flex;flex-direction:column}
.rdi-think-head{display:flex;align-items:center;gap:9px;padding-bottom:14px;border-bottom:1px solid var(--border-soft);font-size:12px;font-weight:600;color:var(--llm)}
.rdi-think-head .rdi-stage{color:var(--text-faint);font-weight:400}
.rdi-think-body{flex:1;display:flex;align-items:center;padding:18px 4px;font-family:var(--font-mono);font-size:14px;line-height:1.9;color:var(--text-dim)}
.rdi-think-badge{margin-left:auto;padding:3px 10px;border-radius:999px;font-size:11px;font-family:var(--font-mono);background:var(--accent-soft);color:var(--llm);border:1px solid rgba(247,129,102,.3);font-weight:500;flex-shrink:0}
/* 目标输出 */
.rdi-output{border:1px solid var(--border);border-radius:9px;overflow:hidden;background:var(--bg-panel);flex-shrink:0}
.rdi-output summary{cursor:pointer;padding:10px 16px;list-style:none;display:flex;align-items:center;gap:12px}
.rdi-output summary::-webkit-details-marker{display:none}
.rdi-out-label{color:var(--accent);font-size:11px;font-weight:600;text-transform:uppercase}
.rdi-out-tick{color:var(--done)}
.rdi-out-title{font-size:14px;font-weight:600;color:var(--text);flex:1}
.rdi-out-caret{margin-left:auto;color:var(--text-faint)}
.rdi-out-detail{border-top:1px solid var(--border);padding:12px 16px;font-family:var(--font-mono);font-size:12px;background:var(--bg-sidebar);color:var(--text-dim)}
.rdi-out-file{display:flex;align-items:center;gap:8px;padding:3px 0}
.rdi-out-fico{width:16px;text-align:center;flex-shrink:0}
.rdi-out-fname{overflow:hidden;text-overflow:ellipsis}
.rdi-out-fsize{margin-left:auto;font-size:11px;color:var(--text-faint)}
/* 右栏检查器 */
.rdi-inspector{width:300px;min-width:200px;max-width:520px;background:var(--bg-sidebar);border-left:1px solid var(--border);display:flex;flex-direction:column;flex-shrink:0}
.rdi-tabs{display:flex;border-bottom:1px solid var(--border);flex-shrink:0}
.rdi-tab{flex:1;padding:10px 0;text-align:center;font-size:12px;color:var(--text-faint);cursor:pointer;border-bottom:2px solid transparent;white-space:nowrap;user-select:none}
.rdi-tab.active{color:var(--text);border-bottom-color:var(--accent)}
.rdi-insp-body{flex:1;overflow:auto;padding:16px;font-family:var(--font-mono);font-size:12px;color:var(--text-dim)}
.rdi-insp-pane pre{white-space:pre-wrap;word-break:break-all;font-family:var(--font-mono);font-size:12px;line-height:1.7;color:var(--text-dim)}
.rdi-kv{margin-bottom:14px}
.rdi-kv-k{font-size:11px;color:var(--text-faint);font-weight:600;letter-spacing:.4px;margin-bottom:5px;text-transform:uppercase}
.rdi-kv-v{font-family:var(--font-mono);font-size:12px;color:var(--text-dim);line-height:1.6}
.rdi-good{color:var(--done)}
.rdi-warn{color:var(--warn)}
.rdi-kv-list{margin:0;padding-left:16px}
.rdi-kv-list li{margin-bottom:4px;font-size:12px;color:var(--text-dim);line-height:1.6}
/* 底部状态栏 */
.rdi-statusbar{height:28px;display:flex;align-items:center;gap:16px;padding:0 14px;background:var(--bg-sidebar);border-top:1px solid var(--border);font-family:var(--font-mono);font-size:11.5px;color:var(--text-dim);flex-shrink:0}
.rdi-statusbar .rdi-left{display:flex;align-items:center;gap:16px}
.rdi-statusbar .rdi-right{margin-left:auto;display:flex;align-items:center;gap:16px}
.rdi-sb{display:flex;align-items:center;gap:6px}
.rdi-sb .rdi-ok{color:var(--done)}
.rdi-sb .rdi-llm{color:var(--llm)}
.rdi-spinner{width:11px;height:11px;border:2px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:rdiSpin .8s linear infinite}
@keyframes rdiSpin{to{transform:rotate(360deg)}}
.rdi-caret{display:inline-block;width:2px;height:14px;background:var(--accent);margin-left:2px;vertical-align:-2px;animation:rdiBlink 1s steps(1) infinite}
@keyframes rdiBlink{50%{opacity:0}}
.rdi-key{color:var(--text-faint);font-weight:600}
.rdi-req-list{display:flex;flex-direction:column;gap:10px;padding:0 10px}
.rdi-req-card{background:var(--bg-panel);border:1px solid var(--border);border-radius:8px;padding:10px 12px}
.rdi-req-title{font-weight:600;color:var(--text);margin-bottom:8px;font-size:13px}
.rdi-req-line{display:flex;gap:8px;padding:3px 0;font-size:12px}
.rdi-req-k{color:var(--text-faint);width:64px;flex-shrink:0}
.rdi-req-v{color:var(--text-dim);word-break:break-all}
/* 深色滚动条 */
.rdi-app ::-webkit-scrollbar{width:8px;height:8px}
.rdi-app ::-webkit-scrollbar-track{background:transparent}
.rdi-app ::-webkit-scrollbar-thumb{background:#30363d;border-radius:4px}
.rdi-app ::-webkit-scrollbar-thumb:hover{background:#484f58}
.rdi-app *{scrollbar-width:thin;scrollbar-color:#30363d transparent}
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


def _file_icon(name: str) -> str:
    """按文件扩展名返回类型图标（VSCode 风格占位）。"""
    if name.endswith(".json"):
        return "{}"
    if name.endswith(".md"):
        return "#"
    if name.endswith(".urdf") or name.endswith(".xacro"):
        return "⧉"
    if name.endswith(".pkl") or name.endswith(".npz"):
        return "◈"
    return "≡"


def _file_icon_class(name: str) -> str:
    """文件类型图标的颜色 class（设计稿：json 琥珀 / md 珊瑚 / urdf 紫 / grasp 绿）。"""
    if name.endswith(".json"):
        return "rdi-file-json"
    if name.endswith(".md"):
        return "rdi-file-md"
    if name.endswith(".urdf") or name.endswith(".xacro"):
        return "rdi-file-urdf"
    if name.endswith(".pkl") or name.endswith(".npz"):
        return "rdi-file-grasp"
    return "rdi-file-txt"


def _format_size(n: Any) -> str:
    """把字节数格式化为易读大小（B/KB/MB）。"""
    if n is None:
        return ""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return ""
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.1f} KB"
    return f"{n / (1024 * 1024):.1f} MB"


def _tree_row_html(indent: int, name: str, is_dir: bool, size: Any = None) -> str:
    indent_html = f'<span class="rdi-tree-indent" style="width:{indent * 16}px"></span>'
    if is_dir:
        return (
            '<div class="rdi-tree-row rdi-tree-folder">'
            f"{indent_html}"
            '<span class="rdi-tree-chev">▾</span>'
            '<span class="rdi-tree-ico">📁</span>'
            f'<span class="rdi-tree-name">{_html.escape(name)}</span>'
            "</div>"
        )
    meta = _format_size(size)
    return (
        '<div class="rdi-tree-row">'
        f"{indent_html}"
        f'<span class="rdi-tree-ico {_file_icon_class(name)}">{_file_icon(name)}</span>'
        f'<span class="rdi-tree-name">{_html.escape(name)}</span>'
        f'<span class="rdi-tree-meta">{meta}</span>'
        "</div>"
    )


def _nested_tree_rows(paths: list[str], sizes: dict[str, Any], start_indent: int = 0) -> list[str]:
    """把扁平路径列表转成嵌套可折叠树（目录用 rdi-group 包裹 children）。"""
    tree: dict[str, dict[str, Any]] = {}
    for rel in paths:
        parts = rel.split("/")
        node = tree
        for part in parts[:-1]:
            node = node.setdefault(part, {"type": "dir", "children": {}})["children"]
        node[parts[-1]] = {"type": "file", "size": sizes.get(rel)}

    def render(name: str, meta: dict[str, Any], indent: int) -> str:
        if meta["type"] == "file":
            return _tree_row_html(indent, name, False, meta.get("size"))
        children = meta["children"]
        items = sorted(children.items(), key=lambda kv: (0 if kv[1]["type"] == "dir" else 1, kv[0]))
        inner = "".join(render(cn, cv, indent + 1) for cn, cv in items)
        indent_html = f'<span class="rdi-tree-indent" style="width:{indent * 16}px"></span>'
        return (
            '<div class="rdi-tree-row rdi-tree-folder rdi-group">'
            f"{indent_html}"
            '<span class="rdi-tree-chev">▾</span>'
            '<span class="rdi-tree-ico">📁</span>'
            f'<span class="rdi-tree-name">{_html.escape(name)}</span>'
            "</div>"
            f'<div class="rdi-group-children">{inner}</div>'
        )

    items = sorted(tree.items(), key=lambda kv: (0 if kv[1]["type"] == "dir" else 1, kv[0]))
    return [render(cn, cv, start_indent) for cn, cv in items]


def _package_file_rows(package_dir: Path) -> list[str]:
    """返回某数据包目录下的文件树行（嵌套可折叠，从 0 缩进开始）。"""
    paths = sorted(
        str(p.relative_to(package_dir)).replace("\\", "/")
        for p in package_dir.rglob("*")
        if p.is_file()
    )
    sizes: dict[str, Any] = {}
    for rel in paths:
        try:
            sizes[rel] = (package_dir / rel).stat().st_size
        except OSError:
            sizes[rel] = None
    return _nested_tree_rows(paths, sizes)


def _local_package_tree_rows() -> list[str]:
    """生成本地数据包列表文件树行（分组与数据包均可折叠展开）。"""
    rows: list[str] = []
    for root in (OUTPUT_ROOT, DEMO_ROOT):
        if not root.exists():
            continue
        pkgs = sorted(p for p in root.iterdir() if p.is_dir())
        if not pkgs:
            continue
        rows.append(
            '<div class="rdi-tree-row rdi-tree-folder rdi-group">'
            '<span class="rdi-tree-chev">▾</span>'
            '<span class="rdi-tree-ico">📁</span>'
            f'<span class="rdi-tree-name">{_html.escape(root.name)}</span>'
            "</div>"
            '<div class="rdi-group-children">'
        )
        for p in pkgs:
            rows.append(
                '<div class="rdi-tree-row rdi-pkg" '
                f'data-group="{_html.escape(root.name)}" data-package="{_html.escape(p.name)}">'
                '<span class="rdi-tree-indent" style="width:16px"></span>'
                '<span class="rdi-tree-chev">▸</span>'
                '<span class="rdi-tree-ico">📦</span>'
                f'<span class="rdi-tree-name">{_html.escape(p.name)}</span>'
                "</div>"
                '<div class="rdi-pkg-children" style="display:none"></div>'
            )
        rows.append("</div>")
    return rows


def render_file_tree_html(state: dict[str, Any]) -> str:
    """VSCode 风格文件树：优先包目录（含真实大小），否则 manifest files[].path 兜底。"""
    package_dir = get_package_dir(state)
    sizes: dict[str, Any] = {}
    if package_dir is not None and package_dir.exists():
        paths = sorted(
            str(p.relative_to(package_dir)).replace("\\", "/")
            for p in package_dir.rglob("*")
            if p.is_file()
        )
        for rel in paths:
            try:
                sizes[rel] = (package_dir / rel).stat().st_size
            except OSError:
                sizes[rel] = None
    else:
        manifest = to_plain(state.get("experiment_package"))
        paths = sorted(
            {
                str(f.get("path", "")).replace("\\", "/")
                for f in manifest.get("files", [])
                if isinstance(f, dict) and f.get("path")
            }
            if isinstance(manifest, dict)
            else []
        )
        if isinstance(manifest, dict):
            for f in manifest.get("files", []):
                if isinstance(f, dict) and f.get("path"):
                    sizes[str(f["path"]).replace("\\", "/")] = f.get("file_size")

    if not paths:
        local_rows = _local_package_tree_rows()
        if local_rows:
            return '<div class="rdi-tree">' + "".join(local_rows) + "</div>"
        return '<div class="rdi-key">暂无数据包文件</div>'

    root_name: str | None = None
    if package_dir is not None and package_dir.exists():
        root_name = package_dir.name
    else:
        manifest = to_plain(state.get("experiment_package"))
        if isinstance(manifest, dict) and isinstance(manifest.get("package_info"), dict):
            root_name = str(manifest["package_info"].get("package_id", "")) or None

    rows: list[str] = []
    if root_name:
        rows.append(
            '<div class="rdi-tree-row rdi-tree-folder rdi-group">'
            '<span class="rdi-tree-chev">▾</span>'
            '<span class="rdi-tree-ico">📦</span>'
            f'<span class="rdi-tree-name">{_html.escape(root_name)}</span>'
            "</div>"
            '<div class="rdi-group-children">'
        )
        rows.extend(_nested_tree_rows(paths, sizes, start_indent=1))
        rows.append("</div>")
    else:
        rows.extend(_nested_tree_rows(paths, sizes))
    return '<div class="rdi-tree">' + "".join(rows) + "</div>"


def render_workflow_html(state: dict[str, Any]) -> str:
    """灯带式 5 节点工作流：完成点亮 / 当前呼吸 / 未开始灰点。"""
    completed = _board_completed(state)
    current_idx = min(len(completed), len(BOARD_STAGES) - 1)
    stops: list[str] = []
    for i, (name, label) in enumerate(BOARD_STAGES):
        if name in completed and i != current_idx:
            cls = "rdi-wf-done"
        elif i == current_idx:
            cls = "rdi-wf-current"
        else:
            cls = ""
        stops.append(
            '<div class="rdi-wf-stop ' + cls + '">'
            '<span class="rdi-wf-dot"></span>'
            f'<span class="rdi-wf-label">{_html.escape(label)}</span>'
            "</div>"
        )
    return '<div class="rdi-wf-rail">' + "".join(stops) + "</div>"


def _current_thinking(state: dict[str, Any]) -> tuple[str, str, str]:
    """反推当前阶段的 LLM 思考文本与来源标注（不含 confidence 数字）。"""
    completed = _board_completed(state)
    current_idx = min(len(completed), len(BOARD_STAGES) - 1)
    name, label = BOARD_STAGES[current_idx]
    text = "该阶段尚未执行"
    source = "规则兜底"

    if name == "retrieve_data":
        plans = to_plain(state.get("retrieval_plan", {}))
        for req_id, plan in plans.items():
            if isinstance(plan, dict) and plan.get("reason"):
                text = str(plan["reason"])
                source = _decision_source(state, "retrieval_plan", True, str(req_id))
                break
    elif name == "parse_and_convert":
        sm = to_plain(state.get("semantic_map", {}))
        for req_id, conv in sm.items():
            if isinstance(conv, dict):
                text = (
                    f"语义类型 {conv.get('semantic_type', '?')}，"
                    f"旋转 {conv.get('rotation', '?')}，原点 {conv.get('origin', '?')}，"
                    f"单位 {conv.get('unit', '?')}"
                )
                source = _decision_source(state, "unify_semantics", True, str(req_id))
                break
    elif name == "validate":
        issues = to_plain(state.get("validation_issues", []))
        text = f"质量校验发现 {len(issues)} 项问题" if issues else "质量校验通过，无阻塞性问题"
        source = "规则兜底"
    elif name == "assemble_package":
        qe = to_plain(state.get("quality_explanation"))
        if isinstance(qe, dict) and qe.get("summary"):
            text = str(qe["summary"])
            source = _decision_source(state, "explain_quality", True)
    elif name == "human_review":
        sug = to_plain(state.get("review_suggestions"))
        payload = state.get("interrupt_payload")
        payload_sug = None
        if isinstance(payload, dict) and isinstance(payload.get("suggestions"), dict):
            payload_sug = to_plain(payload["suggestions"])
        data = sug or payload_sug
        if isinstance(data, dict):
            if data.get("rationale"):
                text = str(data["rationale"])
            elif data.get("issues"):
                text = "；".join(str(i) for i in data.get("issues", []))
            src = data.get("source")
            if src == "llm":
                source = "LLM 生成"
            elif src == "rule":
                source = "规则兜底"
            else:
                source = _decision_source(state, "review_suggestions", True)

    return label, text, source


# 阶段 → LLM 决策点名称（设计稿 stage 文案格式：校验阶段 · explain_quality）
_STAGE_DECISION: dict[str, str] = {
    "retrieve_data": "retrieval_plan",
    "parse_and_convert": "unify_semantics",
    "validate": "explain_quality",
    "assemble_package": "assemble_package",
    "human_review": "review_suggestions",
}


def render_llm_analysis_html(state: dict[str, Any]) -> str:
    """LLM 分析主体视图：思考文本 + 来源标注，不含 confidence 数字。"""
    label, text, source = _current_thinking(state)
    completed = _board_completed(state)
    current_idx = min(len(completed), len(BOARD_STAGES) - 1)
    name, _ = BOARD_STAGES[current_idx]
    stage_txt = f"{label}阶段 · {_STAGE_DECISION.get(name, name)}"
    # 规则兜底不显示来源标注（用户要求），仅 LLM 生成时展示 pill 徽章
    badge = '<span class="rdi-think-badge">LLM 生成</span>' if source == "LLM 生成" else ""
    return (
        '<div class="rdi-think">'
        '<div class="rdi-think-head"><span>◉</span><span>LLM 分析</span>'
        f'<span class="rdi-stage">· {_html.escape(stage_txt)}</span>'
        f"{badge}"
        "</div>"
        f'<div class="rdi-think-body">{_html.escape(text)}<span class="rdi-caret"></span></div>'
        "</div>"
    )


def _output_files(state: dict[str, Any]) -> list[tuple[str, Any]]:
    """返回数据包文件清单 [(相对路径, 大小), ...]，优先包目录，否则 manifest 兜底。"""
    package_dir = get_package_dir(state)
    files: list[tuple[str, Any]] = []
    if package_dir is not None and package_dir.exists():
        for p in sorted(package_dir.rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(package_dir)).replace("\\", "/")
                try:
                    size: Any = p.stat().st_size
                except OSError:
                    size = None
                files.append((rel, size))
        return files
    manifest = to_plain(state.get("experiment_package"))
    if isinstance(manifest, dict):
        for f in manifest.get("files", []):
            if isinstance(f, dict) and f.get("path"):
                files.append((str(f["path"]).replace("\\", "/"), f.get("file_size")))
    return files


def render_target_output_html(state: dict[str, Any]) -> str:
    """目标输出：单行汇总 + 可展开文件清单（图标 + 名称 + 大小）。"""
    manifest = to_plain(state.get("experiment_package"))
    if manifest:
        title = "robot-data-package 已生成"
    elif state.get("errors"):
        title = "运行失败，未生成数据包"
    else:
        title = "尚未生成数据包"

    detail = "".join(
        '<div class="rdi-out-file">'
        f'<span class="rdi-out-fico {_file_icon_class(rel)}">{_file_icon(rel)}</span>'
        f'<span class="rdi-out-fname">{_html.escape(rel)}</span>'
        f'<span class="rdi-out-fsize">{_format_size(size)}</span>'
        "</div>"
        for rel, size in _output_files(state)
    )
    return (
        '<details class="rdi-output">'
        '<summary><span class="rdi-out-label"><span class="rdi-out-tick">✓</span>目标输出</span>'
        f'<span class="rdi-out-title">{_html.escape(title)}</span>'
        '<span class="rdi-out-caret">▾</span></summary>'
        f'<div class="rdi-out-detail">{detail}</div>'
        "</details>"
    )


def render_inspector_html(state: dict[str, Any]) -> str:
    """检查器「详情」Tab：当前文件 / 需求状态 / 语义约定 / 质量校验 / 来源标注。"""
    files = _output_files(state)
    current_file = files[0][0] if files else "—"

    req_line = "—"
    _headers, rows = build_req_status_table(state)
    if rows:
        row = rows[0]
        req_line = f'<span class="rdi-good">{_html.escape(str(row[2]))}</span> · 数据源 {_html.escape(str(row[3] or "—"))}'

    semantic_html = "—"
    sm = to_plain(state.get("semantic_map", {}))
    for conv in sm.values():
        if isinstance(conv, dict):
            semantic_html = (
                f"type: {_html.escape(str(conv.get('semantic_type', '?')))}<br>"
                f"rotation: {_html.escape(str(conv.get('rotation', '?')))}<br>"
                f"origin: {_html.escape(str(conv.get('origin', '?')))} · "
                f"unit: {_html.escape(str(conv.get('unit', '?')))}"
            )
            break

    qe = to_plain(state.get("quality_explanation"))
    issues = to_plain(state.get("validation_issues", []))
    checks: list[str] = []
    if isinstance(qe, dict):
        for s in qe.get("strengths", []):
            checks.append(f'<li class="rdi-good">✓ {_html.escape(str(s))}</li>')
        for r in qe.get("risks", []):
            checks.append(f'<li class="rdi-warn">△ {_html.escape(str(r))}</li>')
    if not checks:
        checks.append(
            f'<li class="rdi-warn">△ {len(issues)} 项校验问题</li>'
            if issues
            else '<li class="rdi-good">✓ 无校验问题</li>'
        )
    quality_html = '<ul class="rdi-kv-list">' + "".join(checks) + "</ul>"

    source_label = _decision_source(state, "explain_quality", bool(qe))
    if source_label == "规则兜底":
        source_label = "—"

    def _kv(k: str, v: str) -> str:
        return f'<div class="rdi-kv"><div class="rdi-kv-k">{k}</div><div class="rdi-kv-v">{v}</div></div>'

    return "".join(
        [
            _kv("当前文件", _html.escape(current_file)),
            _kv("需求状态", req_line),
            _kv("语义约定", semantic_html),
            _kv("质量校验", quality_html),
            _kv("来源标注", f'<span style="color:var(--llm)">{source_label}</span>'),
        ]
    )


_WORKSPACE_JS = """
(function () {
  var acts = document.querySelectorAll('.rdi-act');
  var panes = document.querySelectorAll('.rdi-sidebar .rdi-pane');
  var titles = {explorer: '资源管理器', retrieve: '数据检索', decision: '决策', review: '审查', log: '日志', settings: '设置'};
  var titleEl = document.getElementById('rdi-panel-title');
  acts.forEach(function (a) {
    a.addEventListener('click', function () {
      acts.forEach(function (x) { x.classList.remove('active'); });
      a.classList.add('active');
      var p = a.getAttribute('data-panel');
      panes.forEach(function (n) { n.style.display = (n.getAttribute('data-panel') === p) ? '' : 'none'; });
      if (titleEl) titleEl.textContent = titles[p] || '';
    });
  });
  var tabs = document.querySelectorAll('.rdi-tab');
  var insp = document.querySelectorAll('.rdi-insp-pane');
  tabs.forEach(function (t) {
    t.addEventListener('click', function () {
      tabs.forEach(function (x) { x.classList.remove('active'); });
      t.classList.add('active');
      var k = t.getAttribute('data-tab');
      insp.forEach(function (n) { n.style.display = (n.getAttribute('data-tab') === k) ? '' : 'none'; });
    });
  });
})();
"""


def _req_status_table_html(state: dict[str, Any]) -> str:
    """数据需求状态：每个需求一张竖排卡片（字段名纵向排列）。"""
    _headers, rows = build_req_status_table(state)
    if not rows:
        return '<div class="rdi-key">暂无数据需求</div>'
    cards: list[str] = []
    for row in rows:
        fields = [
            ("类型", row[1]),
            ("状态", row[2]),
            ("数据源", row[3]),
            ("fallback", row[4]),
            ("失败原因", row[5]),
        ]
        lines = "".join(
            '<div class="rdi-req-line">'
            f'<span class="rdi-req-k">{_html.escape(k)}</span>'
            f'<span class="rdi-req-v">{_html.escape(str(v or "—"))}</span>'
            "</div>"
            for k, v in fields
        )
        cards.append(
            '<div class="rdi-req-card">'
            f'<div class="rdi-req-title">{_html.escape(str(row[0]))}</div>'
            f"{lines}"
            "</div>"
        )
    return '<div class="rdi-req-list">' + "".join(cards) + "</div>"


def _derive_status(state: dict[str, Any]) -> str:
    if state.get("errors"):
        return "运行失败"
    if state.get("experiment_package"):
        return "运行完成"
    return "运行中"


def _status_badge(status: str) -> str:
    if "运行失败" in status:
        return '<span class="rdi-badge rdi-badge-red">失败</span>'
    if "运行完成" in status:
        return '<span class="rdi-badge rdi-badge-ok">完成</span>'
    if any(k in status for k in ("继续运行", "已生成中间结果", "待审查")):
        return '<span class="rdi-badge rdi-badge-rule">待审查</span>'
    if any(k in status for k in ("待输入", "请输入", "没有待继续")):
        return '<span class="rdi-badge rdi-badge-gray">待输入</span>'
    return '<span class="rdi-badge rdi-badge-ok">运行中</span>'


def build_workspace_html(state: dict[str, Any], status: str) -> str:
    """完整工作区 HTML：标题栏 + 活动栏 + 左栏 6 面板 + 中栏 + 检查器 + 状态栏。"""
    run_id = _html.escape(str(state.get("run_id", "") or "—"))
    file_tree = render_file_tree_html(state)
    req_table = _req_status_table_html(state)
    semantic = _html.escape(semantic_map_json(state))
    missing = _html.escape(
        json.dumps(to_plain(state.get("missing_items", [])), ensure_ascii=False, indent=2)
    )
    provenance = _html.escape(
        "\n".join(str(x) for x in to_plain(state.get("provenance", []))) or "暂无日志"
    )
    llm_usage = _html.escape(
        json.dumps(to_plain(state.get("llm_usage", [])), ensure_ascii=False, indent=2)
    )
    manifest = _html.escape(
        json.dumps(to_plain(state.get("experiment_package", {})), ensure_ascii=False, indent=2)
    )
    llm_count = len(to_plain(state.get("llm_usage", [])))
    completed_count = len(_board_completed(state))
    elapsed = sum(
        float(u.get("elapsed", 0))
        for u in to_plain(state.get("llm_usage", []))
        if isinstance(u, dict) and u.get("elapsed")
    )
    error_count = len(to_plain(state.get("errors", [])))
    error_label = "无错误" if error_count == 0 else f"{error_count} 错误"

    return _DECISION_CSS + (
        '<div class="rdi-app">'
        '<header class="rdi-titlebar">'
        '<div class="rdi-brand"><span class="rdi-logo">R</span>Robot Data Integrator'
        ' <span class="rdi-sub">· LLM 智能决策工作区</span></div>'
        '<div class="rdi-spacer"></div>'
        f'<span class="rdi-chip"><span class="rdi-dot"></span>run_id {run_id}</span>'
        f"{_status_badge(status)}"
        '<span class="rdi-badge rdi-badge-llm">LLM 引擎</span>'
        "</header>"
        '<div class="rdi-workspace">'
        '<nav class="rdi-activitybar">'
        '<div class="rdi-act active" data-panel="explorer" title="资源管理器">🗂</div>'
        '<div class="rdi-act" data-panel="retrieve" title="数据检索">⌕</div>'
        '<div class="rdi-act" data-panel="decision" title="决策">◉</div>'
        '<div class="rdi-act" data-panel="review" title="审查">✓</div>'
        '<div class="rdi-act" data-panel="log" title="日志">▷</div>'
        '<div class="rdi-act" data-panel="settings" title="设置">⚙</div>'
        '<div class="rdi-actbar-spacer"></div>'
        '<div class="rdi-activity-action" data-action="new-session" title="新会话（清空输入并重新开始）">↻</div>'
        "</nav>"
        '<aside class="rdi-sidebar" data-min="180" data-max="460">'
        '<div class="rdi-panel-head"><span id="rdi-panel-title">资源管理器</span>'
        '<div class="rdi-panel-actions">'
        '<span data-action="refresh" title="刷新">⟳</span>'
        '<span data-action="expand" title="全部展开">＋</span>'
        '<span data-action="collapse" title="全部折叠">▾</span>'
        "</div></div>"
        f'<div class="rdi-panel-body rdi-pane" data-panel="explorer">{file_tree}</div>'
        f'<div class="rdi-panel-body rdi-pane" data-panel="retrieve" style="display:none">{req_table}</div>'
        f'<div class="rdi-panel-body rdi-pane" data-panel="decision" style="display:none"><pre>{semantic}</pre></div>'
        f'<div class="rdi-panel-body rdi-pane" data-panel="review" style="display:none"><pre>审查决定与反馈请在下方输入区提交\n\nmissing_items\n{missing}</pre></div>'
        f'<div class="rdi-panel-body rdi-pane" data-panel="log" style="display:none"><pre>provenance 日志\n{provenance}\n\nllm_usage\n{llm_usage}</pre></div>'
        '<div class="rdi-panel-body rdi-pane" data-panel="settings" style="display:none"><pre>运行模式与本地文件注入请在下方输入区设置</pre></div>'
        "</aside>"
        '<div class="rdi-resizer" data-target="sidebar" data-dir="right"></div>'
        '<main class="rdi-main">'
        '<div class="rdi-main-scroll">'
        '<div class="rdi-section-title">工作流 · 实时点亮</div>'
        f"{render_workflow_html(state)}"
        '<div class="rdi-section-title">LLM 分析 · 实时思考</div>'
        f"{render_llm_analysis_html(state)}"
        '<div class="rdi-section-title">目标输出</div>'
        f"{render_target_output_html(state)}"
        "</div>"
        "</main>"
        '<div class="rdi-resizer" data-target="inspector" data-dir="left"></div>'
        '<aside class="rdi-inspector" data-min="200" data-max="520">'
        '<div class="rdi-tabs">'
        '<div class="rdi-tab active" data-tab="detail">详情</div>'
        '<div class="rdi-tab" data-tab="manifest">manifest</div>'
        '<div class="rdi-tab" data-tab="semantic">语义</div>'
        '<div class="rdi-tab" data-tab="llm">LLM 调用</div>'
        "</div>"
        '<div class="rdi-insp-body">'
        f'<div class="rdi-insp-pane" data-tab="detail">{render_inspector_html(state)}</div>'
        f'<div class="rdi-insp-pane" data-tab="manifest" style="display:none"><pre>{manifest}</pre></div>'
        f'<div class="rdi-insp-pane" data-tab="semantic" style="display:none"><pre>{semantic}</pre></div>'
        f'<div class="rdi-insp-pane" data-tab="llm" style="display:none"><pre>{llm_usage}</pre></div>'
        "</div>"
        "</aside>"
        "</div>"
        '<footer class="rdi-statusbar">'
        '<div class="rdi-left">'
        f'<span class="rdi-sb">⎇ 阶段 {completed_count}/5</span>'
        f'<span class="rdi-sb"><span class="rdi-spinner"></span> {_html.escape(status)}</span>'
        '<span class="rdi-sb rdi-stage-text" id="rdi-stage-text"></span>'
        "</div>"
        '<div class="rdi-right">'
        f'<span class="rdi-sb"><span class="rdi-llm">◉</span> LLM 调用 <span class="rdi-llm">{llm_count} 次</span></span>'
        f'<span class="rdi-sb">⧗ 耗时 {elapsed:.1f}s</span>'
        f'<span class="rdi-sb"><span class="rdi-ok">✓</span> {error_label}</span>'
        "</div>"
        "</footer>"
        "</div>"
    )


def build_decision_board(state: dict[str, Any]) -> str:
    """中栏决策看板 HTML：完整工作区（活动栏 + 三栏 + 状态栏）。"""
    return build_workspace_html(state, _derive_status(state))


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
