# src/rdi/models/common.py
"""通用数据模型，被所有模块引用。

包含数据源标识、溯源信息、置信度等基础结构。
所有 Pydantic 模型使用 `model_config = ConfigDict(extra="forbid")` 禁止额外字段。
"""

from datetime import datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ─── 枚举定义 ───


class DataSource(StrEnum):
    """数据源类型枚举。"""

    ARXIV = "arxiv"
    IEEE = "ieee"
    GITHUB = "github"
    PAPERSWITHCODE = "paperswithcode"
    HUGGINGFACE = "huggingface"
    GRASPNET = "graspnet"
    DEXGRASP = "dexgrasp"
    YCB = "ycb"
    GOOGLE_SCANNED = "google_scanned"
    ZENODO = "zenodo"
    FRANKA = "franka"
    ALLEGRO = "allegro"
    ROBOTIQ = "robotiq"
    MUJOCO = "mujoco"
    ISAAC = "isaac"


class DataReqType(StrEnum):
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
    UNKNOWN = "unknown"


class Priority(StrEnum):
    """数据需求优先级。"""

    REQUIRED = "required"
    RECOMMENDED = "recommended"
    OPTIONAL = "optional"


class Severity(StrEnum):
    """校验问题严重程度。"""

    ERROR = "error"
    WARNING = "warning"


# ─── 数据模型 ───


class ProvenanceEntry(BaseModel):
    """单条溯源记录，记录数据的来源和转换历史。

    每个数据项（ParsedItem）必须携带此信息。
    """

    model_config = ConfigDict(extra="forbid")

    source: DataSource = Field(description="数据来源")
    source_url: str = Field(description="原始 URL")
    retrieved_at: datetime = Field(description="获取时间")
    original_format: str = Field(description="原始格式（如 urdf, stl, npz）")
    transformations: list[str] = Field(
        default_factory=list,
        description="经历的转换步骤列表，按时间顺序",
    )
    user_corrected: bool = Field(
        default=False,
        description="是否被用户修正过",
    )
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="置信度：1.0=直接从源获取，<1.0=模型推断或用户修正",
    )
    is_inferred: bool = Field(
        default=False,
        description="是否为模型推断数据（非直接从源获取）",
    )
    extra: dict[str, Any] = Field(
        default_factory=dict,
        description="额外元数据（如原始文件大小、校验和等）",
    )


class ValIssue(BaseModel):
    """单条校验问题。"""

    model_config = ConfigDict(extra="forbid")

    severity: Severity = Field(description="严重程度：error 或 warning")
    req_id: str = Field(description="关联的需求 ID")
    message: str = Field(description="问题描述")
    suggestion: str = Field(default="", description="修正建议")
    auto_fixable: bool = Field(
        default=False,
        description="是否可自动修正",
    )
    context: dict[str, Any] = Field(
        default_factory=dict,
        description="额外上下文信息（如具体数值、位置等）",
    )


class ValidationReport(BaseModel):
    """校验报告。"""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool = Field(description="是否通过校验（无 ERROR 级别问题）")
    issues: list[ValIssue] = Field(default_factory=list, description="所有校验问题")
    summary: str = Field(default="", description="校验总结摘要")
    checked_at: datetime = Field(default_factory=datetime.now, description="校验时间")


class StandardResult(BaseModel):
    """Skill 处理结果的基类。

    所有 Skill 的 process() 方法返回此模型。
    """

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(description="是否成功")
    canonical_format: str = Field(description="标准化后的格式名")
    output_path: str | None = Field(default=None, description="输出文件路径")
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
        description="置信度：1.0=直接解析原始数据，<1.0=含推断/降级（如缺时间戳、Isaac 描述性解析、元数据-only）",
    )
    errors: list[str] = Field(default_factory=list, description="错误列表")
    warnings: list[str] = Field(default_factory=list, description="警告列表")
    provenance: ProvenanceEntry | None = Field(default=None, description="溯源信息")
    data_source_quality: str | None = Field(
        default=None,
        description="数据来源真实程度：real / synthetic / fallback",
    )
    data: Any = Field(
        default=None,
        description="处理后的内存中间表示对象（CanonicalRobot/Trimesh/...），供节点装配 ParsedItem 与校验引擎读取",
    )

    def has_errors(self) -> bool:
        """是否包含错误。"""
        return len(self.errors) > 0

    def has_warnings(self) -> bool:
        """是否包含警告。"""
        return len(self.warnings) > 0
