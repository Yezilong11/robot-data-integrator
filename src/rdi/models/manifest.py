# src/rdi/models/manifest.py
"""数据包 Manifest 模型。

最终输出数据包的完整清单，包含文件列表、质量报告和溯源日志。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ManifestFile(BaseModel):
    """Manifest 中单个文件记录。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    path: str = Field(description="相对于数据包根目录的路径")
    format: str = Field(description="标准化格式名")
    source_url: str = Field(description="原始来源 URL")
    retrieved_at: datetime = Field(description="获取时间")
    transformations: list[str] = Field(default_factory=list, description="转换步骤列表")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="置信度")
    completeness: float = Field(default=100.0, ge=0.0, le=100.0, description="完整度")
    data_source_quality: str = Field(
        default="unknown",
        description="数据来源真实程度：real / synthetic / fallback / unknown（未知来源默认 unknown，不再隐式标 fallback）",
    )
    is_fallback: bool = Field(default=False, description="是否使用了备选源（经 ParsedItem 从 RetrievalResult 透传）")
    file_size: int = Field(default=0, description="文件大小（字节）；引用未下载时为远端大小")
    downloaded: bool = Field(default=True, description="是否已下载到本地数据包")
    local_path: str = Field(
        default="",
        description="本地文件路径（相对于数据包根目录）；未下载为空字符串",
    )
    file_url: str = Field(default="", description="原始文件 URL（已下载为来源 URL；引用为远端 URL）")
    checksum_sha256: str = Field(default="", description="文件 SHA-256（小写 hex）；未计算或引用文件为空字符串")


class ManifestMissingItem(BaseModel):
    """Manifest 中缺失项记录。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    reason: str = Field(description="缺失原因")
    alternatives: list[str] = Field(default_factory=list, description="替代方案")


class QualityReport(BaseModel):
    """数据包质量报告。"""

    model_config = ConfigDict(extra="forbid")

    total_requirements: int = Field(default=0, description="总需求数")
    fulfilled: int = Field(default=0, description="已满足数")
    missing: int = Field(default=0, description="缺失数")
    validation_issues: int = Field(default=0, description="校验问题数")
    avg_confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="平均置信度")
    avg_completeness: float = Field(default=0.0, ge=0.0, le=100.0, description="平均完整度")


class PackageManifest(BaseModel):
    """完整的数据包清单。"""

    model_config = ConfigDict(extra="forbid")

    package_info: dict[str, str | int | float] = Field(
        description="包信息（goal, created_at, iteration 等）"
    )
    files: list[ManifestFile] = Field(default_factory=list, description="文件列表")
    missing_items: list[ManifestMissingItem] = Field(
        default_factory=list,
        description="缺失项列表",
    )
    quality_report: QualityReport = Field(
        default_factory=QualityReport,
        description="质量报告",
    )
    provenance_log: list[str] = Field(
        default_factory=list,
        description="溯源日志条目（每行一个时间戳记录）",
    )
    runtime_check: dict[str, Any] = Field(
        default_factory=dict,
        description="MuJoCo 一步仿真验证结果（status: passed/failed/skipped, detail 等）",
    )
    revision_history: list[dict[str, Any]] = Field(
        default_factory=list,
        description="human_review 触发的版本关联记录（revision, feedback, timestamp, package_id）",
    )
    output_dir: str = Field(description="数据包输出目录的绝对路径")
