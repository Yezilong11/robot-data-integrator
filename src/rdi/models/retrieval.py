# src/rdi/models/retrieval.py
"""数据查找结果模型。"""

from typing import Any

from pydantic import BaseModel, Field

from .common import DataSource


class SearchResult(BaseModel):
    """单个数据源的搜索结果。"""

    item_id: str = Field(description="数据项ID（如arxiv_id、repo全名）")
    title: str = Field(description="标题")
    source: DataSource = Field(description="数据源")
    url: str = Field(default="", description="原始URL")
    pdf_url: str | None = Field(default=None, description="PDF链接")
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="额外元数据"
    )


class RawData(BaseModel):
    """从数据源获取的原始数据。"""

    source: DataSource
    item_id: str
    format: str = Field(description="原始格式")
    data: bytes = Field(description="原始数据内容")
    url: str = Field(default="", description="获取来源URL")


class RetrievalResult(BaseModel):
    """单个数据需求的查找结果。"""

    req_id: str = Field(description="关联的需求ID")
    data: RawData | None = Field(default=None, description="获取的数据")
    status: str = Field(
        default="success",
        description="success / missing / fallback / error",
    )
    source: DataSource | None = Field(default=None, description="实际使用的源")
    is_fallback: bool = Field(
        default=False, description="是否用了备选源"
    )
    search_results: list[SearchResult] = Field(
        default_factory=list, description="搜索到的候选列表"
    )
    error_message: str = Field(default="", description="失败原因")
    elapsed_seconds: float = Field(default=0.0, description="耗时秒数")


class RetrievalError(BaseModel):
    """查找失败记录。"""

    req_id: str
    source: DataSource
    error_type: str = Field(description="超时/限流/未找到/认证失败")
    error_message: str
    timestamp: str
