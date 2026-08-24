# src/rdi/models/goal.py
"""目标解析与数据需求模型。

包含用户研究目标的结构化表示，以及拆解后的数据需求清单。
"""

from pydantic import BaseModel, ConfigDict, Field

from .common import DataReqType, DataSource, Priority


class PaperInfo(BaseModel):
    """从论文 PDF 中提取的关键信息。"""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="", description="论文标题")
    authors: list[str] = Field(default_factory=list, description="作者列表")
    abstract: str = Field(default="", description="摘要")
    robot_type: str | None = Field(default=None, description="机器人型号（如 Franka Panda）")
    simulator: str | None = Field(default=None, description="仿真器名称（如 MuJoCo, Isaac Sim）")
    dataset_name: str | None = Field(default=None, description="使用的数据集名称")
    policy_type: str | None = Field(default=None, description="策略类型（如 RL, 模仿学习）")
    code_repo_url: str | None = Field(default=None, description="代码仓库 URL")
    key_findings: list[str] = Field(default_factory=list, description="关键发现摘要")


class GoalSpec(BaseModel):
    """LLM 解析后的结构化目标规格。"""

    model_config = ConfigDict(extra="forbid")

    research_topic: str = Field(description="研究主题描述")
    robot_type: str | None = Field(default=None, description="目标机器人型号")
    simulator: str | None = Field(default=None, description="目标仿真器")
    experiment_type: str = Field(
        default="", description="实验类型（grasping / manipulation / navigation）"
    )
    paper_info: PaperInfo | None = Field(default=None, description="论文提取信息")


class DataReq(BaseModel):
    """单条数据需求。"""

    model_config = ConfigDict(extra="forbid")

    req_id: str = Field(description="唯一标识，格式: req_XXX")
    req_type: DataReqType = Field(description="数据类型")
    description: str = Field(description="数据需求描述（自然语言）")
    priority: Priority = Field(description="优先级")
    keywords: list[str] = Field(default_factory=list, description="搜索关键词")
    semantic_terms: list[str] = Field(
        default_factory=list,
        description="语义约束词（LLM 提炼，用于需求-内容语义匹配）",
    )
    fallback_sources: list[DataSource] = Field(
        default_factory=list,
        description="备选数据源列表（按优先级排序）",
    )
    expected_format: str | None = Field(
        default=None,
        description="期望的标准化格式（如 URDF, STL, NPZ）",
    )
    object_name: str = Field(
        default="",
        description="目标物体名称（从目标文本提取，供抓取/网格检索精确定位文件；空串表示未指定）",
    )
