# src/rdi/skills/registry.py
"""SkillRegistry — 按 DataReqType 分发到对应 Skill 的注册表。

维护 ``DataReqType → BaseSkill`` 单例映射（懒加载），提供 ``get_skill`` 与
``process_retrieval_result`` 便捷方法。所有标准数据类型均已注册对应 Skill。

``process_retrieval_result`` 把 ``RetrievalResult.data.data`` 字节交给对应 Skill
处理，按 ``StandardResult`` 装配 ``ParsedItem``（provenance 从 RawData 继承），
处理失败或无对应 Skill 时装配 ``MissingItem``。Skill 抛出未预期异常时防御性降级
为 ``MissingItem``（Skill 本应自行降级，此处兜底防止节点崩溃）。
"""

from typing import Any

from rdi.models.common import DataReqType, DataSource, ProvenanceEntry
from rdi.models.goal import DataReq
from rdi.models.parsed import MissingItem, ParsedItem
from rdi.models.retrieval import RetrievalResult
from rdi.skills.base import BaseSkill
from rdi.skills.code_parse import CodeSkill
from rdi.skills.dataset_parse import DatasetSkill
from rdi.skills.grasp_parse import GraspSkill
from rdi.skills.mesh_process import MeshSkill
from rdi.skills.paper_parse import PaperSkill
from rdi.skills.policy_interface import PolicyInterfaceSkill
from rdi.skills.sensor_data import SensorDataSkill
from rdi.skills.sim_config import SimConfigSkill
from rdi.skills.urdf_convert import URDFSkill


def _dataset_name_from_source(source: DataSource) -> str:
    """由数据源推断抓取数据集名；未知源默认 graspnet。"""
    if source == DataSource.GRASPNET:
        return "graspnet"
    if source == DataSource.DEXGRASP:
        return "dexgraspnet"
    if source == DataSource.YCB:
        return "ycb"
    return "graspnet"


class SkillRegistry:
    """``DataReqType → BaseSkill`` 单例注册表（懒加载）。

    首次 ``get_skill`` 时实例化对应 Skill 并缓存，后续调用返回同一实例。
    """

    def __init__(self) -> None:
        # ponytail: 懒加载单例，避免 import 时实例化全部 Skill（部分依赖可选库）
        self._instances: dict[DataReqType, BaseSkill] = {}
        self._factory: dict[DataReqType, type[BaseSkill]] = {
            DataReqType.ROBOT_URDF: URDFSkill,
            DataReqType.MESH: MeshSkill,
            DataReqType.GRASP: GraspSkill,
            DataReqType.SIM_CONFIG: SimConfigSkill,
            DataReqType.POLICY_MODEL: PolicyInterfaceSkill,
            DataReqType.SENSOR_DATA: SensorDataSkill,
            DataReqType.PAPER: PaperSkill,
            DataReqType.CODE: CodeSkill,
            DataReqType.DATASET: DatasetSkill,
        }

    def get_skill(self, req_type: DataReqType) -> BaseSkill | None:
        """返回 req_type 对应的 Skill 单例；未注册类型返回 None。"""
        if req_type not in self._factory:
            return None
        if req_type not in self._instances:
            self._instances[req_type] = self._factory[req_type]()
        return self._instances[req_type]

    def process_retrieval_result(
        self,
        result: RetrievalResult,
        req: DataReq,
        context: dict[str, Any] | None = None,
    ) -> ParsedItem | MissingItem:
        """把 RetrievalResult 交给对应 Skill 处理，装配 ParsedItem 或 MissingItem。

        - ``result.data is None`` 或 ``status != "success"`` → MissingItem
        - req_type 无对应 Skill → MissingItem
        - Skill 处理成功且 data 非空 → ParsedItem（provenance 从 RawData 装配）
        - Skill 处理失败或抛异常 → MissingItem（防御性捕获）

        Args:
            context: 调用方传入的额外上下文，将透传给 Skill.process（如 object_name）。
        """
        if result.data is None or result.status != "success":
            reason = (
                f"检索失败[{result.status}]: {result.error_message}"
                if result.status == "error"
                else (result.error_message or "无原始数据")
            )
            return MissingItem(
                req_id=result.req_id,
                req_type=req.req_type,
                description=req.description or "",
                reason=reason,
                fallback_sources=[],
            )

        skill = self.get_skill(req.req_type)
        if skill is None:
            return MissingItem(
                req_id=result.req_id,
                req_type=req.req_type,
                description=req.description or "",
                reason=f"req_type {req.req_type} 无对应 Skill",
                fallback_sources=[],
            )

        raw = result.data
        fmt = raw.format
        name = raw.item_id or result.req_id
        extra: dict[str, Any] = dict(context) if context else {}
        if req.req_type == DataReqType.GRASP:
            # 抓取数据集约定由数据源推断；GRASP 的 process 需要 dataset_name
            src = result.source or raw.source
            extra["dataset_name"] = _dataset_name_from_source(src)

        try:
            res = skill.process(raw.data, fmt=fmt, name=name, url=raw.url, **extra)
        except Exception as exc:  # noqa: BLE001 — 防御性：Skill 应自身降级，但仍兜底
            return MissingItem(
                req_id=result.req_id,
                req_type=req.req_type,
                description=req.description or "",
                reason=f"Skill 处理异常: {exc}",
                fallback_sources=[],
            )

        if not res.success or res.data is None:
            reason = "; ".join(res.errors) or "Skill 处理失败"
            return MissingItem(
                req_id=result.req_id,
                req_type=req.req_type,
                description=req.description or "",
                reason=reason,
                fallback_sources=[],
            )

        # confidence 由 Skill 自身报告；is_inferred 据此推断
        confidence = res.confidence_score
        is_inferred = confidence < 1.0
        # P0-3 数据包自包含：仅 URDF/MJCF（robot_urdf / sim_config）携带原始字节与
        # 外部资产（mesh/texture），避免 DATASET 等大文件膨胀 state
        if req.req_type in (DataReqType.ROBOT_URDF, DataReqType.SIM_CONFIG):
            raw_bytes: bytes | None = raw.data
            assets: dict[str, bytes] = raw.assets
        else:
            raw_bytes = None
            assets = {}
        provenance = ProvenanceEntry(
            source=raw.source,
            source_url=raw.url,
            retrieved_at=raw.retrieved_at,
            original_format=raw.format,
            transformations=[],
            confidence_score=confidence,
            is_inferred=is_inferred,
        )
        return ParsedItem(
            req_id=result.req_id,
            req_type=req.req_type,
            name=name,
            canonical_format=res.canonical_format,
            output_path=res.output_path or "",
            data=res.data,
            raw_bytes=raw_bytes,
            assets=assets,
            reference=raw.reference,  # P0-4：未下载大文件引用无条件透传（已下载为 None）
            provenance=provenance,
            completeness_pct=res.completeness_pct,
            confidence_score=confidence,
            is_inferred=is_inferred,
            warnings=res.warnings,
            data_source_quality=res.data_source_quality,
            is_fallback=result.is_fallback,
        )


default_registry = SkillRegistry()
