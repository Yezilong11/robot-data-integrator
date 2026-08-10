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
    assert "errors" not in out  # 节点不再无条件清空 errors（由 state reducer 累积）


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
    assert "errors" not in out


def test_node_local_file_injection(tmp_path: Path) -> None:
    """local_files 注入：本地文件作为 RetrievalResult 参与解析，provenance 溯源为 local://。"""
    local = tmp_path / "hand.stl"
    local.write_bytes((_SAMPLE_DIR / "hand.stl").read_bytes())
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state: SystemState = {
        "data_requirements": [req],
        "retrieval_results": {},
        "local_files": {"r1": str(local)},
    }

    out = node_parse_convert(state)

    assert "r1" in out["parsed_data"]
    item = out["parsed_data"]["r1"]
    assert isinstance(item, ParsedItem)
    assert item.provenance.source == DataSource.LOCAL
    assert item.provenance.source_url == f"local://{local}"
    assert item.canonical_format == "trimesh.Trimesh"
    assert isinstance(item.data, trimesh.Trimesh)


def test_node_local_file_skips_missing_path(tmp_path: Path) -> None:
    """local_files 指向不存在的文件时静默跳过：不产生 parsed_data，也不误报缺失。"""
    missing = tmp_path / "no_such.stl"
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state: SystemState = {
        "data_requirements": [req],
        "retrieval_results": {},
        "local_files": {"r1": str(missing)},
    }

    out = node_parse_convert(state)

    assert "r1" not in out["parsed_data"]
    assert out["missing_items"] == []  # 无检索结果时不制造缺失项（由 retrieve_data 负责）


def test_node_does_not_reset_accumulated_errors() -> None:
    """节点返回值不含 errors 键：不无条件清空 errors，错误累积交给 state reducer。"""
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    data = (_SAMPLE_DIR / "hand.stl").read_bytes()
    state = _make_state(
        [req],
        {"r1": RetrievalResult(req_id="r1", data=_mesh_raw(data), status="success")},
    )

    out = node_parse_convert(state)

    assert "errors" not in out


def test_node_passes_urdf_mesh_paths_to_sim_config() -> None:
    """sim_config 处理时，节点应把 URDF/Mesh 输出路径传给 SimConfigSkill。"""
    sample_base = Path(__file__).parent.parent / "skills" / "sample_data"
    mesh_data = (sample_base / "mesh" / "hand.stl").read_bytes()
    urdf_data = (sample_base / "urdf" / "allegro_hand_r.urdf").read_bytes()
    isaac_data = b"isaac: {objects: [{name: box, type: box, pos: [0,0,0], size: [1,1,1]}]}"

    urdf_req = DataReq(
        req_id="r_urdf",
        req_type=DataReqType.ROBOT_URDF,
        description="robot",
        priority=Priority.REQUIRED,
    )
    mesh_req = DataReq(
        req_id="r_mesh",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    sim_req = DataReq(
        req_id="r_sim",
        req_type=DataReqType.SIM_CONFIG,
        description="sim",
        priority=Priority.REQUIRED,
    )

    state: SystemState = {
        "data_requirements": [urdf_req, mesh_req, sim_req],
        "retrieval_results": {
            "r_urdf": RetrievalResult(
                req_id="r_urdf",
                data=RawData(
                    source=DataSource.GITHUB,
                    item_id="panda",
                    format="urdf",
                    data=urdf_data,
                    url="https://example.com/panda.urdf",
                ),
                status="success",
            ),
            "r_mesh": RetrievalResult(
                req_id="r_mesh",
                data=RawData(
                    source=DataSource.GITHUB,
                    item_id="hand",
                    format="stl",
                    data=mesh_data,
                    url="https://example.com/hand.stl",
                ),
                status="success",
            ),
            "r_sim": RetrievalResult(
                req_id="r_sim",
                data=RawData(
                    source=DataSource.GITHUB,
                    item_id="scene",
                    format="yaml",
                    data=isaac_data,
                    url="https://example.com/scene",
                ),
                status="success",
            ),
        },
    }

    out = node_parse_convert(state)

    assert "r_urdf" in out["parsed_data"]
    assert "r_mesh" in out["parsed_data"]
    assert "r_sim" in out["parsed_data"]
    sim_item = out["parsed_data"]["r_sim"]
    assert isinstance(sim_item, ParsedItem)
    assert sim_item.req_type == DataReqType.SIM_CONFIG
    assert sim_item.canonical_format == "mjcf"
    assert isinstance(sim_item.data, bytes)
    assert sim_item.output_path == "sim_config/scene.xml"
    assert b"<mujoco" in sim_item.data
    assert b"robots/panda.urdf" in sim_item.data
    assert b"objects/hand.stl" in sim_item.data
    assert b'<mesh file="objects/hand.stl" name="hand"/>' in sim_item.data
