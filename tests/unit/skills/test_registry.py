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
from rdi.models.retrieval import RawData, RawReference, RetrievalResult
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
        assert outcome.reason == "检索失败[error]: timeout"

    def test_error_status_reason_keeps_structured_info(self) -> None:
        """status=error 且 error_message 非空时，reason 保留结构化失败信息。"""
        raw = _make_raw("stl", b"x")
        result = RetrievalResult(
            req_id="req_001",
            data=raw,
            status="error",
            error_message="github:rate_limit",
        )
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "检索失败" in outcome.reason
        assert "github:rate_limit" in outcome.reason

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

    # ─── P0-3: URDF/MJCF 原始字节与资产透传 ───

    def test_urdf_passthrough_raw_bytes_and_assets(self) -> None:
        """ROBOT_URDF 类型把 raw_bytes 与 assets 透传到 ParsedItem。"""
        urdf = (
            b'<robot name="r"><link name="base"><visual><geometry>'
            b'<mesh filename="meshes/base.stl"/>'
            b"</geometry></visual></link></robot>"
        )
        raw = _make_raw("urdf", urdf, item_id="panda", source=DataSource.FRANKA)
        raw.assets = {"meshes/base.stl": b"stl-data"}
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.ROBOT_URDF)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.raw_bytes == urdf
        assert outcome.assets == {"meshes/base.stl": b"stl-data"}

    def test_non_urdf_types_do_not_passthrough(self) -> None:
        """MESH 等其他类型不透传 raw_bytes/assets（保持默认 None/空 dict）。"""
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        raw.assets = {"tex.png": b"png-data"}  # 即便 RawData 有 assets 也不透传
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.raw_bytes is None
        assert outcome.assets == {}

    # ─── P0-4: RawReference 透传 ───

    def test_reference_passthrough_from_raw_data(self) -> None:
        """P0-4：RawData.reference 无条件透传到 ParsedItem.reference。"""
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        raw.reference = RawReference(
            url="https://example.com/big.tar",
            file_size=12345,
            download_hint="https://mirror.example.com/big.tar",
            reason="过大",
        )
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.reference is not None
        assert outcome.reference.url == "https://example.com/big.tar"
        assert outcome.reference.file_size == 12345
        assert outcome.reference.reason == "过大"

    def test_reference_none_when_raw_has_none(self) -> None:
        """P0-4：RawData.reference 为 None 时 ParsedItem.reference 保持 None。"""
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.reference is None

    # ─── P1-2: is_fallback 透传 ───

    def test_is_fallback_passthrough_true(self) -> None:
        """RetrievalResult.is_fallback=True（非首选源成功）→ ParsedItem.is_fallback=True。"""
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        result = RetrievalResult(
            req_id="req_001", data=raw, status="success", is_fallback=True
        )
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.is_fallback is True

    def test_is_fallback_default_false(self) -> None:
        """RetrievalResult 未设置 is_fallback（默认 False，首选源成功）→ ParsedItem.is_fallback=False。"""
        data = (_SAMPLE_DIR / "hand.stl").read_bytes()
        raw = _make_raw("stl", data, item_id="hand")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.is_fallback is False
