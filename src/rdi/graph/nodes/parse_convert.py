# src/rdi/graph/nodes/parse_convert.py
"""数据解析与标准化节点。

对获取到的原始数据调用对应 Skill 进行解析和标准化。
"""

from datetime import datetime
from typing import Any

from rdi.graph.state import SystemState
from rdi.models import DataReqType, DataSource, ParsedItem, ProvenanceEntry


def node_parse_convert(state: SystemState) -> dict[str, Any]:
    """数据解析与标准化节点。

    当前为空骨架实现，返回占位解析结果。
    后续由人员 D（机器人数据工程师）接入 6 类 Skill。

    Returns:
        更新 state 的字段：parsed_data, provenance
    """
    retrieval_results = state.get("retrieval_results", {})
    parsed_data: dict[str, ParsedItem] = {}

    for req_id, result in retrieval_results.items():
        if result.status == "success" and result.data:
            # 占位：构造一个 ParsedItem
            parsed_data[req_id] = ParsedItem(
                req_id=req_id,
                req_type=DataReqType.DATASET,  # 占位
                name=f"parsed_{req_id}",
                canonical_format="placeholder",
                output_path=f"outputs/{req_id}.bin",
                data=b"placeholder parsed data",
                provenance=ProvenanceEntry(
                    source=DataSource.GITHUB,  # 占位
                    source_url=result.data.url or "https://example.com",
                    retrieved_at=datetime.now(),
                    original_format="unknown",
                    transformations=["placeholder_parse"],
                ),
                completeness_pct=100.0,
                confidence_score=1.0,
                is_inferred=False,
            )

    return {
        "parsed_data": parsed_data,
        "provenance": [
            f"[{datetime.now().isoformat()}] parse_convert: "
            f"解析 {len(parsed_data)} 个数据项 (骨架实现)"
        ],
    }
