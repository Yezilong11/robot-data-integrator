"""GraspSkill 元数据降级（降级成功语义）测试。

数据集仅返回元数据 JSON（无真实 npz/pkl）时，按 Day2 修复的 fmt=json
降级消费契约（PaperSkill 同款）返回 success + is_fallback=True：
fetch 显式降级 → skill 消费为可用结果，装配 ParsedItem，判定 PASS_WITH_FALLBACK。
"""

import json
from pathlib import Path

import numpy as np
import pytest

from rdi.skills.grasp_parse import GraspSkill

SAMPLE_DIR = Path(__file__).parent / "sample_data" / "grasp"


class TestMetadataFallback:
    """数据集仅返回元数据 JSON → 降级成功语义（success + is_fallback=True）。"""

    def test_graspnet_metadata_json_returns_success_fallback(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            name="banana_grasps",
            object_name="banana",
        )
        assert result.success
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"
        assert result.data is not None
        assert any("元数据" in w for w in result.warnings)

    def test_dexgraspnet_metadata_json_returns_success_fallback(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "dexgraspnet", "reason": "no single pkl available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="dexgraspnet",
            name="mug_grasps",
            object_name="mug",
        )
        assert result.success
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"
        assert result.data is not None

    def test_graspnet_non_metadata_json_still_fails(self) -> None:
        skill = GraspSkill()
        payload = {"foo": "bar"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            name="x",
        )
        assert not result.success
        assert any("解析失败" in e for e in result.errors)


class TestDataSourceQuality:
    """data_source_quality 标注测试。"""

    def test_real_npz_marks_real(self) -> None:
        """真实 GraspNet npz 解析成功 → data_source_quality="real"。"""
        skill = GraspSkill()
        data = (SAMPLE_DIR / "sample_labels.npz").read_bytes()
        result = skill.process(data, dataset_name="graspnet", max_points=5)
        assert result.success
        assert result.data_source_quality == "real"
        assert len(result.data["grasps"]) > 0

    def test_synthetic_fallback_marks_fallback(self) -> None:
        """metadata JSON 无真实数据 → 降级成功，data_source_quality="fallback"。"""
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            object_name="banana",
        )
        assert result.success
        assert result.data_source_quality == "fallback"

    def test_synthetic_fallback_marks_is_fallback(self) -> None:
        """元数据降级结果 → is_fallback=True 且 data_source_quality="fallback"。"""
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            object_name="banana",
        )
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"

    def test_real_dexgrasp_pkl_marks_real(self) -> None:
        """真实 DexGrasp 格式 pkl（无 graspnetAPI）→ data_source_quality="real"。"""
        skill = GraspSkill()
        data = (SAMPLE_DIR / "sample_dexgrasp.pkl").read_bytes()
        result = skill.process(data, dataset_name="dexgraspnet", name="mug")
        assert result.success
        assert result.data_source_quality == "real"
        assert result.completeness_pct == 100.0
        assert len(result.data["grasps"]) == 3
        for g in result.data["grasps"]:
            assert len(g["orientation"]) == 4
            assert abs(g["width"] - 0.05) < 0.02  # DexGrasp 宽度量级（米）

    def test_invalid_dexgrasp_pkl_returns_failure(self) -> None:
        """损坏 pkl（无法反序列化）→ 失败语义（非降级，数据损坏不消费）。"""
        skill = GraspSkill()
        result = skill.process(b"not a pkl", dataset_name="dexgraspnet")
        assert not result.success
        assert result.data is None
        assert any("反序列化失败" in e for e in result.errors)


class TestCanonicalGraspUnits:
    """D1：CanonicalGrasp 单位/坐标系标注（按 DATASET_CONVENTIONS 填充）。"""

    def test_standardize_grasps_annotates_units_and_frame(self) -> None:
        """standardize_grasps 按 dexgraspnet 约定填 frame=object_center，units 为标准化米制。"""
        skill = GraspSkill()
        raw = [
            {
                "position": [0.01, 0.02, 0.03],
                "quaternion": [1.0, 0.0, 0.0, 0.0],  # quaternion_wxyz
                "width": 0.04,
                "score": 0.9,
            }
        ]
        grasps = skill.standardize_grasps(raw, "dexgraspnet")
        assert len(grasps) == 1
        assert grasps[0].units == "meter"
        assert grasps[0].frame == "object_center"

    def test_standardize_grasps_millimeter_conversion_annotated(self) -> None:
        """abdataset（millimeter 约定）→ position/width 除以 1000，标注仍为标准化米制。"""
        skill = GraspSkill()
        raw = [
            {
                "position": [10.0, 20.0, 30.0],
                "quaternion": [0.0, 0.0, 0.0, 1.0],  # quaternion_xyzw
                "width": 40.0,
                "score": 0.9,
            }
        ]
        grasps = skill.standardize_grasps(raw, "abdataset")
        assert len(grasps) == 1
        assert grasps[0].units == "meter"
        assert grasps[0].frame == "object_center"
        assert abs(grasps[0].width - 0.04) < 1e-9
        assert np.allclose(grasps[0].position, [0.01, 0.02, 0.03])

    def test_finish_standardize_accepts_convention_and_field_map(self) -> None:
        """_finish_standardize 透传 convention/field_map：LLM 动态约定与字段映射覆盖硬编码约定。

        覆盖后 ycb（硬编码 euler/world/meter）按约定 matrix/object_center/millimeter 处理，
        结果标注 units/coordinate_frame 与数据保持一致。
        """
        skill = GraspSkill()
        raw = [
            {
                "pos": [10.0, 20.0, 30.0],  # position
                "rot": np.eye(3).tolist(),  # rotation_matrix
                "w": 40.0,  # width
                "sc": 0.9,  # score
            }
        ]
        field_map = {"pos": "position", "rot": "rotation_matrix", "w": "width", "sc": "score"}
        conv = {"rotation": "matrix", "origin": "object_center", "unit": "millimeter"}
        result = skill._finish_standardize(
            raw, "ycb", "grasps/x.json", convention=conv, field_map=field_map
        )
        assert result.success
        assert result.units == "millimeter"
        assert result.coordinate_frame == "object_center"
        grasp = result.data["grasps"][0]
        assert np.allclose(grasp["position"], [0.01, 0.02, 0.03])  # 10mm → 0.01m
        assert abs(grasp["width"] - 0.04) < 1e-9

    def test_parse_graspnet_npz_annotates_camera_frame(self) -> None:
        """npz 直解路径：frame 按 graspnet 约定填 camera，units 为标准化米制。"""
        skill = GraspSkill()
        data = (SAMPLE_DIR / "sample_labels.npz").read_bytes()
        grasps = skill.parse_graspnet_npz(data, max_points=2)
        assert grasps
        assert all(g.units == "meter" for g in grasps)
        assert all(g.frame == "camera" for g in grasps)

    def test_grasp_dict_serializes_units_and_frame(self) -> None:
        """序列化 dict 携带 units/frame，落盘抓取自带量纲标注。"""
        skill = GraspSkill()
        data = (SAMPLE_DIR / "sample_labels.npz").read_bytes()
        result = skill.process(data, dataset_name="graspnet", max_points=2)
        assert result.success
        for g in result.data["grasps"]:
            assert g["units"] == "meter"
            assert g["frame"] == "camera"
        assert result.units == "millimeter"  # DATASET_CONVENTIONS graspnet 原始单位约定
        assert result.coordinate_frame == "camera"


class TestUnknownDatasetLLMSemantics:
    """D2：未知数据集约定 → LLM 语义识别补充（_parse_unknown_dataset）。"""

    def test_unknown_dataset_with_llm_semantics(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM 识别成功 → 产出 CanonicalGrasp，field_map 生效（毫米→米 /1000）。"""
        from rdi.intelligence import decisions
        from rdi.intelligence.schemas import SemanticConvention

        skill = GraspSkill()
        raw = [{"trans": [0.0, 0.0, 0.02], "width": 0.05, "score": 0.9, "quaternion": [0, 0, 0, 1]}]
        conv = SemanticConvention(
            dataset_name="mygrid",
            semantic_type="grasp_pose",
            rotation="quaternion_xyzw",
            origin="object_center",
            unit="millimeter",
            field_map={"trans": "position"},
            confidence=0.85,
            needs_human_review=False,
        )
        monkeypatch.setattr(decisions, "unify_semantics", lambda **kw: conv)

        result = skill.process(
            json.dumps(raw).encode("utf-8"),
            dataset_name="mygrid",
            name="banana_grasps",
        )

        assert result.success
        assert result.data is not None
        # position 毫米→米 /1000：0.02mm = 2e-5m
        assert np.allclose(result.data["grasps"][0]["position"], [0.0, 0.0, 2e-5])
        assert result.units == "millimeter"  # 保留 LLM 标注的原始单位
        assert result.coordinate_frame == "object_center"
        assert result.semantic_convention is not None
        assert result.semantic_convention["field_map"] == {"trans": "position"}
        assert result.semantic_convention["confidence"] == 0.85
        assert result.confidence_score == 0.85
        assert any("未知数据集约定" in w for w in result.warnings)
        assert not any("语义待人工确认" in w for w in result.warnings)
        # LLM 决策调用记录：status=ok + elapsed
        assert result.llm_usage is not None
        assert result.llm_usage["decision"] == "unify_semantics"
        assert result.llm_usage["status"] == "ok"
        assert isinstance(result.llm_usage["elapsed"], float)

    def test_unknown_dataset_with_llm_semantics_needs_review(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """needs_human_review=True → warnings 含「语义待人工确认」。"""
        from rdi.intelligence import decisions
        from rdi.intelligence.schemas import SemanticConvention

        skill = GraspSkill()
        raw = [
            {"position": [0.0, 0.0, 0.02], "width": 0.05, "score": 0.9, "quaternion": [0, 0, 0, 1]}
        ]
        conv = SemanticConvention(
            dataset_name="mygrid",
            semantic_type="grasp_pose",
            rotation="quaternion_xyzw",
            origin="object_center",
            unit="millimeter",
            field_map={},
            confidence=0.5,
            needs_human_review=True,
        )
        monkeypatch.setattr(decisions, "unify_semantics", lambda **kw: conv)

        result = skill.process(json.dumps(raw).encode("utf-8"), dataset_name="mygrid")

        assert result.success
        assert any("语义待人工确认" in w for w in result.warnings)
        assert result.confidence_score == 0.5

    def test_unknown_dataset_llm_failure_falls_back(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """LLM 识别失败（None）→ 现状降级：失败 + errors 含「未知数据集约定」。"""
        from rdi.intelligence import decisions

        skill = GraspSkill()
        raw = [{"trans": [0.0, 0.0, 0.02], "width": 0.05, "score": 0.9, "quaternion": [0, 0, 0, 1]}]
        monkeypatch.setattr(decisions, "unify_semantics", lambda **kw: None)

        result = skill.process(json.dumps(raw).encode("utf-8"), dataset_name="mygrid")

        assert not result.success
        assert result.data is None
        assert any("未知数据集约定" in e for e in result.errors)
        # LLM 决策调用记录保留降级状态
        assert result.llm_usage is not None
        assert result.llm_usage["decision"] == "unify_semantics"
        assert result.llm_usage["status"] == "fallback"

    def test_unknown_dataset_unparseable_skips_llm(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """数据非列表/解码失败 → 不调用 LLM，直接返回现状失败结果。"""
        from rdi.intelligence import decisions

        skill = GraspSkill()
        calls = []
        monkeypatch.setattr(decisions, "unify_semantics", lambda **kw: calls.append(kw) or None)

        result = skill.process(b"not json/pkl", dataset_name="mygrid")

        assert not result.success
        assert any("未知数据集约定" in e for e in result.errors)
        assert calls == []  # 无可摘要数据时不发起 LLM 调用
