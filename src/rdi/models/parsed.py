# src/rdi/models/parsed.py
"""Skill 解析标准化后的数据模型。

每个 Skill 处理完成后输出 ParsedItem，
包含标准化数据、溯源信息和完整度评估。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import DataReqType, DataSource, ProvenanceEntry


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
