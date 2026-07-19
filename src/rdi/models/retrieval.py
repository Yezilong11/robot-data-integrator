# src/rdi/models/retrieval.py
"""数据查找结果模型。

包含从数据源搜索和获取数据的相关结构。
"""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .common import DataSource


class SearchResult(BaseModel):
    """单个数据源的搜索结果。"""

    model_config = ConfigDict(extra="forbid")

    item_id: str = Field(description="数据项 ID（如 arxiv_id、repo 全名）")
    title: str = Field(description="标题")
    source: DataSource = Field(description="数据源")
    url: str = Field(default="", description="原始 URL")
    pdf_url: str | None = Field(default=None, description="PDF 链接（如有）")
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="额外元数据（作者、摘要、stars 等）",
    )


class RawData(BaseModel):
    """从数据源获取的原始数据。"""

    model_config = ConfigDict(extra="forbid")

    source: DataSource = Field(description="数据源")
    item_id: str = Field(description="数据项 ID")
    format: str = Field(description="原始格式（如 pdf, zip, urdf, stl）")
    data: bytes = Field(description="原始数据二进制内容")
    url: str = Field(default="", description="获取来源 URL")
    retrieved_at: datetime = Field(default_factory=datetime.now, description="获取时间")
    size_bytes: int = Field(default=0, description="数据大小（字节）")


class RetrievalResult(BaseModel):
    """单个数据需求的查找结果。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    data: RawData | None = Field(default=None, description="获取到的原始数据")
    status: str = Field(
        default="success",
        description="success / missing / fallback / error",
    )
    source: DataSource | None = Field(default=None, description="实际使用的数据源")
    is_fallback: bool = Field(default=False, description="是否使用了备选源")
    search_results: list[SearchResult] = Field(
        default_factory=list,
        description="搜索到的候选列表（按相关性排序）",
    )
    error_message: str = Field(default="", description="失败原因")
    elapsed_seconds: float = Field(default=0.0, description="耗时（秒）")


class RetrievalError(BaseModel):
    """单次查找失败记录。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="关联的需求 ID")
    source: DataSource = Field(description="尝试的数据源")
    error_type: str = Field(
        description="错误类型：timeout / rate_limit / not_found / auth / unknown"
    )
    error_message: str = Field(description="错误详情")
    timestamp: datetime = Field(default_factory=datetime.now, description="发生时间")
