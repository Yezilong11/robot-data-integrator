# src/rdi/graph/nodes/parse_goal.py
"""目标解析节点：自然语言 + PDF → 结构化数据需求清单。

系统入口节点，调用 LLMClient 把 ``user_goal`` + 可选论文 PDF 文本拆解为
``GoalSpec`` + ``list[DataReq]``。LLM 不可用时降级返回占位数据，保证流水线
继续运行而非崩溃。
"""

from datetime import datetime
from typing import Any

import fitz  # PyMuPDF
from pydantic import BaseModel, Field

from rdi.config import settings
from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.graph.state import SystemState
from rdi.intelligence import LLMClient
from rdi.intelligence.prompts import build_goal_parsing_prompt
from rdi.models import DataReq, DataReqType, GoalSpec

# ponytail: 临时用 PyMuPDF 直接抽取 PDF 文本，等 D 工程师的 PDFParseSkill 就绪后替换
_PDF_TEXT_MAX_CHARS = 8000


class _GoalParsingResult(BaseModel):
    """LLM 目标解析的输出结构（内部使用）。

    ponytail: 单次 LLM 调用同时返回 goal + requirements，减少 token 消耗与往返。
    """

    goal: GoalSpec = Field(description="结构化研究目标")
    requirements: list[DataReq] = Field(default_factory=list, description="数据需求清单")


# 模块级懒加载 LLMClient 单例，便于测试 monkeypatch
_llm_client: LLMClient | None = None


def _get_llm_client() -> LLMClient:
    """返回缓存的 LLMClient 单例；首次调用时创建。"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def _extract_paper_text(paper_pdf: bytes | None) -> str | None:
    """从 PDF bytes 抽取纯文本。

    Args:
        paper_pdf: PDF 原始字节；为空或非合法 PDF 返回 None。

    Returns:
        抽取的纯文本；超过 ``_PDF_TEXT_MAX_CHARS`` 字符时截断并加标记。
        抽取失败、空内容均返回 None。
    """
    if not paper_pdf:
        return None
    try:
        with fitz.open(stream=paper_pdf, filetype="pdf") as doc:
            text = "".join(page.get_text() for page in doc)
    except Exception:
        # ponytail: 任何抽取异常都视为"无可用论文文本"，让上层走无论文路径
        return None
    if not text.strip():
        return None
    if len(text) > _PDF_TEXT_MAX_CHARS:
        return text[:_PDF_TEXT_MAX_CHARS] + "...[截断]"
    return text


def _correct_req_type(req: DataReq) -> DataReq:
    """基于 expected_format 与 description 关键词修正误分类的 req_type。

    LLM 容易把真实机器人数据识别为通用的 code/dataset；
    当显式格式或描述关键词命中时，强制映射到更具体的类型。
    """
    desc = req.description.lower()
    fmt = (req.expected_format or "").lower()
    text = f"{desc} {fmt}"
    cur = req.req_type

    if cur not in (DataReqType.CODE, DataReqType.DATASET):
        return req

    # 机器人描述文件
    if "urdf" in text or "xacro" in text:
        return req.model_copy(update={"req_type": DataReqType.ROBOT_URDF})

    # 抓取姿态数据
    grasp_keywords = ("grasp pose", "grasping pose", "grasp data", "grasp_label", "抓取姿态")
    if any(k in text for k in grasp_keywords) or fmt in ("npz", "pkl"):
        return req.model_copy(update={"req_type": DataReqType.GRASP})

    # 仿真场景配置
    sim_keywords = (
        "mujoco",
        "isaac",
        "simulation scene",
        "sim config",
        "mjcf",
        "仿真场景",
        "仿真配置",
    )
    if any(k in text for k in sim_keywords) or fmt in ("xml", "mjcf"):
        return req.model_copy(update={"req_type": DataReqType.SIM_CONFIG})

    # 物体三维模型
    mesh_keywords = (
        "mesh",
        "3d model",
        "obj",
        "stl",
        "ply",
        "dae",
        "glb",
        "三维模型",
        "网格",
    )
    if any(k in text for k in mesh_keywords) or fmt in ("obj", "stl", "ply", "dae", "glb"):
        return req.model_copy(update={"req_type": DataReqType.MESH})

    return req


def node_parse_goal(state: SystemState) -> dict[str, Any]:
    """目标解析节点：调用 LLM 把 user_goal + paper_pdf 转换为结构化数据需求。

    流程：
        1. 从 state 取 ``user_goal`` 和 ``paper_pdf``；
        2. 用 PyMuPDF 抽取 PDF 纯文本（失败则视为无论文）；
        3. 调 ``build_goal_parsing_prompt`` 构造 (system, user) Prompt；
        4. 调 ``LLMClient.call_structured`` 一次性拿到 goal + requirements；
        5. LLM 失败时降级返回占位 GoalSpec + 空 requirements + 错误信息。

    Returns:
        更新 state 的字段：``parsed_goal`` / ``data_requirements`` /
        ``provenance`` / 可选 ``errors``。
    """
    user_goal = state.get("user_goal", "")
    paper_pdf = state.get("paper_pdf")
    paper_text = _extract_paper_text(paper_pdf)

    system_prompt, user_prompt = build_goal_parsing_prompt(user_goal, paper_text)
    now = datetime.now().isoformat()

    try:
        client = _get_llm_client()
        result = client.call_structured(
            prompt=user_prompt,
            schema=_GoalParsingResult,
            system=system_prompt,
        )
    except (LLMUnavailableError, LLMParseError) as e:
        # 降级：返回占位数据 + 错误信息，不抛异常，保证流水线继续
        return {
            "parsed_goal": GoalSpec(research_topic=user_goal or "未知目标"),
            "data_requirements": [],
            "errors": [f"parse_goal 降级: {type(e).__name__}: {e}"],
            "provenance": [
                f"[{now}] parse_goal: LLM 调用失败，降级返回占位数据 ({type(e).__name__})"
            ],
        }

    # 防御性：LLM 返回的 req_id 可能不规范，统一重编号为 req_XXX
    requirements = [
        req.model_copy(update={"req_id": f"req_{i:03d}"})
        for i, req in enumerate(result.requirements)
    ]

    # 后处理：根据 expected_format / description 关键词修正误分类
    requirements = [_correct_req_type(req) for req in requirements]

    return {
        "parsed_goal": result.goal,
        "data_requirements": requirements,
        "provenance": [
            f"[{now}] parse_goal: LLM 解析成功，生成 {len(requirements)} 条数据需求"
            f" (model={settings.llm_model})"
        ],
    }
