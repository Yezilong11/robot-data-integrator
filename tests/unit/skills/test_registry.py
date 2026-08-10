# tests/unit/skills/test_registry.py
"""SkillRegistry 单元测试（同步）。

覆盖 spec「SkillRegistry — 按 req_type 分发」需求的全部场景：
- 已注册类型分发（全部 Skill 单例，二次调用返回同一实例）
- 端到端装配 ParsedItem（MeshSkill + hand.stl，provenance 从 RawData 继承）
- 无原始数据 / 查找失败 → MissingItem
- Skill 处理失败 → MissingItem（errors 拼接为 reason）
"""

from datetime import datetime
from pathlib import Path

import trimesh

from rdi.models.common import DataReqType, DataSource
from rdi.models.goal import DataReq, Priority
from rdi.models.parsed import MissingItem, ParsedItem
from rdi.models.retrieval import RawData, RetrievalResult
from rdi.skills import (
    CodeSkill,
    DatasetSkill,
    GraspSkill,
    MeshSkill,
    PolicyInterfaceSkill,
    SensorDataSkill,
    SimConfigSkill,
    SkillRegistry,
    URDFSkill,
)

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "mesh"
_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)


def _make_req(req_type: DataReqType, req_id: str = "req_001") -> DataReq:
    return DataReq(
        req_id=req_id,
        req_type=req_type,
        description="test",
        priority=Priority.REQUIRED,
    )


def _make_raw(
    fmt: str,
    data: bytes,
    item_id: str = "hand",
    source: DataSource = DataSource.GITHUB,
) -> RawData:
    return RawData(
        source=source,
        item_id=item_id,
        format=fmt,
        data=data,
        url="https://example.com/hand",
        retrieved_at=_FIXED_TIME,
    )


# ─── Scenario: 已注册类型分发 ───


class TestGetSkill:
    def test_get_skill_returns_correct_singleton(self) -> None:
        reg = SkillRegistry()
        assert isinstance(reg.get_skill(DataReqType.ROBOT_URDF), URDFSkill)
        assert isinstance(reg.get_skill(DataReqType.MESH), MeshSkill)
        assert isinstance(reg.get_skill(DataReqType.GRASP), GraspSkill)
        assert isinstance(reg.get_skill(DataReqType.SIM_CONFIG), SimConfigSkill)
        assert isinstance(reg.get_skill(DataReqType.POLICY_MODEL), PolicyInterfaceSkill)
        assert isinstance(reg.get_skill(DataReqType.SENSOR_DATA), SensorDataSkill)
        assert isinstance(reg.get_skill(DataReqType.CODE), CodeSkill)
        assert isinstance(reg.get_skill(DataReqType.DATASET), DatasetSkill)

    def test_get_skill_returns_same_instance(self) -> None:
        reg = SkillRegistry()
        for req_type in (
            DataReqType.ROBOT_URDF,
            DataReqType.MESH,
            DataReqType.GRASP,
            DataReqType.SIM_CONFIG,
            DataReqType.POLICY_MODEL,
            DataReqType.SENSOR_DATA,
            DataReqType.CODE,
            DataReqType.DATASET,
        ):
            assert reg.get_skill(req_type) is reg.get_skill(req_type)

    def test_get_skill_code_and_dataset_registered(self) -> None:
        reg = SkillRegistry()
        assert isinstance(reg.get_skill(DataReqType.CODE), CodeSkill)
        assert isinstance(reg.get_skill(DataReqType.DATASET), DatasetSkill)


# ─── Scenario: 端到端装配 ParsedItem / 失败降级 ───


class TestProcessRetrievalResult:
    def test_success_builds_parsed_item(self) -> None:
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.req_id == "req_001"
        assert outcome.req_type == DataReqType.MESH
        assert outcome.name == "hand"
        assert outcome.canonical_format == "trimesh.Trimesh"
        assert isinstance(outcome.data, trimesh.Trimesh)
        assert outcome.provenance.source == DataSource.GITHUB
        assert outcome.provenance.source_url == "https://example.com/hand"
        assert outcome.provenance.original_format == "stl"
        assert outcome.provenance.retrieved_at == _FIXED_TIME

    def test_missing_on_no_data(self) -> None:
        result = RetrievalResult(req_id="req_001", data=None, status="missing")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert outcome.req_id == "req_001"
        assert outcome.req_type == DataReqType.MESH
        assert outcome.reason  # non-empty
        assert outcome.fallback_sources == []

    def test_missing_on_non_success_status(self) -> None:
        raw = _make_raw("stl", b"x")
        result = RetrievalResult(
            req_id="req_001", data=raw, status="error", error_message="timeout"
        )
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert outcome.reason == "timeout"

    def test_missing_on_code_skill_failure(self) -> None:
        raw = _make_raw("zip", b"code bytes")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.CODE)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert outcome.reason

    def test_missing_on_skill_failure(self) -> None:
        raw = _make_raw("stl", b"not a mesh")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert outcome.reason  # skill errors propagated as reason
