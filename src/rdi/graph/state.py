# src/rdi/graph/state.py
"""LangGraph 全局状态定义。

所有节点读写同一个 State 对象，每个字段有明确类型和默认值。
关键原则：所有字段必须可序列化（支持 Checkpoint 持久化）。
"""

import operator
from typing import Annotated, Any, TypedDict

from rdi.models import (
    DataReq,
    GoalSpec,
    MissingItem,
    PackageManifest,
    ParsedItem,
    RetrievalError,
    RetrievalResult,
    ValIssue,
)


class SystemState(TypedDict, total=False):
    """全局状态，按功能分组。

    total=False 表示所有字段可选，节点只修改自己负责的字段。
    所有字段必须可 JSON 序列化（支持 LangGraph Checkpoint）。
    """

    # ─── 目标解析阶段（parse_goal 节点写入） ───
    user_goal: str  # 用户输入的原始目标描述
    paper_pdf: bytes  # 上传的论文 PDF 原始数据
    parsed_goal: GoalSpec  # LLM 解析后的结构化目标
    data_requirements: list[DataReq]  # 拆解后的数据需求清单

    # ─── 数据查找阶段（retrieve_data 节点写入） ───
    retrieval_results: dict[str, RetrievalResult]  # key=req_id
    retrieval_errors: list[RetrievalError]  # 失败记录列表

    # ─── 解析标准化阶段（parse_and_convert 节点写入） ───
    parsed_data: dict[str, ParsedItem]  # key=req_id，标准化后的数据
    # last-wins：validate 每轮全量重算该字段，若用 operator.add 会在多轮修订循环中重复累积
    validation_issues: list[ValIssue]  # 质量校验发现的问题
    runtime_check: dict[str, Any]  # SIM_CONFIG 的 MuJoCo 运行时验证结果（validate 节点写入）

    # ─── 整合输出阶段（assemble_package 节点写入） ───
    experiment_package: PackageManifest  # 最终数据包清单
    missing_items: list[MissingItem]  # 未找到的项 + 替代建议

    # ─── 用户审查阶段（human_review 节点写入） ───
    review_decision: str  # "satisfied" / "revised" / "unsatisfied"
    user_feedback: list[str]  # 用户反馈记录
    revised_goal: str | None  # revised 反馈转换后的修正目标描述
    query_cache: dict[str, str]  # 查询关键词压缩缓存（key=description hash，value=压缩后关键词）
    revision_history: list[
        dict[str, Any]
    ]  # 修订记录（revision 序号/decision/feedback/revised_goal/timestamp，human_review 追加，assemble 写入 manifest）
    interrupt_review: bool  # 真实流程是否在 human_review 前中断等待用户决策
    review_iteration: int  # 用户审查/修订轮次（独立于 validate 的 validate_iteration）
    local_files: dict[str, str]  # req_id → 本地文件路径（前端注入，跳过外部检索）

    # ─── 元数据（各节点共享） ───
    iteration_count: int  # 历史字段，保留兼容；validate 使用 validate_iteration
    validate_iteration: int  # validate 重试轮次
    provenance: Annotated[
        list[str], operator.add
    ]  # 数据溯源日志（时间戳 + 操作描述），累积各节点溯源日志
    errors: Annotated[list[str], operator.add]  # 累积的错误信息，不被后序节点清空
    run_id: (
        str  # 本次运行的唯一标识（时间戳-随机短串），流程入口注入；未注入时为空串（兼容单跑/测试）
    )
    retry_req_ids: Annotated[
        list[str], operator.add
    ]  # 需重试/重跑的 req_id（human_review 追加，retrieve_data 只处理这些 + 新需求）
