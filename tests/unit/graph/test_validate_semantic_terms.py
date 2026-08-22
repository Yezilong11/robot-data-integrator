"""semantic_terms 语义约束词校验单元测试（阶段一：语义校验补牙齿）。

覆盖：LLM 提炼的 semantic_terms 参与需求-内容语义匹配（DATASET 等类型启用）、
semantic_terms 为空时 fail-open（行为与现状一致）、空串跳过与命中不误报。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from rdi.graph.nodes.validate import _extract_semantic_terms, _semantic_mismatch
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry
from rdi.models.goal import DataReq

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance(fmt: str = "bin", url: str = "https://example.com/asset/a.bin") -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.ZENODO,
        source_url=url,
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


def _item(
    req_id: str,
    req_type: DataReqType,
    data: object,
    fmt: str = "bin",
    name: str | None = None,
    url: str = "https://example.com/asset/a.bin",
) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=name or req_id,
        canonical_format=fmt,
        output_path="files/out.bin",
        data=data,
        provenance=_provenance(fmt, url),
    )


def _req(
    req_id: str,
    req_type: DataReqType,
    description: str = "",
    semantic_terms: list[str] | None = None,
) -> DataReq:
    return DataReq(
        req_id=req_id,
        req_type=req_type,
        description=description,
        priority=Priority.REQUIRED,
        semantic_terms=semantic_terms or [],
    )


def test_semantic_terms_mismatch_dataset_eclipse() -> None:
    """DATASET 需求语义约束词（robot manipulation / action labels）对全为英日食内容文本零重叠。"""
    req = _req(
        "r1",
        DataReqType.DATASET,
        description="robot manipulation dataset with action labels",
        semantic_terms=["robot", "manipulation", "action labels"],
    )
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "2024-04-08 Total Solar Eclipse", "file_tree": ["eclipse.zip"]},
        fmt="DatasetSummary",
        name="total_solar_eclipse",
    )
    mismatch = _semantic_mismatch(req, item)
    assert mismatch
    assert "内容与需求语义不符" in mismatch


def test_semantic_terms_empty_no_object_no_keywords_returns_empty() -> None:
    """semantic_terms 为空且无 object_name/keywords → 提取为空，语义校验跳过（fail-open）。"""
    req = _req("r1", DataReqType.DATASET, description="抓取数据集")
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "unrelated", "file_tree": ["labels.zip"]},
        fmt="DatasetSummary",
        name="unrelated_dataset",
    )
    assert _extract_semantic_terms(req) == set()
    assert _semantic_mismatch(req, item) == ""


def test_semantic_terms_match_content_no_mismatch() -> None:
    """语义约束词命中内容（title 含 robot manipulation / action labels）→ 不误报。"""
    req = _req(
        "r1",
        DataReqType.DATASET,
        description="robot manipulation dataset with action labels",
        semantic_terms=["robot manipulation", "action labels"],
    )
    item = _item(
        "r1",
        DataReqType.DATASET,
        {"title": "Robot Manipulation Dataset with Action Labels"},
        fmt="DatasetSummary",
        name="robot_manipulation_dataset",
        url="https://example.com/robot-manipulation/dataset",
    )
    assert _semantic_mismatch(req, item) == ""


def test_semantic_terms_skip_empty_strings() -> None:
    """semantic_terms 中空串/空白项被跳过，其余按原文采用（失败时也可用 null 兜底）。"""
    req = _req(
        "r1",
        DataReqType.POLICY_MODEL,
        description="policy weights",
        semantic_terms=["", "   ", "policy weight", "action labels"],
    )
    assert _extract_semantic_terms(req) == {"policy weight", "action labels"}


@pytest.mark.parametrize(
    "req_type",
    [DataReqType.DATASET, DataReqType.SENSOR_DATA, DataReqType.POLICY_MODEL],
)
def test_new_semantic_types_enabled(req_type: DataReqType) -> None:
    """DATASET / SENSOR_DATA / POLICY_MODEL 均已启用语义匹配：语义约束词零重叠 → 非空。"""
    req = _req("r1", req_type, description="robot manipulation", semantic_terms=["action labels"])
    item = _item(
        "r1",
        req_type,
        {"title": "2024-04-08 Total Solar Eclipse"},
        fmt="DatasetSummary",
        name="eclipse_data",
    )
    assert _semantic_mismatch(req, item)