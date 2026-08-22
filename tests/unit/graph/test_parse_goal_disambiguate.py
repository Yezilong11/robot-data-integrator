# tests/unit/graph/test_parse_goal_disambiguate.py
"""P1-B：DATASET→GRASP 单向消歧与 GRASP 强词补全测试。"""

from rdi.graph.nodes.parse_goal import _normalize_datareq
from rdi.models import DataReq, DataReqType, Priority


def _req(description: str, req_type: DataReqType = DataReqType.DATASET) -> DataReq:
    return DataReq(
        req_id="req_000",
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
    )


def test_dataset_with_grasp_label_rewrites_to_grasp() -> None:
    """单向消歧：DATASET + "抓取标签" → GRASP（ss_graspnet_004 类）。"""
    out = _normalize_datareq(_req("香蕉抓取标签数据集 ss_graspnet_004"))
    assert out.req_type == DataReqType.GRASP


def test_dataset_with_grasp_annotation_rewrites_to_grasp() -> None:
    """单向消歧：DATASET + "抓取标注" → GRASP。"""
    out = _normalize_datareq(_req("苹果的抓取标注数据集"))
    assert out.req_type == DataReqType.GRASP


def test_dataset_with_english_grasp_annotation_rewrites_to_grasp() -> None:
    """单向消歧：DATASET + "grasp annotation" → GRASP。"""
    out = _normalize_datareq(_req("banana grasp annotation dataset"))
    assert out.req_type == DataReqType.GRASP


def test_dataset_without_content_word_stays_dataset() -> None:
    """"机器人抓取数据集"无内容强词，仍为 DATASET，不受消歧影响。"""
    out = _normalize_datareq(_req("机器人抓取数据集"))
    assert out.req_type == DataReqType.DATASET


def test_unknown_with_grasp_planning_hits_grasp_strong_word() -> None:
    """强词补全：非 DATASET 类型含"抓取规划"命中 GRASP 强词。"""
    out = _normalize_datareq(_req("多指手抓取规划数据", req_type=DataReqType.UNKNOWN))
    assert out.req_type == DataReqType.GRASP