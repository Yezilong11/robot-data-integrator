# src/rdi/skills/mesh_process.py
"""MeshSkill — 3D 几何数据处理 Skill.

用 trimesh 将 STL/OBJ/PLY/DAE 统一加载为 ``trimesh.Trimesh``，标准化坐标系
（原点移到质心、单位统一为米），并生成多精度版本。标准化产物即
``trimesh.Trimesh``，无需自定义中间表示。

处理失败时返回降级 ``StandardResult(success=False)``，不抛异常中断流程。
"""

import io
import warnings
import zipfile
from typing import Any

import numpy as np
import trimesh

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# 支持的直接输入格式（trimesh 可直接加载）
_SUPPORTED_FMTS = frozenset({"stl", "obj", "ply", "dae", "glb"})
# zip 内部支持的 mesh 扩展名
_ZIP_MESH_EXTS = frozenset({"stl", "obj", "ply", "dae", "glb"})
# 疑似毫米单位阈值：bounding box 最大边长 > 10 视为毫米，需除以 1000 转米
_MM_TO_M_EXTENT = 10.0
# 触发 LOD 简化的最小面数
_LOD_FACE_THRESHOLD = 400
# 面数过少阈值（用于 warning 与 validate）
_LOW_FACE_COUNT = 100
_CANONICAL_FORMAT = "trimesh.Trimesh"


class MeshSkill(BaseSkill):
    """3D Mesh 处理 Skill：parse → standardize → generate_lod / validate."""

    skill_name = "mesh"

    def parse(self, mesh_bytes: bytes, fmt: str) -> trimesh.Trimesh:
        """解析 STL/OBJ/PLY/DAE 字节为统一的 trimesh 对象。

        Args:
            mesh_bytes: 原始 mesh 字节
            fmt: 文件格式（stl/obj/ply/dae）

        Returns:
            ``trimesh.Trimesh`` 对象

        Raises:
            Exception: trimesh 加载失败时抛出，由 ``process`` 捕获降级
        """
        loaded = trimesh.load(io.BytesIO(mesh_bytes), file_type=fmt, force="mesh")
        if not isinstance(loaded, trimesh.Trimesh):
            raise ValueError(f"trimesh 加载结果不是 Trimesh: {type(loaded).__name__}")
        return loaded

    def standardize(self, mesh: trimesh.Trimesh) -> tuple[trimesh.Trimesh, list[str]]:
        """统一到标准坐标系：原点移到质心，单位统一为米。

        Args:
            mesh: 原始 trimesh 对象

        Returns:
            (标准化后的 mesh, 转换步骤列表)
        """
        mesh = mesh.copy()
        transformations: list[str] = []

        # ponytail: trimesh.center_mass 对非水密/零体积 mesh 返回 NaN（不会自动
        # 回退到 centroid），会导致顶点全部被 NaN 污染；这里手动回退。
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            center = mesh.center_mass
        if not bool(np.all(np.isfinite(center))):
            center = mesh.centroid
        mesh.vertices -= center
        transformations.append("recenter_to_centroid")

        extent = float(mesh.extents.max())
        if extent > _MM_TO_M_EXTENT:
            mesh.vertices /= 1000.0
            transformations.append("unit_mm_to_m")

        return mesh, transformations

    def generate_lod(self, mesh: trimesh.Trimesh) -> dict[str, trimesh.Trimesh]:
        """生成多精度版本：``high``（渲染）与 ``collision``（碰撞检测）。

        面数 > 400 时将 collision 简化至 1/4 面数；否则 collision 退化为原 mesh，
        由 ``process`` 追加 warning。``simplify_quadric_decimation`` 依赖可选包
        ``fast-simplification``，缺失时 collision 退化为原 mesh。

        Args:
            mesh: 标准化后的 trimesh 对象

        Returns:
            ``{"high": <原 mesh>, "collision": <简化或原 mesh>}``
        """
        if len(mesh.faces) > _LOD_FACE_THRESHOLD:
            try:
                collision = mesh.simplify_quadric_decimation(
                    face_count=len(mesh.faces) // 4,
                )
            except Exception:
                # ponytail: fast-simplification 未安装时退化；升级路径=安装该包
                collision = mesh
            return {"high": mesh, "collision": collision}
        return {"high": mesh, "collision": mesh}

    def _load_zip_mesh(self, data: bytes) -> trimesh.Trimesh:
        """解压 zip，找到第一个支持的 mesh 文件并用 trimesh 加载。"""
        with zipfile.ZipFile(io.BytesIO(data), "r") as zf:
            names = [
                name
                for name in zf.namelist()
                if not name.endswith("/") and name.rsplit(".", 1)[-1].lower() in _ZIP_MESH_EXTS
            ]
            if not names:
                raise ValueError("zip 中未找到支持的 mesh 文件 (stl/obj/ply/dae/glb)")
            names.sort()
            chosen = names[0]
            file_bytes = zf.read(chosen)
            ext = chosen.rsplit(".", 1)[-1].lower()
        loaded = trimesh.load(io.BytesIO(file_bytes), file_type=ext, force="mesh")
        if not isinstance(loaded, trimesh.Trimesh):
            raise ValueError(f"trimesh 加载结果不是 Trimesh: {type(loaded).__name__}")
        return loaded

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """处理原始 mesh 字节，返回标准化结果。

        Args:
            data: 原始 mesh 字节
            **kwargs: ``fmt`` 显式格式；``filename`` 推断格式；``name`` 输出名

        Returns:
            ``StandardResult``，失败时 ``success=False``、``data=None``，不抛异常
        """
        fmt = self._infer_fmt(kwargs)
        try:
            mesh = self._load_zip_mesh(data) if fmt == "zip" else self.parse(data, fmt)
            # trimesh 对损坏输入常返回空 mesh（0 面）而非抛错，视作解析失败
            if len(mesh.faces) == 0:
                return StandardResult(
                    success=False,
                    canonical_format=_CANONICAL_FORMAT,
                    errors=["Mesh 解析失败: 解析结果为空 (faces=0)"],
                )
            mesh, _transformations = self.standardize(mesh)
        except Exception as e:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=[f"Mesh 解析失败: {e}"],
            )

        warnings_list: list[str] = []
        if not mesh.is_watertight:
            warnings_list.append(f"Mesh 非水密 (faces={len(mesh.faces)})")
        if len(mesh.faces) < _LOW_FACE_COUNT:
            warnings_list.append(f"Mesh 面数过少 ({len(mesh.faces)})")

        output_path: str | None = None
        name = kwargs.get("name")
        if isinstance(name, str) and name:
            output_path = f"objects/{name}.stl"

        # provenance 由 parse_convert 节点从 RawData 装配，Skill 保持纯净
        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data=mesh,
            output_path=output_path,
            completeness_pct=100.0,
            warnings=warnings_list,
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验 Mesh 处理结果：水密性与面数。

        Args:
            result: ``process`` 的返回值

        Returns:
            ``ValidationReport``，处理失败时 ``is_valid=False`` + ERROR
        """
        if not result.success or result.data is None:
            return ValidationReport(
                is_valid=False,
                issues=[
                    ValIssue(
                        severity=Severity.ERROR,
                        req_id="mesh",
                        message="Mesh 处理失败，无可校验数据",
                    )
                ],
                summary="Mesh 处理失败",
            )

        mesh = result.data
        issues: list[ValIssue] = []
        if not mesh.is_watertight:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="mesh",
                    message=f"Mesh 非水密 (faces={len(mesh.faces)})",
                    suggestion="检查 mesh 是否有孔洞或未封闭面",
                )
            )
        if len(mesh.faces) < _LOW_FACE_COUNT:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="mesh",
                    message=f"Mesh 面数过少 ({len(mesh.faces)})",
                    suggestion="使用更高精度的原始 mesh",
                )
            )

        return ValidationReport(
            is_valid=True,
            issues=issues,
            summary=f"Mesh 校验完成 (faces={len(mesh.faces)}, warnings={len(issues)})",
        )

    @staticmethod
    def _infer_fmt(kwargs: dict[str, Any]) -> str:
        """从 kwargs 推断 mesh 格式：fmt > filename 扩展名 > 默认 stl。"""
        fmt = kwargs.get("fmt")
        if isinstance(fmt, str) and fmt:
            return fmt.lower()
        filename = kwargs.get("filename", "")
        if isinstance(filename, str) and "." in filename:
            ext = filename.rsplit(".", 1)[-1].lower()
            if ext in _SUPPORTED_FMTS:
                return ext
            if ext == "zip":
                return ext
        return "stl"
