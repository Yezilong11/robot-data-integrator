"""第二次联调集成测试：mock 上游节点并跑通 validate 节点。

验证在「Franka + YCB + MuJoCo」样例数据流下，validate 节点能正确输出
validation_issues（含可加载性成功与失败记录）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from rdi.graph.nodes.validate import node_validate
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry, Severity
from rdi.models.goal import DataReq

if TYPE_CHECKING:
    from rdi.graph.state import SystemState
    from rdi.models.parsed import MissingItem

_SAMPLE_DIR = Path(__file__).parent.parent / "unit" / "skills" / "sample_data"
_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _provenance(fmt: str) -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.FRANKA,
        source_url="https://example.com",
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


def _item(
    req_id: str,
    req_type: DataReqType,
    data: object,
    fmt: str,
    output_path: str,
) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=req_type,
        name=req_id,
        canonical_format=fmt,
        output_path=output_path,
        data=data,
        provenance=_provenance(fmt),
    )


def _mock_parse_goal(state: SystemState) -> dict[str, Any]:
    """模拟 parse_goal 节点输出数据需求清单。"""
    return {
        "data_requirements": [
            DataReq(
                req_id="req_000",
                req_type=DataReqType.ROBOT_URDF,
                description="Franka Panda URDF",
                priority=Priority.REQUIRED,
                fallback_sources=[DataSource.FRANKA],
            ),
            DataReq(
                req_id="req_001",
                req_type=DataReqType.MESH,
                description="YCB banana mesh",
                priority=Priority.REQUIRED,
                fallback_sources=[DataSource.YCB],
            ),
            DataReq(
                req_id="req_002",
                req_type=DataReqType.SIM_CONFIG,
                description="MuJoCo simulation scene",
                priority=Priority.REQUIRED,
                fallback_sources=[DataSource.MUJOCO],
            ),
            DataReq(
                req_id="req_003",
                req_type=DataReqType.GRASP,
                description="Grasp poses",
                priority=Priority.RECOMMENDED,
            ),
        ],
        "parsed_goal": None,
        "provenance": ["parse_goal: mocked"],
    }


def _mock_retrieve_data(state: SystemState) -> dict[str, Any]:
    """模拟 retrieve_data 节点输出检索结果（此处仅用于 provenance，validate 不读取）。"""
    return {"retrieval_results": {}, "provenance": ["retrieve_data: mocked"]}


def _mock_parse_convert(state: SystemState) -> dict[str, Any]:
    """模拟 parse_convert 节点输出 parsed_data 与 missing_items。"""
    parsed_data: dict[str, ParsedItem] = {
        "req_000": _item(
            "req_000",
            DataReqType.ROBOT_URDF,
            (_SAMPLE_DIR / "urdf" / "allegro_hand_r.urdf").read_bytes(),
            fmt="urdf",
            output_path="robots/robot.urdf",
        ),
        "req_001": _item(
            "req_001",
            DataReqType.MESH,
            (_SAMPLE_DIR / "mesh" / "hand.stl").read_bytes(),
            fmt="stl",
            output_path="objects/object.stl",
        ),
        "req_002": _item(
            "req_002",
            DataReqType.SIM_CONFIG,
            (_SAMPLE_DIR / "sim" / "sample_mujoco.xml").read_bytes(),
            fmt="xml",
            output_path="sim_config/scene.xml",
        ),
        "req_003": _item(
            "req_003",
            DataReqType.GRASP,
            {"translations": np.zeros((5, 3)), "rotations": np.zeros((5, 3, 3))},
            fmt="CanonicalGrasp",
            output_path="grasps/grasp.npz",
        ),
    }
    missing_items: list[MissingItem] = []
    return {
        "parsed_data": parsed_data,
        "missing_items": missing_items,
        "provenance": ["parse_convert: mocked"],
    }


@pytest.fixture
def mocked_upstream_nodes(monkeypatch: pytest.MonkeyPatch) -> None:
    """将上游三个节点替换为 mock 实现， isolate 真实 LLM / 网络 / Skill。"""
    monkeypatch.setattr("rdi.graph.nodes.parse_goal.node_parse_goal", _mock_parse_goal)
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.node_retrieve_data", _mock_retrieve_data)
    monkeypatch.setattr("rdi.graph.nodes.parse_convert.node_parse_convert", _mock_parse_convert)


def test_second_integration_validate_happy_path(mocked_upstream_nodes: None) -> None:
    """全为合法数据时，validate 不应产生 ERROR 级可加载性问题。"""
    state: SystemState = {"user_goal": "Franka Panda grasps YCB banana in MuJoCo simulation"}

    # 模拟上游链路逐个节点执行
    state.update(_mock_parse_goal(state))
    state.update(_mock_retrieve_data(state))
    state.update(_mock_parse_convert(state))

    out = node_validate(state)
    issues = out["validation_issues"]

    loadability_errors = [
        i
        for i in issues
        if i.severity == Severity.ERROR
        and any(
            k in i.message
            for k in (
                "URDF 无法解析",
                "Mesh 无法加载",
                "面片",
                "XML/MJCF 无法解析",
                "Python 仿真配置语法错误",
                "Grasp 数据缺少必要字段",
            )
        )
    ]
    assert loadability_errors == []

    # 确认 provenance 中统计了检查动作
    assert any("validate:" in line for line in out["provenance"])


def test_second_integration_validate_detects_bad_data(
    mocked_upstream_nodes: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    """当 URDF / mesh / sim_config / grasp 中存在非法数据时，validate 记录 ERROR。"""
    bad_parsed_data: dict[str, ParsedItem] = {
        "req_000": _item(
            "req_000",
            DataReqType.ROBOT_URDF,
            b"not a urdf",
            fmt="urdf",
            output_path="robots/robot.urdf",
        ),
        "req_001": _item(
            "req_001",
            DataReqType.MESH,
            b"not a mesh",
            fmt="stl",
            output_path="objects/object.stl",
        ),
        "req_002": _item(
            "req_002",
            DataReqType.SIM_CONFIG,
            b"<not>xml",
            fmt="xml",
            output_path="sim_config/scene.xml",
        ),
        "req_003": _item(
            "req_003",
            DataReqType.GRASP,
            {"score": 0.5},
            fmt="CanonicalGrasp",
            output_path="grasps/grasp.npz",
        ),
    }

    def bad_parse_convert(state: SystemState) -> dict[str, Any]:
        return {
            "parsed_data": bad_parsed_data,
            "missing_items": [],
            "provenance": ["parse_convert: mocked bad"],
        }

    monkeypatch.setattr("rdi.graph.nodes.parse_convert.node_parse_convert", bad_parse_convert)

    state: SystemState = {"user_goal": "Franka Panda grasps YCB banana in MuJoCo simulation"}
    state.update(_mock_parse_goal(state))
    state.update(_mock_retrieve_data(state))
    state.update(bad_parse_convert(state))

    out = node_validate(state)
    issues = out["validation_issues"]

    messages = {i.message for i in issues if i.severity == Severity.ERROR}
    assert any("URDF 无法解析" in m for m in messages)
    assert any("Mesh 无法加载" in m or "Mesh 不包含任何面片" in m for m in messages)
    assert any("XML/MJCF 无法解析" in m for m in messages)
    assert any("Grasp 数据缺少必要字段" in m for m in messages)
