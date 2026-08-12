"""GraspSkill 元数据降级（失败语义）测试。

数据集仅返回元数据 JSON（无真实 npz/pkl）时不再以 success 交付合成抓取，
而是返回失败语义（errors 含「原始数据缺失，合成占位仅作参考」），由
registry 装配为 MissingItem，真实数据经 reference 供手动获取。
"""

import json
from pathlib import Path

import numpy as np

from rdi.skills.grasp_parse import GraspSkill

SAMPLE_DIR = Path(__file__).parent / "sample_data" / "grasp"


class TestMetadataFallback:
    """数据集仅返回元数据 JSON → 失败语义（不再以 success 交付合成抓取）。"""

    def test_graspnet_metadata_json_returns_failure(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            name="banana_grasps",
            object_name="banana",
        )
        assert not result.success
        assert result.canonical_format == "CanonicalGrasp"
        assert result.data is None
        assert any("原始数据缺失，合成占位仅作参考" in e for e in result.errors)

    def test_dexgraspnet_metadata_json_returns_failure(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "dexgraspnet", "reason": "no single pkl available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="dexgraspnet",
            name="mug_grasps",
            object_name="mug",
        )
        assert not result.success
        assert result.canonical_format == "CanonicalGrasp"
        assert result.data is None
        assert any("原始数据缺失，合成占位仅作参考" in e for e in result.errors)

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
        """metadata JSON 无真实数据 → 失败，但 data_source_quality="fallback" 标记保留。"""
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            object_name="banana",
        )
        assert not result.success
        assert result.data_source_quality == "fallback"

    def test_synthetic_fallback_marks_is_fallback(self) -> None:
        """元数据占位结果 → is_fallback=True 且 data_source_quality="fallback"。"""
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
        """损坏 pkl（无法反序列化）→ 失败语义（不再交付合成抓取），fallback 标记保留。"""
        skill = GraspSkill()
        result = skill.process(b"not a pkl", dataset_name="dexgraspnet")
        assert not result.success
        assert result.data is None
        assert result.data_source_quality == "fallback"
        assert result.is_fallback is True
        assert any("原始数据缺失，合成占位仅作参考" in e for e in result.errors)


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
