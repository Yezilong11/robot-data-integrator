# src/rdi/models/goal.py
"""目标解析与数据需求模型。"""

from typing import Any

from pydantic import BaseModel, Field

from .common import DataReqType, Priority


class GoalSpec(BaseModel):
    """用户研究目标的结构化表示。"""

    raw_input: str = Field(description="用户原始输入文本")
    research_question: str = Field(description="提炼的研究问题")
    domain: str = Field(default="", description="研究领域")
    sub_tasks: list[str] = Field(
        default_factory=list, description="拆解的子任务"
    )
    paper_references: list[str] = Field(
        default_factory=list, description="引用的论文ID"
    )


class DataReq(BaseModel):
    """单条数据需求。"""

    req_id: str = Field(description="需求唯一ID")
    req_type: DataReqType = Field(description="数据类型")
    description: str = Field(description="需求描述")
    priority: Priority = Field(default=Priority.REQUIRED)
    keywords: list[str] = Field(default_factory=list, description="搜索关键词")
    constraints: dict[str, Any] = Field(
        default_factory=dict, description="约束条件"
    )
