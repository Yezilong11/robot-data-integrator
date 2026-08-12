# tests/unit/skills/test_registry.py
"""SkillRegistry 单元测试（同步）。

覆盖 spec「SkillRegistry — 按 req_type 分发」需求的全部场景：
- 已注册类型分发（全部 Skill 单例，二次调用返回同一实例）
- 端到端装配 ParsedItem（MeshSkill + hand.stl，provenance 从 RawData 继承）
- 无原始数据 / 查找失败 → MissingItem
- Skill 处理失败 → MissingItem（errors 拼接为 reason）
"""

import json
from datetime import datetime
from pathlib import Path

import pytest
import trimesh

from rdi.models.common import DataReqType, DataSource, StandardResult
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
from rdi.skills.registry import _format_mismatch_reason

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

    def test_missing_reason_passthrough_catalog_diagnostics(self) -> None:
        """C2：missing 的 error_message 携带清单外诊断时，MissingItem.reason 原样透出。"""
        result = RetrievalResult(
            req_id="req_001",
            data=None,
            status="missing",
            error_message="ycb: 该源仅收录 20 个已知目标，未收录 'xxx'（有源但未收录）",
        )
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "仅收录" in outcome.reason
        assert "有源但未收录" in outcome.reason

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

    def test_grasp_metadata_missing_item_with_reference_alternative(self) -> None:
        """GRASP 仅返回元数据 JSON → MissingItem：reason 含合成占位说明，reference url 进 alternatives。"""
        payload = json.dumps(
            {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        ).encode("utf-8")
        raw = RawData(
            source=DataSource.GRASPNET,
            item_id="banana",
            format="json",
            data=payload,
            url="https://example.com/graspnet",
            retrieved_at=_FIXED_TIME,
            reference=RawReference(url="https://hf.co/datasets/graspnet-1b", reason="过大"),
        )
        result = RetrievalResult(
            req_id="req_001", data=raw, status="success", source=DataSource.GRASPNET
        )
        req = _make_req(DataReqType.GRASP)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "原始数据缺失，合成占位仅作参考" in outcome.reason
        assert outcome.alternatives, "reference url 应进入 alternatives 供手动获取"
        assert "https://hf.co/datasets/graspnet-1b" in outcome.alternatives[0]

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
        result = RetrievalResult(req_id="req_001", data=raw, status="success", is_fallback=True)
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

    # ─── P1-2: is_fallback 合并（retrieval 层 or skill 层任一 True 即 True） ───

    @staticmethod
    def _assemble_with_fake_skill(
        monkeypatch: pytest.MonkeyPatch,
        *,
        retrieval_fallback: bool,
        skill_fallback: bool,
    ) -> ParsedItem:
        """用返回指定 is_fallback 的假 Skill 装配 ParsedItem。"""
        raw = _make_raw("stl", b"fake bytes", item_id="hand")
        result = RetrievalResult(
            req_id="req_001",
            data=raw,
            status="success",
            is_fallback=retrieval_fallback,
        )
        req = _make_req(DataReqType.MESH)
        skill_result = StandardResult(
            success=True,
            canonical_format="trimesh.Trimesh",
            data="fake",
            is_fallback=skill_fallback,
        )
        fake_skill = type("_FakeSkill", (), {"process": lambda self, data, **kw: skill_result})()
        monkeypatch.setattr(SkillRegistry, "get_skill", lambda self, req_type: fake_skill)

        outcome = SkillRegistry().process_retrieval_result(result, req)
        assert isinstance(outcome, ParsedItem)
        return outcome

    def test_is_fallback_true_when_skill_synthetic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """skill 返回 is_fallback=True（合成占位）而 retrieval 为 False → ParsedItem.is_fallback=True。"""
        outcome = self._assemble_with_fake_skill(
            monkeypatch, retrieval_fallback=False, skill_fallback=True
        )
        assert outcome.is_fallback is True

    def test_is_fallback_true_when_retrieval_fallback(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """retrieval.is_fallback=True 而 skill 正常返回 → ParsedItem.is_fallback=True。"""
        outcome = self._assemble_with_fake_skill(
            monkeypatch, retrieval_fallback=True, skill_fallback=False
        )
        assert outcome.is_fallback is True

    def test_is_fallback_false_when_both_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """retrieval 与 skill 均非 fallback → ParsedItem.is_fallback=False。"""
        outcome = self._assemble_with_fake_skill(
            monkeypatch, retrieval_fallback=False, skill_fallback=False
        )
        assert outcome.is_fallback is False

    # ─── D1: 物理量纲显式化 —— units/coordinate_frame/timestamp_epoch 透传 ───

    def test_units_metadata_passthrough_from_skill(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Skill 结果标注 units/coordinate_frame/timestamp_epoch → ParsedItem 原样透传。"""
        raw = _make_raw("stl", b"fake bytes", item_id="hand")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)
        skill_result = StandardResult(
            success=True,
            canonical_format="trimesh.Trimesh",
            data="fake",
            units="meter",
            coordinate_frame="object_center",
            timestamp_epoch=1720000000.0,
        )
        fake_skill = type("_FakeSkill", (), {"process": lambda self, data, **kw: skill_result})()
        monkeypatch.setattr(SkillRegistry, "get_skill", lambda self, req_type: fake_skill)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.units == "meter"
        assert outcome.coordinate_frame == "object_center"
        assert outcome.timestamp_epoch == 1720000000.0

    def test_grasp_units_coordinate_frame_from_dataset_convention(self) -> None:
        """GRASP（graspnet npz）→ units/coordinate_frame 按 DATASET_CONVENTIONS 透传。"""
        data = (Path(__file__).parent / "sample_data" / "grasp" / "sample_labels.npz").read_bytes()
        raw = RawData(
            source=DataSource.GRASPNET,
            item_id="banana",
            format="npz",
            data=data,
            url="https://example.com/graspnet",
            retrieved_at=_FIXED_TIME,
        )
        result = RetrievalResult(
            req_id="req_001", data=raw, status="success", source=DataSource.GRASPNET
        )
        req = _make_req(DataReqType.GRASP)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.units == "millimeter"  # DATASET_CONVENTIONS["graspnet"]["unit"]
        assert outcome.coordinate_frame == "camera"  # DATASET_CONVENTIONS["graspnet"]["origin"]
        assert outcome.timestamp_epoch is None


# ─── C4: 类型错配检测（需求类型期望的格式 vs 实际返回） ───


class TestFormatMismatchDetection:
    """C4：GRASP 需求拿到 YCB mesh 等错配在装配前被拦截为 MissingItem。"""

    def test_grasp_mesh_mismatch_ycb_degradation(self) -> None:
        """GRASP + YCB obj mesh（标注不可用降级）→ MissingItem，reason 含期望/实际/无标注。"""
        raw = RawData(
            source=DataSource.YCB,
            item_id="002_master_chef_can",
            format="obj",
            data=b"v 0 0 0\nv 1 0 0\n",
            url="https://example.com/ycb/002_master_chef_can",
            retrieved_at=_FIXED_TIME,
            metadata={"grasp_annotation_available": False},
        )
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.GRASP)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "期望" in outcome.reason
        assert "实际返回 obj" in outcome.reason
        assert "类型错配" in outcome.reason
        assert "无真实抓取标注" in outcome.reason

    def test_grasp_stl_mismatch_without_annotation_flag(self) -> None:
        """GRASP + stl 但 metadata 未标无标注 → 仍拦截（不追加补充说明）。"""
        raw = RawData(
            source=DataSource.YCB,
            item_id="002_master_chef_can",
            format="stl",
            data=b"solid x\nendsolid x\n",
            url="https://example.com/ycb",
            retrieved_at=_FIXED_TIME,
        )
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.GRASP)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "类型错配" in outcome.reason
        assert "无真实抓取标注" not in outcome.reason

    def test_grasp_legit_format_not_blocked(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """GRASP + npz（合法抓取标注格式）不误报：仍走 Skill 路径装配 ParsedItem。"""
        raw = RawData(
            source=DataSource.GRASPNET,
            item_id="banana",
            format="npz",
            data=b"\x93NUMPY fake",
            url="https://example.com/graspnet",
            retrieved_at=_FIXED_TIME,
        )
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.GRASP)
        skill_result = StandardResult(success=True, canonical_format="CanonicalGrasp", data="fake")
        fake_skill = type("_FakeSkill", (), {"process": lambda self, data, **kw: skill_result})()
        monkeypatch.setattr(SkillRegistry, "get_skill", lambda self, req_type: fake_skill)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, ParsedItem)
        assert outcome.canonical_format == "CanonicalGrasp"

    def test_mesh_mismatch_npz(self) -> None:
        """MESH + npz（抓取格式）→ MissingItem，reason 含期望 mesh 与实际 npz。"""
        raw = _make_raw("npz", b"\x93NUMPY", item_id="hand")
        result = RetrievalResult(req_id="req_001", data=raw, status="success")
        req = _make_req(DataReqType.MESH)

        outcome = SkillRegistry().process_retrieval_result(result, req)

        assert isinstance(outcome, MissingItem)
        assert "期望 mesh" in outcome.reason
        assert "实际返回 npz" in outcome.reason

    def test_format_mismatch_reason_pure_function(self) -> None:
        """_format_mismatch_reason：合法格式返回 None，错配返回含期望/实际的 reason。"""
        grasp_req = _make_req(DataReqType.GRASP)
        mesh_req = _make_req(DataReqType.MESH)
        sim_req = _make_req(DataReqType.SIM_CONFIG)
        urdf_req = _make_req(DataReqType.ROBOT_URDF)

        # 各 req_type 的现存合法格式不误报（含大小写不敏感）
        for fmt in ("npz", "pkl", "npy", "mat", "json", "h5", "hdf5"):
            assert _format_mismatch_reason(grasp_req, fmt) is None
        assert _format_mismatch_reason(grasp_req, "NPZ") is None
        for fmt in ("urdf", "xacro", "zip", "json"):
            assert _format_mismatch_reason(urdf_req, fmt) is None
        for fmt in ("obj", "stl", "ply", "dae", "glb", "gltf", "zip", "json"):
            assert _format_mismatch_reason(mesh_req, fmt) is None
        for fmt in ("xml", "mjcf", "mujoco", "json", "py", "python", "yaml"):
            assert _format_mismatch_reason(sim_req, fmt) is None

        # 错配返回语义化 reason
        reason = _format_mismatch_reason(grasp_req, "obj")
        assert reason is not None
        assert "期望" in reason and "实际返回 obj" in reason
        reason = _format_mismatch_reason(mesh_req, "npz")
        assert reason is not None
        assert "期望 mesh" in reason and "实际返回 npz" in reason
        reason = _format_mismatch_reason(urdf_req, "markdown")
        assert reason is not None
        assert "实际返回 markdown" in reason
