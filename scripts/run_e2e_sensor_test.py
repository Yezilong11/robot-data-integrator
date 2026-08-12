"""SENSOR_DATA 端到端测试驱动。

驱动系统正式 ``build_graph().ainvoke()``（与 Gradio 真实流程同代码路径，
[app.py:267 run_graph](file:///d:/robot-data-integrator-latest/src/rdi/frontend/app.py)），
让 LLM 真实解析目标生成数据需求，记录 SENSOR_DATA 在完整系统流程里的表现。

**这不是测试脚本**（不直接调 Skill），而是驱动系统正式 LangGraph 流程。

用法::

    uv run python scripts/run_e2e_sensor_test.py            # 第一轮：系统自动搜
    uv run python scripts/run_e2e_sensor_test.py --inject-local  # 第二轮：本地 CSV 注入
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from rdi.graph.builder import build_graph

GOAL = "获取 Franka Panda 机器人的末端力/力矩传感器时序数据，用于接触力分析与抓取接触检测"
LOCAL_FT_CSV = Path("data/sensor_real/ft_end_effector_prepared.csv")


def _plain(value: Any) -> Any:
    """递归转可 JSON 序列化（参考 app.py to_plain）。"""
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(v) for v in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _print_section(title: str, data: Any) -> None:
    print(f"\n{'=' * 20} {title} {'=' * 20}")
    if not data:
        print("  (空)")
        return
    if isinstance(data, list | dict):
        print(json.dumps(_plain(data), ensure_ascii=False, indent=2, default=str)[:4000])
    else:
        print(data)


def _req_type_value(req: Any) -> str:
    rt = getattr(req, "req_type", None)
    return getattr(rt, "value", str(rt))


async def run_first_round() -> None:
    """第一轮:系统自动搜(真实 LLM + Adapter 联网)。"""
    print(f"[第一轮·系统自动搜] 目标: {GOAL}")
    graph = build_graph()
    state: dict[str, Any] = {
        "user_goal": GOAL,
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
        "review_decision": "satisfied",
        "user_feedback": [],
    }
    result = await graph.ainvoke(
        state, config={"configurable": {"thread_id": "e2e-sensor-test"}}
    )

    reqs = result.get("data_requirements", [])
    print(f"\n>>> LLM 生成 {len(reqs)} 条数据需求:")
    for req in reqs:
        print(
            f"  - {getattr(req, 'req_id', '?')}: type={_req_type_value(req)} "
            f"desc={getattr(req, 'description', '')} fmt={getattr(req, 'expected_format', '')}"
        )

    has_sensor = any(_req_type_value(r) == "sensor_data" for r in reqs)
    print(f"\n>>> 含 SENSOR_DATA 需求: {has_sensor}")

    # 重点看 SENSOR_DATA 的检索结果
    rrs = result.get("retrieval_results", {})
    print(f"\n>>> 检索结果 {len(rrs)} 条:")
    for rid, rr in rrs.items():
        status = getattr(rr, "status", "?")
        data = getattr(rr, "data", None)
        source = getattr(data, "source", None) if data else None
        src_val = getattr(source, "value", source) if source else None
        err = getattr(rr, "error_message", "") or ""
        print(f"  - {rid}: status={status} source={src_val} err={err}")

    _print_section("retrieval_results(完整)", rrs)
    _print_section("validation_issues", result.get("validation_issues", []))
    _print_section("errors", result.get("errors", []))

    pkg = result.get("experiment_package")
    if pkg:
        _print_section(
            "experiment_package(摘要)",
            {
                "files_count": len(getattr(pkg, "files", [])),
                "missing_count": len(getattr(pkg, "missing_items", [])),
                "quality_report": getattr(pkg, "quality_report", None),
                "output_dir": getattr(pkg, "output_dir", None),
            },
        )
    else:
        print("\n>>> 未生成 experiment_package")

    _print_section("provenance(尾)", result.get("provenance", [])[-10:])


async def run_second_round() -> None:
    """第二轮:本地 CSV 注入(绕过 retrieve_data,跑 parse_convert→validate→assemble)。"""
    from rdi.graph.nodes.parse_convert import node_parse_convert
    from rdi.graph.nodes.validate import node_validate
    from rdi.graph.nodes.assemble import node_assemble
    from rdi.models import DataReq, DataReqType, DataSource, GoalSpec, Priority, RetrievalResult, RawData

    print(f"[第二轮·本地CSV注入] 目标: {GOAL}")
    print(f"本地数据: {LOCAL_FT_CSV}")

    # 1) 先跑 parse_goal 拿 requirements(真实 LLM)
    graph = build_graph()
    state: dict[str, Any] = {
        "user_goal": GOAL,
        "iteration_count": 0,
        "provenance": [],
        "errors": [],
        "review_decision": "satisfied",
        "user_feedback": [],
    }
    # 只跑 parse_goal:用图但只到 retrieve_data 前。简单起见直接调 node_parse_goal
    from rdi.graph.nodes.parse_goal import node_parse_goal
    from rdi.graph.state import SystemState

    # node_parse_goal 需要 SystemState;构造最小 state
    pg_result = node_parse_goal(state)
    state.update(pg_result)
    reqs = state.get("data_requirements", [])
    print(f"\n>>> LLM 生成 {len(reqs)} 条需求:")
    for req in reqs:
        print(f"  - {getattr(req, 'req_id', '?')}: type={_req_type_value(req)} desc={getattr(req, 'description', '')}")

    # 找 SENSOR_DATA 需求(若 LLM 没生成,手动构造一个)
    sensor_req = next((r for r in reqs if _req_type_value(r) == "sensor_data"), None)
    if sensor_req is None:
        print("\n>>> LLM 未生成 SENSOR_DATA，手动构造一条")
        sensor_req = DataReq(
            req_id="req_sensor_inject",
            req_type=DataReqType.SENSOR_DATA,
            description="franka force torque sensor time series",
            priority=Priority.REQUIRED,
            keywords=["franka", "force", "torque", "sensor"],
            fallback_sources=[DataSource.GITHUB],
            expected_format="csv",
        )
        reqs.append(sensor_req)
        state["data_requirements"] = reqs

    # 2) 构造本地 CSV 的 RetrievalResult 注入
    csv_bytes = LOCAL_FT_CSV.read_bytes()
    raw = RawData(
        source=DataSource.GITHUB,
        item_id="ft_end_effector_local",
        format="csv",
        data=csv_bytes,
        url=str(LOCAL_FT_CSV),
        size_bytes=len(csv_bytes),
    )
    rr = RetrievalResult(
        req_id=sensor_req.req_id,
        status="success",
        data=raw,
        source=DataSource.GITHUB,
        is_fallback=False,
        search_results=[],
        elapsed_seconds=0.0,
    )
    state["retrieval_results"] = {sensor_req.req_id: rr}
    print(f"\n>>> 注入本地 CSV: {len(csv_bytes)} bytes 作为 {sensor_req.req_id}")

    # 3) 跑 parse_convert → validate → assemble
    pc_update = node_parse_convert(state)
    state.update(pc_update)
    _print_section("parse_convert 结果", state.get("parsed_data", {}))

    val_update = node_validate(state)
    state.update(val_update)
    _print_section("validation_issues", state.get("validation_issues", []))

    asm_update = node_assemble(state)
    state.update(asm_update)
    pkg = state.get("experiment_package")
    if pkg:
        _print_section(
            "experiment_package(摘要)",
            {
                "files_count": len(getattr(pkg, "files", [])),
                "missing_count": len(getattr(pkg, "missing_items", [])),
                "quality_report": getattr(pkg, "quality_report", None),
                "output_dir": getattr(pkg, "output_dir", None),
            },
        )
    _print_section("errors", state.get("errors", []))
    _print_section("provenance(尾)", state.get("provenance", [])[-10:])


async def main() -> None:
    parser = argparse.ArgumentParser(description="SENSOR_DATA 端到端测试驱动")
    parser.add_argument("--inject-local", action="store_true", help="第二轮:本地 CSV 注入")
    args = parser.parse_args()
    if args.inject_local:
        await run_second_round()
    else:
        await run_first_round()


if __name__ == "__main__":
    asyncio.run(main())
