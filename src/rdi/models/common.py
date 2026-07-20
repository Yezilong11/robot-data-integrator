# src/rdi/models/common.py
"""通用数据模型，被所有模块引用。

包含数据源标识、溯源信息、置信度等基础结构。
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DataSource(str, Enum):
    """数据源类型枚举。"""

    ARXIV = "arxiv"
    IEEE = "ieee"
    GITHUB = "github"
    PAPERSWITHCODE = "paperswithcode"
    GRASPNET = "graspnet"
    DEXGRASP = "dexgrasp"
    YCB = "ycb"
    FRANKA = "franka"
    ALLEGRO = "allegro"
    ROBOTIQ = "robotiq"
    MUJOCO = "mujoco"
    ISAAC = "isaac"
    HUGGINGFACE = "huggingface"
    ZENODO = "zenodo"


class DataReqType(str, Enum):
    """数据需求类型枚举，对应六类异构数据。"""

    PAPER = "paper"
    CODE = "code"
    DATASET = "dataset"
    ROBOT_URDF = "robot_urdf"
    MESH = "mesh"
    GRASP = "grasp"
    SIM_CONFIG = "sim_config"
    POLICY_MODEL = "policy_model"
    SENSOR_DATA = "sensor_data"


class Priority(str, Enum):
    """数据需求优先级。"""

    REQUIRED = "required"  # 必需：缺少则实验无法复现
    RECOMMENDED = "recommended"  # 推荐：显著影响实验效果
    OPTIONAL = "optional"  # 可选：辅助参考


class ProvenanceEntry(BaseModel):
    """单条溯源记录，记录数据的来源和转换历史。"""

    source: DataSource = Field(description="数据来源")
    source_url: str = Field(description="原始URL")
    retrieved_at: datetime = Field(description="获取时间")
    original_format: str = Field(description="原始格式")
    transformations: list[str] = Field(
        default_factory=list,
        description="经历的转换步骤列表",
    )
    user_corrected: bool = Field(
        default=False, description="是否被用户修正过"
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="置信度：1.0=直接从源获取，<1.0=模型推断",
    )
    is_inferred: bool = Field(
        default=False,
        description="是否为模型推断数据（非直接获取）",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict, description="额外元数据"
    )


class StandardResult(BaseModel):
    """Skill 处理结果的基类。"""

    success: bool = Field(description="是否成功")
    canonical_format: str = Field(description="标准化后的格式名")
    output_path: str | None = Field(default=None, description="输出文件路径")
    completeness_pct: float = Field(
        default=100.0,
        ge=0.0,
        le=100.0,
        description="完整度百分比",
    )
    errors: list[str] = Field(default_factory=list, description="错误列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    provenance: ProvenanceEntry | None = Field(default=None)


class ValidationReport(BaseModel):
    """校验报告。"""

    is_valid: bool
    issues: list["ValIssue"] = Field(default_factory=list)
    summary: str = Field(default="", description="校验总结")


class ValIssue(BaseModel):
    """单条校验问题。"""

    severity: str = Field(description="ERROR 或 WARNING")
    req_id: str = Field(description="关联的需求ID")
    message: str = Field(description="问题描述")
    suggestion: str = Field(default="", description="修正建议")
    auto_fixable: bool = Field(default=False, description="是否可自动修正")


ValidationReport.model_rebuild()
