"""第二次联调端到端演示脚本。

目标：用 "Franka Panda grasps YCB banana in MuJoCo simulation" 生成真实数据包。

实现方式：
- 由于真实 LLM 调用在本机网络环境下不稳定/耗时不可控，本脚本先尝试把
  ``parse_goal`` 替换为确定性实现，直接给出 ``robot_urdf`` / ``mesh`` /
  ``sim_config`` 三类需求；
- 随后驱动 LangGraph 的其余真实节点
  ``retrieve_data → parse_convert → validate → assemble_package``；
- 所有 Adapter / Skill 均为真实实现，因此数据包中的文件来自真实数据源。

这符合任务要求：在 LLM 不可用时可用确定性辅助脚本跑通其余真实工作流。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

# ─── 先导入 builder 模块，再替换 builder 中的节点引用。
# 注意：不能先 ``from rdi.graph.nodes import parse_goal``，因为那会触发
# ``rdi.graph.nodes`` 子包初始化并把原始函数对象绑定到 builder 的导入名中，
# 后续再 patch 模块属性不会生效。直接 patch ``builder.node_parse_goal`` 可
# 确保 ``build_graph()`` 注册的是确定性实现。
from rdi.graph import builder as _builder_module
from rdi.graph.nodes import retrieve_data as _retrieve_data_module
from rdi.models import DataReq, DataReqType, DataSource, GoalSpec, Priority

GOAL = "Franka Panda grasps YCB banana in MuJoCo simulation"


class _NoOpHermesEngine:
    """禁用 Hermes 经验库/Embedding 调用的占位引擎。"""

    def inject_experience(self, task_description: str, req_type: str) -> str:
        return ""

    def record_experience(self, *args: object, **kwargs: object) -> None:
        return None

    def get_source_priority(self, req_type: str, candidates: list[str] | None = None) -> list[str]:
        return []


_retrieve_data_module._get_hermes_engine = lambda: _NoOpHermesEngine()


def _build_requirements() -> list[DataReq]:
    """生成目标对应的数据需求清单（与 LLM 期望输出等价）。"""
    # description 被 retrieve_data 直接当作 Adapter 搜索词，因此使用各
    # Adapter fallback 列表能命中短关键词，避免中文长句导致搜索失败。
    return [
        DataReq(
            req_id="req_000",
            req_type=DataReqType.ROBOT_URDF,
            description="panda",
            priority=Priority.REQUIRED,
            keywords=["Franka", "Panda", "URDF"],
            fallback_sources=[DataSource.FRANKA],
            expected_format="URDF",
        ),
        DataReq(
            req_id="req_001",
            req_type=DataReqType.MESH,
            description="banana",
            priority=Priority.REQUIRED,
            keywords=["YCB", "banana", "mesh"],
            fallback_sources=[DataSource.YCB],
            expected_format="STL",
        ),
        DataReq(
            req_id="req_002",
            req_type=DataReqType.SIM_CONFIG,
            description="franka",
            priority=Priority.REQUIRED,
            keywords=["MuJoCo", "simulation", "MJCF"],
            fallback_sources=[DataSource.MUJOCO],
            expected_format="XML",
        ),
    ]


async def _deterministic_parse_goal(state: dict[str, Any]) -> dict[str, Any]:
    """确定性目标解析节点：绕过 LLM，直接返回已知需求。"""
    goal = state.get("user_goal") or GOAL
    now = datetime.now().isoformat()
    return {
        "parsed_goal": GoalSpec(
            research_topic=goal,
            robot_type="Franka Panda",
            simulator="MuJoCo",
            experiment_type="grasping",
        ),
        "data_requirements": _build_requirements(),
        "provenance": [
            f"[{now}] parse_goal: 使用确定性需求清单（绕过 LLM），"
            f"生成 {len(_build_requirements())} 条数据需求"
        ],
    }


# 替换 builder 模块中的 parse_goal 节点引用
_builder_module.node_parse_goal = _deterministic_parse_goal

# 通过 builder 模块调用 build_graph，此时注册的节点已经是确定性实现
build_graph = _builder_module.build_graph

print("[demo] 模块导入完成，准备构建图", flush=True)


def _verify_package(package_dir: Path) -> dict[str, Any]:
    """验证生成的数据包：URDF 可解析、mesh 可加载、文件类别统计。"""
    result: dict[str, Any] = {
        "package_dir": str(package_dir),
        "files": [],
        "categories": {},
        "urdf_parsable": False,
        "mesh_loadable": False,
        "errors": [],
    }

    if not package_dir.exists():
        result["errors"].append("package_dir 不存在")
        return result

    files_dir = package_dir / "files"
    if not files_dir.exists():
        result["errors"].append("files 目录不存在")
        return result

    files = sorted(files_dir.rglob("*"))
    result["files"] = [str(f.relative_to(package_dir)) for f in files if f.is_file()]

    # 类别统计（按文件扩展名粗略归类）
    categories: dict[str, list[str]] = {"urdf": [], "mesh": [], "sim_config": [], "other": []}
    mesh_exts = {".stl", ".obj", ".ply", ".dae", ".glb"}
    for f in files:
        if not f.is_file():
            continue
        ext = f.suffix.lower()
        if ext == ".urdf":
            categories["urdf"].append(str(f))
        elif ext in mesh_exts:
            categories["mesh"].append(str(f))
        elif ext == ".xml":
            categories["sim_config"].append(str(f))
        else:
            categories["other"].append(str(f))
    result["categories"] = {k: len(v) for k, v in categories.items() if v}

    # URDF 可解析性
    try:
        import yourdfpy
    except Exception as exc:  # pragma: no cover - 依赖可选
        result["errors"].append(f"yourdfpy 未安装: {exc}")
        yourdfpy = None  # type: ignore[assignment]

    if yourdfpy is not None and categories["urdf"]:
        urdf_path = categories["urdf"][0]
        try:
            yourdfpy.URDF.load(urdf_path, load_meshes=False)
            result["urdf_parsable"] = True
        except Exception as exc:
            result["errors"].append(f"URDF 解析失败: {exc}")

    # Mesh 可加载性
    try:
        import trimesh
    except Exception as exc:  # pragma: no cover - 依赖可选
        result["errors"].append(f"trimesh 未安装: {exc}")
        trimesh = None  # type: ignore[assignment]

    if trimesh is not None and categories["mesh"]:
        mesh_path = categories["mesh"][0]
        try:
            mesh = trimesh.load(mesh_path, force="mesh")
            result["mesh_loadable"] = True
            result["mesh_faces"] = len(mesh.faces)  # type: ignore[attr-defined]
        except Exception as exc:
            result["errors"].append(f"Mesh 加载失败: {exc}")

    return result


async def main() -> None:
    print("[demo] 开始构建 LangGraph", flush=True)
    graph = build_graph()
    print("[demo] 图构建完成，开始调用", flush=True)

    state: dict[str, Any] = {
        "user_goal": GOAL,
        "iteration_count": 0,
        "review_decision": "satisfied",
        "user_feedback": [],
        "provenance": [],
        "errors": [],
    }

    final_state = await graph.ainvoke(
        state,
        thread_id="second-integration-demo",
        checkpoint_ns="demo",
        checkpoint_id="run",
    )

    package = final_state.get("experiment_package")
    if package is None:
        print("未生成数据包")
        print("errors:", final_state.get("errors"))
        return

    package_dir = Path(package.output_dir)
    print(f"数据包 ID: {package.package_info.get('package_id')}")
    print(f"输出目录: {package_dir}")
    print(f"文件数: {len(package.files)}")
    print(f"缺失项: {len(package.missing_items)}")
    print(
        f"质量报告: {package.quality_report.fulfilled}/"
        f"{package.quality_report.total_requirements} 需求满足"
    )

    if package.files:
        print("\n文件列表:")
        for f in package.files:
            print(f"  - {f.path} ({f.format}, confidence={f.confidence})")

    manifest_path = package_dir / "manifest.json"
    print(f"\nmanifest.json: {manifest_path}")
    print(json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2)[:2000])

    print("\n--- 数据包验证 ---")
    verify = _verify_package(package_dir)
    print(json.dumps(verify, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
