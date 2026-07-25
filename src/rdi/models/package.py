# src/rdi/models/package.py
"""数据包与解析结果模型。

包含解析标准化结果、数据包清单、缺失项等结构。
这些模型为 state.py 提供类型支撑，后续由 D/E 角色完善。
"""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import DataSource, ProvenanceEntry, ValidationReport


class ParsedItem(BaseModel):
    """标准化后的单个数据项。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    canonical_format: str = Field(description="标准化格式（如 URDF, STL, NPZ）")
    output_path: str = Field(description="输出文件路径")
    source: DataSource = Field(description="数据来源")
    provenance: ProvenanceEntry | None = Field(default=None, description="溯源信息")
    extra: dict[str, Any] = Field(default_factory=dict, description="额外信息")


class MissingItem(BaseModel):
    """未找到的数据项及替代建议。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    description: str = Field(description="原始需求描述")
    suggested_alternatives: list[str] = Field(
        default_factory=list,
        description="替代数据源或方案建议",
    )
    reason: str = Field(default="", description="未找到的原因")


class PackageManifest(BaseModel):
    """最终数据包清单。"""

    model_config = ConfigDict(extra="forbid")

    package_id: str = Field(description="数据包唯一标识")
    goal_summary: str = Field(description="研究目标摘要")
    items: list[ParsedItem] = Field(default_factory=list, description="包含的数据项")
    missing: list[MissingItem] = Field(default_factory=list, description="缺失项")
    validation: ValidationReport | None = Field(default=None, description="校验报告")
    output_dir: str = Field(default="", description="输出目录路径")
