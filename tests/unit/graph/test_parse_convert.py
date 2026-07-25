# tests/unit/graph/test_parse_convert.py
"""parse_convert 节点单元测试（同步）。

验证节点用 SkillRegistry 替换占位逻辑后的真实分发行为：
- Mesh Skill 成功 → ParsedItem（canonical_format="trimesh.Trimesh"）
- 处理失败 → MissingItem
- 未注册 req_type (PAPER) → MissingItem
- provenance 日志非空，含 Skill 名与处理结果
- data_requirements 缺失时由原始格式兜底推断 req_type
"""

from datetime import datetime
from pathlib import Path

import trimesh

from rdi.graph.nodes.parse_convert import node_parse_convert
from rdi.graph.state import SystemState
from rdi.models import DataReqType, DataSource, Priority
from rdi.models.goal import DataReq
from rdi.models.parsed import MissingItem, ParsedItem
from rdi.models.retrieval import RawData, RetrievalResult

_SAMPLE_DIR = Path(__file__).parent.parent / "skills" / "sample_data" / "mesh"
_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _mesh_raw(data: bytes) -> RawData:
    return RawData(
        source=DataSource.GITHUB,
        item_id="hand",
        format="stl",
        data=data,
        url="https://example.com/hand",
        retrieved_at=_FIXED_TIME,
    )


def _make_state(
    reqs: list[DataReq],
    results: dict[str, RetrievalResult],
) -> SystemState:
    state: SystemState = {
        "data_requirements": reqs,
        "retrieval_results": results,
    }
    return state


def test_node_dispatches_mesh_skill() -> None:
    data = (_SAMPLE_DIR / "hand.stl").read_bytes()
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state = _make_state(
        [req],
        {"r1": RetrievalResult(req_id="r1", data=_mesh_raw(data), status="success")},
    )

    out = node_parse_convert(state)

    assert "r1" in out["parsed_data"]
    item = out["parsed_data"]["r1"]
    assert isinstance(item, ParsedItem)
    assert item.canonical_format == "trimesh.Trimesh"
    assert isinstance(item.data, trimesh.Trimesh)
    assert out["provenance"]  # non-empty log
    assert any("mesh" in line and "成功" in line for line in out["provenance"])
    assert out["errors"] == []


def test_node_missing_item_on_failure() -> None:
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state = _make_state(
        [req],
        {"r1": RetrievalResult(req_id="r1", data=_mesh_raw(b"not a mesh"), status="success")},
    )

    out = node_parse_convert(state)

    assert "r1" not in out["parsed_data"]
    assert out["missing_items"]
    assert isinstance(out["missing_items"][0], MissingItem)
    assert any("缺失" in line for line in out["provenance"])


def test_node_skips_unregistered_req_type() -> None:
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.PAPER,
        description="paper",
        priority=Priority.REQUIRED,
    )
    raw = RawData(
        source=DataSource.ARXIV,
        item_id="paper1",
        format="pdf",
        data=b"paper bytes",
    )
    state = _make_state(
        [req],
        {"r1": RetrievalResult(req_id="r1", data=raw, status="success")},
    )

    out = node_parse_convert(state)

    assert "r1" not in out["parsed_data"]
    assert out["missing_items"]
    assert out["missing_items"][0].req_id == "r1"


def test_node_infers_req_type_without_data_requirements() -> None:
    """data_requirements 缺失：由 result.data.format 兜底推断 req_type=MESH。"""
    data = (_SAMPLE_DIR / "hand.stl").read_bytes()
    # 不传 data_requirements，节点应从 stl 格式推断 MESH
    state: SystemState = {
        "retrieval_results": {
            "r1": RetrievalResult(req_id="r1", data=_mesh_raw(data), status="success"),
        },
    }

    out = node_parse_convert(state)

    assert "r1" in out["parsed_data"]
    item = out["parsed_data"]["r1"]
    assert isinstance(item, ParsedItem)
    assert item.req_type == DataReqType.MESH
    assert isinstance(item.data, trimesh.Trimesh)


def test_node_empty_state_returns_empty_dicts() -> None:
    state: SystemState = {}
    out = node_parse_convert(state)
    assert out["parsed_data"] == {}
    assert out["missing_items"] == []
    assert out["errors"] == []
