# src/rdi/intelligence/schemas.py
"""LLM 决策层结构化输出 Schema（pydantic v2）。

四个决策点（检索规划 / 语义统一 / 质量解释 / 审查建议）的输出结构。
所有模型均可 JSON 序列化，写入 SystemState 后支持 LangGraph Checkpoint/msgpack
持久化（不依赖 graph，避免循环导入）。
"""

from typing import Literal

from pydantic import BaseModel, Field


class RetrievalPlan(BaseModel):
    """检索策略规划：为单条数据需求生成搜索词组合与源偏好。"""

    queries: list[str] = Field(description="搜索词组合（含英文关键词），用于在数据源中检索")
    preferred_sources: list[str] = Field(
        description="源偏好（DataSource.value 字符串），按优先级排序"
    )
    reason: str = Field(description="为什么这样检索的理由")
    confidence: float = Field(description="该检索规划的置信度（0~1）")


class SemanticConvention(BaseModel):
    """语义约定：未知数据集的字段映射、旋转表示、坐标系 origin、单位。"""

    dataset_name: str = Field(description="数据集名称")
    semantic_type: str = Field(description="语义类型，如 grasp_pose / robot_urdf / mesh")
    rotation: Literal["matrix", "quaternion_wxyz", "quaternion_xyzw", "euler", "unknown"] = Field(
        description="旋转表示方式"
    )
    origin: Literal["camera", "object_center", "world", "unknown"] = Field(description="坐标系原点")
    unit: Literal["meter", "millimeter", "unknown"] = Field(description="长度单位")
    field_map: dict[str, str] = Field(description="源字段名 → 标准字段名的映射")
    confidence: float = Field(description="该语义约定的置信度（0~1）")
    needs_human_review: bool = Field(default=False, description="是否需要人工复核")


class QualityExplanation(BaseModel):
    """质量报告的自然语言解释。"""

    summary: str = Field(description="整体质量概述")
    strengths: list[str] = Field(description="数据优势列表")
    risks: list[str] = Field(description="潜在风险列表")
    recommendations: list[str] = Field(description="改进建议列表")
    usage_guidance: str = Field(description="如何安全使用这些数据的指引")
    confidence: float = Field(description="该解释的置信度（0~1）")


class ReviewSuggestions(BaseModel):
    """审查建议：基于缺失项 / 校验问题的综合判断。"""

    verdict: Literal["satisfied", "revised", "unsatisfied"] = Field(description="审查结论")
    issues: list[str] = Field(description="逐项问题清单")
    rationale: str = Field(description="做出该结论的理由")
    confidence: float = Field(description="该建议的置信度（0~1）")
