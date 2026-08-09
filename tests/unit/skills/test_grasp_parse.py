"""GraspSkill 合成抓取与元数据降级测试。"""

import json
from pathlib import Path

import numpy as np

from rdi.skills.grasp_parse import CanonicalGrasp, GraspSkill, generate_synthetic_grasps

SAMPLE_DIR = Path(__file__).parent / "sample_data" / "grasp"


class TestGenerateSyntheticGrasps:
    """合成抓取生成测试。"""

    def test_returns_requested_count(self) -> None:
        grasps = generate_synthetic_grasps("banana", count=5)
        assert len(grasps) == 5
        assert all(isinstance(g, CanonicalGrasp) for g in grasps)

    def test_count_zero_guarded(self) -> None:
        grasps = generate_synthetic_grasps("banana", count=0)
        assert len(grasps) == 1

    def test_grasp_attributes(self) -> None:
        grasps = generate_synthetic_grasps("banana", count=3)
        quat = np.array([0.0, 1.0, 0.0, 0.0])
        for g in grasps:
            assert g.orientation.shape == (4,)
            assert np.allclose(g.orientation, quat)
            assert abs(g.width - 0.05) < 1e-9
            assert abs(g.score - 0.8) < 1e-9
            # position around [0, 0, 0.15]
            assert abs(g.position[2] - 0.15) < 1e-9
            assert np.linalg.norm(g.position[:2]) <= 0.02 + 1e-9

    def test_positions_vary(self) -> None:
        grasps = generate_synthetic_grasps("mug", count=5)
        positions = np.stack([g.position for g in grasps])
        # not all identical
        assert not np.allclose(positions, positions[0])
        # z is constant
        assert np.allclose(positions[:, 2], 0.15)


class TestMetadataFallback:
    """元数据 JSON 降级为合成抓取测试。"""

    def test_graspnet_metadata_json_returns_synthetic(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            name="banana_grasps",
            object_name="banana",
        )
        assert result.success
        assert result.canonical_format == "CanonicalGrasp"
        assert result.output_path == "grasps/banana_grasps.json"
        assert isinstance(result.data, dict)
        grasps = result.data["grasps"]
        assert len(grasps) == 5
        assert all(isinstance(g, dict) for g in grasps)
        assert all("position" in g and "orientation" in g for g in grasps)
        assert any("合成" in w for w in result.warnings)
        assert any("banana" in w for w in result.warnings)

    def test_dexgraspnet_metadata_json_returns_synthetic(self) -> None:
        skill = GraspSkill()
        payload = {"dataset_id": "dexgraspnet", "reason": "no single pkl available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="dexgraspnet",
            name="mug_grasps",
            object_name="mug",
        )
        assert result.success
        assert result.canonical_format == "CanonicalGrasp"
        assert result.output_path == "grasps/mug_grasps.json"
        assert isinstance(result.data, dict)
        grasps = result.data["grasps"]
        assert len(grasps) == 5
        assert all(isinstance(g, dict) for g in grasps)
        assert all("position" in g and "orientation" in g for g in grasps)
        assert any("合成" in w for w in result.warnings)

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
        """metadata JSON 降级为合成抓取 → data_source_quality="fallback"。"""
        skill = GraspSkill()
        payload = {"dataset_id": "graspnet-1b", "reason": "no single npz available"}
        result = skill.process(
            json.dumps(payload).encode("utf-8"),
            dataset_name="graspnet",
            object_name="banana",
        )
        assert result.success
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

    def test_invalid_dexgrasp_pkl_falls_back_to_synthetic(self) -> None:
        """损坏 pkl（无法反序列化）→ 降级合成抓取，data_source_quality="fallback"。"""
        skill = GraspSkill()
        result = skill.process(b"not a pkl", dataset_name="dexgraspnet")
        assert result.success
        assert result.data_source_quality == "fallback"
        assert any("合成" in w for w in result.warnings)
