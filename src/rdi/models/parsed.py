# src/rdi/models/parsed.py
"""Skill 解析标准化后的数据模型。

每个 Skill 处理完成后输出 ParsedItem，
包含标准化数据、溯源信息和完整度评估。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import DataReqType, DataSource, ProvenanceEntry

# 循环 import 检查：retrieval.py 仅依赖 common.py，不反向引用 parsed.py，
# 因此可安全使用真实类型 RawReference（无需退化为 Any）。
from .retrieval import RawReference


class ParsedItem(BaseModel):
    """单个需求解析标准化后的数据项。

    每个 Skill 处理完成后输出此模型。
    """

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    req_type: DataReqType = Field(description="数据类型")
    name: str = Field(description="数据项名称")
    canonical_format: str = Field(description="标准化格式名")
    output_path: str = Field(description="输出文件路径（相对于数据包根目录）")
    data: Any = Field(description="标准化后的数据对象（Python 对象，序列化时转为文件）")
    raw_bytes: bytes | None = Field(default=None, description="原始下载字节（URDF/MJCF 原文件）")
    assets: dict[str, bytes] = Field(
        default_factory=dict,
        description="引用的外部资源（相对路径 → 字节）",
    )
    assets_missing: list[str] = Field(
        default_factory=list,
        description="下载/加载阶段缺失的外部资源路径（透传自 RawData.metadata.assets_missing）",
    )
    provenance: ProvenanceEntry = Field(description="溯源信息")
    completeness_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="完整度百分比",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="置信度",
    )
    is_inferred: bool = Field(
        default=False,
        description="是否为模型推断数据",
    )
    warnings: list[str] = Field(default_factory=list, description="处理警告")
    data_source_quality: str | None = Field(
        default=None,
        description="数据来源真实程度：real / synthetic / fallback",
    )
    is_fallback: bool = Field(
        default=False,
        description="是否使用了备选源（透传自 RetrievalResult.is_fallback）",
    )
    reference: RawReference | None = Field(
        default=None,
        description="未下载大文件的引用记录（透传自 RawData.reference）",
    )
    units: str = Field(
        default="",
        description="数据单位标注（如 meter/millimeter/radian，空串=未标注）",
    )
    coordinate_frame: str = Field(
        default="",
        description="坐标系/参考系标注（如 camera/object_center/world/base_link，空串=未标注）",
    )
    timestamp_epoch: float | None = Field(
        default=None,
        description="数据对应的时间戳（Unix epoch 秒），None=无",
    )
    semantic_convention: dict[str, Any] | None = Field(
        default=None,
        description="LLM 生成的语义约定（SemanticConvention.model_dump()），None=无",
    )
    llm_usage: dict[str, Any] | None = Field(
        default=None,
        description="本次处理中的 LLM 决策调用记录（decision/status/model/elapsed），None=无",
    )


class MissingItem(BaseModel):
    """未找到的数据项及替代建议。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    req_type: DataReqType = Field(description="数据类型")
    description: str = Field(description="需求描述")
    reason: str = Field(description="未找到的原因")
    alternatives: list[str] = Field(
        default_factory=list,
        description="替代方案建议",
    )
    fallback_sources: list[DataSource] = Field(
        default_factory=list,
        description="可尝试的备选源",
    )
    llm_usage: dict[str, Any] | None = Field(
        default=None,
        description="本次处理中的 LLM 决策调用记录（decision/status/model/elapsed），None=无",
    )
