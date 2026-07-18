# src/rdi/graph/builder.py
"""LangGraph 状态图构建入口。

将所有节点注册到 StateGraph 中，定义边的路由逻辑，
编译生成可执行的应用实例。
"""

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph

from rdi.graph.edges import route_after_review, route_after_validate
from rdi.graph.nodes import (
    node_assemble,
    node_human_review,
    node_parse_convert,
    node_parse_goal,
    node_retrieve_data,
    node_retrieve_single,
    node_validate,
)
from rdi.graph.state import SystemState


def build_graph() -> CompiledStateGraph[SystemState, None, SystemState, SystemState]:
    """构建并编译 LangGraph 状态图。

    工作流节点：
        1. parse_goal       — 解析用户目标和 PDF，生成数据需求清单
        2. retrieve_data    — 并行查找所有数据需求（Send fan-out）
        3. retrieve_single  — 单个数据需求查找（被 Send 调用）
        4. parse_and_convert — 解析并标准化六类异构数据
        5. validate         — 质量校验，发现问题则回退重试
        6. assemble_package — 整合打包，生成 Manifest
        7. human_review     — 用户审查，决定通过或修正

    条件路由：
        - validate → 校验通过 → assemble_package
        - validate → 校验不通过 → retrieve_data（重试，最多3次）
        - human_review → 用户满意 → END
        - human_review → 用户不满意 → retrieve_data（带反馈）

    Returns:
        编译后的可执行图实例，调用 .invoke(state) 运行。
    """
    # ─── 初始化状态图 ───
    graph = StateGraph(SystemState)

    # ─── 注册所有节点 ───
    graph.add_node("parse_goal", node_parse_goal)
    graph.add_node("retrieve_data", node_retrieve_data)
    graph.add_node("retrieve_single", node_retrieve_single)
    graph.add_node("parse_and_convert", node_parse_convert)
    graph.add_node("validate", node_validate)
    graph.add_node("assemble_package", node_assemble)
    graph.add_node("human_review", node_human_review)

    # ─── 设置入口点 ───
    graph.set_entry_point("parse_goal")

    # ─── 主线边 ───
    graph.add_edge("parse_goal", "retrieve_data")
    graph.add_edge("retrieve_single", "parse_and_convert")
    graph.add_edge("parse_and_convert", "validate")

    # ─── 条件回退：校验不通过则回退重试 ───
    graph.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "retry": "retrieve_data",
            "pass": "assemble_package",
        },
    )

    # ─── 整合打包 ───
    graph.add_edge("assemble_package", "human_review")

    # ─── 用户审查 ───
    graph.add_conditional_edges(
        "human_review",
        route_after_review,
        {
            "satisfied": END,
            "revise": "retrieve_data",
        },
    )

    # ─── 编译并启用 checkpoint ───
    checkpointer = MemorySaver()
    app = graph.compile(checkpointer=checkpointer)

    return app
