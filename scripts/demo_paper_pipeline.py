"""可复现示例：从 arXiv 检索一篇 robot grasping 论文并打包。

此脚本直接调用 LangGraph 工作流，无需启动 Gradio 前端，
用于验证论文类数据需求能完整走通 parse → retrieve → parse_convert →
validate → assemble 全链路，最终产出非空数据包。
"""

import asyncio
import json
from pathlib import Path
from typing import TYPE_CHECKING

from rdi.graph.builder import build_graph

if TYPE_CHECKING:
    from rdi.graph.state import SystemState


async def main() -> None:
    goal = "搜索关于 robot grasping 的 arXiv 论文，获取 PDF 并解析文本"
    graph = build_graph()

    state: SystemState = {
        "user_goal": goal,
        "iteration_count": 0,
        "review_decision": "satisfied",
        "user_feedback": [],
    }

    final_state = await graph.ainvoke(state)
    package = final_state.get("experiment_package")

    if package is None:
        print("未生成数据包")
        return

    print(f"数据包 ID: {package.package_info.get('package_id')}")
    print(f"输出目录: {package.output_dir}")
    print(f"文件数: {len(package.files)}")
    print(f"缺失项: {len(package.missing_items)}")
    print(
        f"质量报告: {package.quality_report.fulfilled}/{package.quality_report.total_requirements} 需求满足"
    )

    if package.files:
        print("\n文件列表:")
        for f in package.files:
            print(f"  - {f.path} ({f.format}, confidence={f.confidence})")
        manifest_path = Path(package.output_dir) / "manifest.json"
        print(f"\nmanifest.json: {manifest_path}")
        print(json.dumps(package.model_dump(mode="json"), ensure_ascii=False, indent=2)[:1000])
    else:
        print("\n缺失项详情:")
        for m in package.missing_items:
            print(f"  - {m.req_id}: {m.reason}")


if __name__ == "__main__":
    asyncio.run(main())
