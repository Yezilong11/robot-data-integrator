# src/rdi/skills/grasp_parse.py
"""GraspSkill — 6-DOF 抓取姿态统一。

将 GraspNet / DexGraspNet / YCB / ABDataset 抓取姿态统一为 ``CanonicalGrasp``
（position 米、orientation 四元数 [x,y,z,w]、width 米、score）。

校准说明（ponytail: 真实数据 ≠ spec 理想）：
- GraspNet-1Billion ``grasp_labels/*.npz`` 实测为**米制**，非文档 2.3 所述毫米：物体 000
  ``textured.obj`` extents ≈ [0.07, 0.16, 0.21] m，``points`` 由该 mesh 采样故为米；
  ``offsets`` 末维实测 ``[角度, 深度~0.01-0.04m, 宽度~0.085-0.13m]``。再 /1000 会得
  10μm 级荒谬值，故 ``parse_graspnet_npz`` 不做单位换算。
- ``DATASET_CONVENTIONS["graspnet"]["unit"]="millimeter"`` 保留文档 2.3 场景级抓取约定，
  供 ``standardize_grasps`` 处理调用方按约定传入的原始抓取；与 npz 内部米制分离。
- ``graspnetAPI`` 未安装，旋转矩阵为近似重建（approach=point-centroid 外法向 +
  in-plane r*π/2），completeness_pct 降为 70.0 并记 warning。
"""

import importlib
import io
import json
import pickle
from dataclasses import dataclass
from typing import Any

import numpy as np
from numpy.lib.npyio import NpzFile
from scipy.spatial.transform import Rotation  # type: ignore[import-untyped]

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill


@dataclass
class CanonicalGrasp:
    """标准化抓取姿态中间表示（position 米 shape (3,)、orientation [x,y,z,w] shape (4,)、width 米、score）。"""

    position: np.ndarray
    orientation: np.ndarray
    width: float
    score: float


DATASET_CONVENTIONS: dict[str, dict[str, str]] = {
    "graspnet": {"rotation": "matrix", "origin": "camera", "unit": "millimeter"},
    "dexgraspnet": {"rotation": "quaternion_wxyz", "origin": "object_center", "unit": "meter"},
    "ycb": {"rotation": "euler", "origin": "world", "unit": "meter"},
    "abdataset": {"rotation": "quaternion_xyzw", "origin": "object_center", "unit": "millimeter"},
}

_APPROX_COMPLETENESS = 70.0  # graspnetAPI 不可用时近似重建旋转的完整度
_PER_POINT_CAP = 6  # parse_graspnet_npz 每个点最多保留的近似抓取数


def _get_field(grasp: Any, key: str) -> Any:
    """从原始抓取（dict 或对象）读取字段。"""
    if isinstance(grasp, dict):
        return grasp[key]
    return getattr(grasp, key)


def _align_z_to(approach: np.ndarray) -> np.ndarray:
    """构造旋转矩阵使 z 轴对齐 ``approach``（单位向量），返回 3x3 右手系矩阵。

    ponytail: 手工构造基比 scipy.align_vectors 更确定，便于控制平行退化边角。
    """
    z = np.asarray(approach, dtype=np.float64)
    ref = np.array([0.0, 0.0, 1.0]) if abs(z[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    x = np.cross(ref, z)
    xn = float(np.linalg.norm(x))
    if xn < 1e-9:
        return np.eye(3, dtype=np.float64)
    x = x / xn
    y = np.cross(z, x)
    yn = float(np.linalg.norm(y))
    if yn > 1e-9:
        y = y / yn
    return np.column_stack((x, y, z))


class GraspSkill(BaseSkill):
    """抓取姿态解析 Skill：GraspNet npz 直解（米制近似旋转）；DexGraspNet pkl 在 graspnetAPI 不可用时降级；未知约定报错。"""

    skill_name = "grasp"

    def standardize_grasps(self, raw_grasps: list[Any], dataset_name: str) -> list[CanonicalGrasp]:
        """按 ``DATASET_CONVENTIONS`` 标准化原始抓取。

        旋转 matrix/quaternion_wxyz(重排为 xyzw)/euler/quaternion_xyzw → 四元数 [x,y,z,w]；
        unit=millimeter 时 position 与 width 除以 1000。KeyError: dataset_name 未知；
        ValueError: 旋转字段缺失或无法解析。
        """
        conv = DATASET_CONVENTIONS[dataset_name]  # KeyError 由调用方捕获
        rot_kind = conv["rotation"]
        to_meters = conv["unit"] == "millimeter"
        results: list[CanonicalGrasp] = []
        for g in raw_grasps:
            pos = np.asarray(_get_field(g, "position"), dtype=np.float64).copy()
            width = float(_get_field(g, "width"))
            score = float(_get_field(g, "score"))
            quat_xyzw = np.asarray(self._rotation_from_raw(g, rot_kind).as_quat(), dtype=np.float64)
            if to_meters:
                pos = pos / 1000.0
                width = width / 1000.0
            results.append(CanonicalGrasp(pos, quat_xyzw, width, score))
        return results

    @staticmethod
    def _rotation_from_raw(grasp: Any, rot_kind: str) -> Rotation:
        """按约定从原始抓取构造 ``Rotation``。"""
        if rot_kind == "matrix":
            return Rotation.from_matrix(
                np.asarray(_get_field(grasp, "rotation_matrix"), dtype=np.float64)
            )
        if rot_kind == "quaternion_wxyz":
            q = np.asarray(_get_field(grasp, "quaternion"), dtype=np.float64)
            return Rotation.from_quat(np.array([q[1], q[2], q[3], q[0]]))  # wxyz→xyzw
        if rot_kind == "quaternion_xyzw":
            return Rotation.from_quat(np.asarray(_get_field(grasp, "quaternion"), dtype=np.float64))
        if rot_kind == "euler":
            return Rotation.from_euler(
                "xyz", np.asarray(_get_field(grasp, "euler"), dtype=np.float64)
            )
        raise ValueError(f"未知旋转约定: {rot_kind}")

    def parse_graspnet_npz(self, data: bytes, max_points: int = 5) -> list[CanonicalGrasp]:
        """解码 GraspNet-1Billion ``*_labels.npz`` 为 ``CanonicalGrasp`` 列表。

        仅解码前 ``max_points`` 个点，跳过 collision=True 或 score<=0 项，输出上限
        ``max_points * _PER_POINT_CAP``。实测 npz 为米制（见模块 docstring），position 取
        ``points`` 不 /1000；``offsets`` 末维 ``[角度, 深度, 宽度]`` 仅取宽度作 ``width``。
        旋转为近似重建，需 ``graspnetAPI`` 精确还原 300 方向。
        """
        npz = np.load(io.BytesIO(data), allow_pickle=True)
        if not isinstance(npz, NpzFile):
            raise ValueError("输入不是合法的 GraspNet npz 归档")
        points = np.asarray(npz["points"], dtype=np.float64)
        offsets = np.asarray(npz["offsets"], dtype=np.float64)
        collision = np.asarray(npz["collision"])
        scores = np.asarray(npz["scores"], dtype=np.float64)

        n_points = min(max_points, int(points.shape[0]))
        n_app, n_dep, n_ang = int(offsets.shape[1]), int(offsets.shape[2]), int(offsets.shape[3])
        cap = max_points * _PER_POINT_CAP
        centroid = points[:n_points].mean(axis=0) if n_points > 0 else np.zeros(3)

        grasps: list[CanonicalGrasp] = []
        for i in range(n_points):
            p = points[i]
            approach = p - centroid
            an = float(np.linalg.norm(approach))
            approach = approach / an if an > 1e-9 else np.array([0.0, 0.0, 1.0])
            r_approach = _align_z_to(approach)
            for a in range(n_app):
                for d in range(n_dep):
                    for r in range(n_ang):
                        if bool(collision[i, a, d, r]):
                            continue
                        sc = float(scores[i, a, d, r])
                        if sc <= 0.0:
                            continue
                        off = offsets[i, a, d, r]
                        w_cand = float(off[2])
                        width = w_cand if 0.0 < w_cand < 0.3 else 0.05
                        rmat = r_approach @ Rotation.from_euler("z", r * (np.pi / 2.0)).as_matrix()
                        quat = np.asarray(Rotation.from_matrix(rmat).as_quat(), dtype=np.float64)
                        grasps.append(CanonicalGrasp(p.copy(), quat, width, sc))
                        if len(grasps) >= cap:
                            return grasps
        return grasps

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """按数据集约定解析抓取数据，失败降级不抛异常。"""
        dataset_name = str(kwargs.get("dataset_name", "graspnet"))
        if dataset_name not in DATASET_CONVENTIONS:
            return StandardResult(
                success=False,
                canonical_format="CanonicalGrasp",
                errors=[f"未知数据集约定: {dataset_name}"],
            )
        name = kwargs.get("name")
        output_path = f"grasps/{name}.json" if name else None

        if dataset_name == "graspnet":
            try:
                grasps = self.parse_graspnet_npz(data, max_points=int(kwargs.get("max_points", 5)))
            except Exception as exc:  # noqa: BLE001 — 任意解析失败均降级
                return StandardResult(
                    success=False,
                    canonical_format="CanonicalGrasp",
                    errors=[f"GraspNet npz 解析失败: {exc}"],
                )
            return StandardResult(
                success=True,
                canonical_format="CanonicalGrasp",
                output_path=output_path,
                completeness_pct=_APPROX_COMPLETENESS,
                confidence_score=0.7,
                warnings=[
                    "graspnetAPI 不可用，旋转矩阵为近似重建"
                    "（approach=point-centroid 外法向 + in-plane r*π/2），"
                    "300 个 frustum 方向无法精确还原"
                ],
                data=grasps,
            )

        if dataset_name == "dexgraspnet":
            # pkl 反序列化依赖 graspnetAPI 自定义类；不可用时直接降级
            try:
                importlib.import_module("graspnetAPI")
            except ImportError:
                return StandardResult(
                    success=False,
                    canonical_format="CanonicalGrasp",
                    errors=["DexGraspNet pkl 需要 graspnetAPI 才能反序列化"],
                )
            try:
                obj = pickle.load(io.BytesIO(data))  # noqa: S301
            except Exception as exc:  # noqa: BLE001
                return StandardResult(
                    success=False,
                    canonical_format="CanonicalGrasp",
                    errors=[f"DexGraspNet pkl 需要 graspnetAPI 才能反序列化: {exc}"],
                )
            return self._finish_standardize(obj, dataset_name, output_path)

        # ycb / abdataset：尽力解析（json 或 pickle），失败降级
        return self._parse_generic(data, dataset_name, output_path)

    def _finish_standardize(
        self, raw: Any, dataset_name: str, output_path: str | None
    ) -> StandardResult:
        """对已加载的原始抓取列表调用 standardize_grasps 装配结果。"""
        if not isinstance(raw, list):
            return StandardResult(
                success=False,
                canonical_format="CanonicalGrasp",
                errors=[f"{dataset_name} 数据非抓取列表，无法标准化"],
            )
        try:
            grasps = self.standardize_grasps(raw, dataset_name)
        except (KeyError, ValueError) as exc:
            return StandardResult(
                success=False,
                canonical_format="CanonicalGrasp",
                errors=[f"{dataset_name} 标准化失败: {exc}"],
            )
        return StandardResult(
            success=True,
            canonical_format="CanonicalGrasp",
            output_path=output_path,
            completeness_pct=100.0,
            data=grasps,
        )

    def _parse_generic(
        self, data: bytes, dataset_name: str, output_path: str | None
    ) -> StandardResult:
        """ycb/abdataset 的尽力解析路径（json 或 pickle）。"""
        raw: Any = None
        try:
            decoded = json.loads(data.decode("utf-8"))
            if isinstance(decoded, list):
                raw = decoded
        except (ValueError, UnicodeDecodeError):
            pass
        if raw is None:
            try:
                raw = pickle.load(io.BytesIO(data))  # noqa: S301
            except Exception:  # noqa: BLE001
                return StandardResult(
                    success=False,
                    canonical_format="CanonicalGrasp",
                    errors=[f"{dataset_name} 数据解析失败（需原始抓取列表）"],
                )
        return self._finish_standardize(raw, dataset_name, output_path)

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验抓取结果：失败→invalid；任一 position 分量 |.|>1m→WARNING。"""
        if not result.success or result.data is None:
            return ValidationReport(is_valid=False, summary="抓取解析失败")
        grasps = result.data
        if not isinstance(grasps, list):
            return ValidationReport(is_valid=False, summary="抓取解析失败: 中间表示类型错误")
        issues: list[ValIssue] = []
        for idx, g in enumerate(grasps):
            if not isinstance(g, CanonicalGrasp):
                continue
            if bool(np.any(np.abs(g.position) > 1.0)):
                issues.append(
                    ValIssue(
                        severity=Severity.WARNING,
                        req_id=f"grasp#{idx}",
                        message=f"抓取点超出工作空间 (position={g.position.tolist()})，请检查坐标系约定",
                        suggestion="确认坐标系原点与单位是否已统一为米制物体中心系",
                        auto_fixable=False,
                    )
                )
        summary = f"抓取校验完成: {len(grasps)} 个抓取，{len(issues)} 个工作空间警告"
        return ValidationReport(is_valid=True, issues=issues, summary=summary)
