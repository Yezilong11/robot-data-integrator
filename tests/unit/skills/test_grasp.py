# tests/unit/skills/test_grasp.py
"""GraspSkill 单元测试（SYNC）。

覆盖：GraspNet npz 解析成功、单位换算、四元数顺序 [x,y,z,w]、DexGraspNet pkl 降级、
未知数据集约定报错、工作空间越界 WARNING、旋转矩阵→四元数。

样本 ``sample_labels.npz`` 由真实 GraspNet-1Billion ``000_labels.npz`` 切片前 5 个
点生成（<2MB），测试自包含不依赖 E: 盘。
"""

from io import BytesIO
from pathlib import Path

import numpy as np

from rdi.models.common import Severity, StandardResult
from rdi.skills.grasp_parse import CanonicalGrasp, GraspSkill

SAMPLE_NPZ = Path(__file__).parent / "sample_data" / "grasp" / "sample_labels.npz"


def _load_sample_bytes() -> bytes:
    """读取样本 npz 为字节。"""
    return SAMPLE_NPZ.read_bytes()


class TestGraspSkillGraspNet:
    """GraspNet npz 解析路径测试。"""

    def test_parse_graspnet_npz_success(self) -> None:
        """正常情况：解析真实 GraspNet npz 样本为 JSON 可序列化的 grasp 列表。"""
        skill = GraspSkill()
        data = _load_sample_bytes()
        result = skill.process(data, dataset_name="graspnet", max_points=5)

        assert result.success
        assert result.canonical_format == "CanonicalGrasp"
        assert isinstance(result.data, dict)
        grasps = result.data["grasps"]
        assert len(grasps) > 0
        assert all(isinstance(g, dict) for g in grasps)
        # graspnetAPI 不可用 → 近似重建，completeness 降为 70.0 且 warnings 非空
        assert result.completeness_pct == 70.0
        assert result.confidence_score < 1.0
        assert any("graspnetAPI" in w for w in result.warnings)

        # 校准：GraspNet grasp_labels 实测为米制，position 直接取 points 不做 /1000
        raw = np.load(BytesIO(data), allow_pickle=True)
        raw_point0 = np.asarray(raw["points"][0], dtype=np.float64)
        assert np.allclose(np.asarray(grasps[0]["position"]), raw_point0)
        # 米制范围合理（< 1.0m，真实物体表面点 ~0.1m 量级）
        for g in grasps:
            assert bool(np.all(np.abs(np.asarray(g["position"])) < 1.0))

    def test_quaternion_order_xyzw(self) -> None:
        """正常情况：每个 orientation 为 shape (4,) 的单位四元数（scipy [x,y,z,w]）。"""
        skill = GraspSkill()
        result = skill.process(_load_sample_bytes(), dataset_name="graspnet", max_points=5)
        assert result.success
        for g in result.data["grasps"]:
            orientation = np.asarray(g["orientation"])
            assert orientation.shape == (4,)
            assert np.allclose(np.linalg.norm(orientation), 1.0, atol=1e-5)


class TestGraspSkillStandardize:
    """standardize_grasps 约定分发测试。"""

    def test_standardize_rotation_matrix_to_quat(self) -> None:
        """正常情况：单位旋转矩阵 → 四元数 [0,0,0,1]。"""
        skill = GraspSkill()
        raw = [
            {
                "position": np.array([0.0, 0.0, 0.0]),
                "rotation_matrix": np.eye(3),
                "width": 0.0,
                "score": 1.0,
            }
        ]
        grasps = skill.standardize_grasps(raw, "graspnet")
        assert np.allclose(grasps[0].orientation, [0.0, 0.0, 0.0, 1.0])

    def test_unit_conversion_mm_to_m(self) -> None:
        """正常情况：graspnet(mm) 约定对 position/width 做 /1000 换算。

        GraspNet grasp_labels npz 实测为米制（见 test_parse_graspnet_npz_success），
        故 /1000 换算在 standardize 约定路径上用合成 mm 输入验证。
        """
        skill = GraspSkill()
        raw = [
            {
                "position": np.array([100.0, 200.0, 300.0]),  # mm
                "rotation_matrix": np.eye(3),
                "width": 50.0,  # mm
                "score": 0.9,
            }
        ]
        grasps = skill.standardize_grasps(raw, "graspnet")
        assert np.allclose(grasps[0].position, [0.1, 0.2, 0.3])  # mm→m
        assert abs(grasps[0].width - 0.05) < 1e-9  # 50mm→0.05m


class TestGraspSkillDegradation:
    """降级与校验路径测试。"""

    def test_dexgraspnet_pkl_degrades(self) -> None:
        """异常情况：DexGraspNet pkl 反序列化失败 → 失败语义（数据损坏不消费）。"""
        skill = GraspSkill()
        result = skill.process(b"not a pkl", dataset_name="dexgraspnet")
        assert not result.success
        assert any("反序列化失败" in e for e in result.errors)

    def test_unknown_dataset_name(self) -> None:
        """异常情况：未知 dataset_name 返回 success=False，不猜测约定。"""
        skill = GraspSkill()
        result = skill.process(b"x", dataset_name="unknown_ds")
        assert not result.success
        assert any("未知" in e for e in result.errors)

    def test_validate_workspace_warning(self) -> None:
        """正常情况：position 任一分量 |.|>1m 触发 WARNING（不影响 is_valid）。"""
        skill = GraspSkill()
        grasps = [
            CanonicalGrasp(
                position=np.array([2.0, 0.0, 0.0]),
                orientation=np.array([0.0, 0.0, 0.0, 1.0]),
                width=0.05,
                score=1.0,
            )
        ]
        result = StandardResult(success=True, canonical_format="CanonicalGrasp", data=grasps)
        report = skill.validate(result)
        assert report.is_valid  # WARNING 不影响 is_valid
        assert any(
            vi.severity == Severity.WARNING and "工作空间" in vi.message for vi in report.issues
        )
