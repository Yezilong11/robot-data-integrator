# src/rdi/graph/nodes/parse_goal.py
"""目标解析节点：自然语言 + PDF → 结构化数据需求清单。

系统入口节点，调用 LLMClient 把 ``user_goal`` + 可选论文 PDF 文本拆解为
``GoalSpec`` + ``list[DataReq]``。LLM 不可用时降级返回占位数据，保证流水线
继续运行而非崩溃。
"""

import logging
import re
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

_logger = logging.getLogger(__name__)

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


# 强制映射关键词表（不区分大小写）。命中即覆盖 LLM 输出的 req_type。
# 强关键词（格式后缀 / 专有名词）精确匹配，对任何 req_type 都生效；
# 弱关键词（通用词）仅在 req_type 为非具体类型（code / dataset / unknown）时兜底，
# 避免误伤已正确分类的具体需求（如 grasp 需求的描述里出现 "robot"）。
_STRONG_TYPE_KEYWORDS: dict[DataReqType, tuple[str, ...]] = {
    # 检索容器类目标最优先：描述含仓库/数据集专词时先判 CODE/DATASET。
    # Day2 回归：LLM 把 "retrieve robot grasp dataset" 判为 GRASP 且配 expected_format=npz 时，
    # GRASP 强词 npz 会抢先命中；把 CODE/DATASET 提到最前，容器专词优先于数据格式词。
    DataReqType.CODE: (
        "开源仓库",
        "代码仓库",
        "源代码",
        "开源代码",
        "github",
        "codebase",
        "repository",
        "repo",
    ),
    DataReqType.DATASET: ("dataset", "数据集"),
    DataReqType.ROBOT_URDF: ("urdf", "xacro"),
    DataReqType.MESH: ("mesh", "3d model", "obj", "stl", "ply", "dae", "glb"),
    DataReqType.GRASP: (
        "grasp pose",
        "grasping pose",
        "grasp data",
        "grasp_label",
        "npz",
        "pkl",
        "抓取姿态",
    ),
    DataReqType.SIM_CONFIG: (
        "mujoco",
        "isaac",
        "mjcf",
        "xml",
        "simulation scene",
        "sim config",
        "仿真场景",
        "仿真配置",
    ),
    # D2: 新增四类强关键词。中文用具体词避开泛词误伤：
    # "配置" 会命中 SIM_CONFIG 的"仿真场景配置"，故 ROBOT_CONFIG 只收英文具体词。
    DataReqType.CAMERA_CALIB: (
        "camera calibration",
        "calibration",
        "calib",
        "intrinsics",
        "extrinsics",
        "标定",
        "内参",
        "外参",
    ),
    DataReqType.TEACHING_TRAJECTORY: (
        "teaching trajectory",
        "teaching",
        "demonstration",
        "示教轨迹",
        "示教",
    ),
    DataReqType.ROBOT_CONFIG: (
        "robot config",
        "robot_config",
        "robot-config",
        "config.yaml",
        "yaml config",
    ),
    DataReqType.BENCHMARK_TASK: ("benchmark", "基准测试", "基准任务"),
}

_WEAK_TYPE_KEYWORDS: dict[DataReqType, tuple[str, ...]] = {
    DataReqType.ROBOT_URDF: ("robot", "robots", "机器人"),
    DataReqType.MESH: ("模型", "物体"),
    DataReqType.GRASP: ("grasp", "grasping", "抓取"),
    DataReqType.SIM_CONFIG: ("simulation", "仿真"),
}

# 仅这几种"非具体"类型允许用弱关键词兜底；paper / policy_model / sensor_data 等
# 具体类型描述里常出现 robot / 抓取 等通用词，不应被强转。
_WEAK_ELIGIBLE_TYPES: frozenset[DataReqType] = frozenset(
    {DataReqType.CODE, DataReqType.DATASET, DataReqType.UNKNOWN}
)

# C1: 中文抓取语境物体名提取模式（先"X 的抓取标注"语序，再"抓取标注：X"语序）
_OBJECT_NAME_PATTERNS: tuple[str, ...] = (
    r"([\u4e00-\u9fa5a-zA-Z][\u4e00-\u9fa5a-zA-Z0-9_-]*)\s*的\s*抓取(?:标注|姿态|数据)?",
    r"抓取(?:标注|姿态|数据)?\s*[:：]?\s*([\u4e00-\u9fa5a-zA-Z][\u4e00-\u9fa5a-zA-Z0-9_-]*)",
)
# 语序二可能误捕获的泛化词（如"抓取数据"中的"数据"不是物体名）
_OBJECT_NAME_STOPWORDS: frozenset[str] = frozenset(
    {"数据", "文件", "标注", "姿态", "模型", "网格", "物体", "场景", "配置", "任务", "信息"}
)
# C1: YCB 常见物体英文名小列表（覆盖测试场景，不做全表）
_YCB_COMMON_OBJECT_NAMES: tuple[str, ...] = (
    "banana",
    "apple",
    "mug",
    "bowl",
    "cracker box",
    "sugar box",
    "tomato soup can",
    "master chef can",
    "mustard bottle",
    "tuna fish can",
)


def _kw_in(text: str, keyword: str) -> bool:
    """不区分大小写的关键词匹配：中文按子串，英文按整词边界。

    ``robot`` 只匹配独立单词，避免把 "Robotiq" / "robotics" 误判为 ROBOT_URDF；
    ``obj`` 只匹配扩展名，避免命中 "objects"。
    """
    if any(ord(c) > 127 for c in keyword):
        return keyword in text
    return re.search(rf"\b{re.escape(keyword)}\b", text) is not None


def _normalize_datareq(req: DataReq) -> DataReq:
    """基于 expected_format 与 description 关键词修正误分类的 req_type。

    LLM 容易把真实机器人数据识别为通用的 code/dataset，或给出错误的具体类型；
    强关键词（格式后缀 / 专有名词）命中时无条件覆盖，弱关键词（通用词）仅在
    req_type 为 code / dataset / unknown 时兜底，保证正常场景不误伤。
    完全无法识别时标记 ``DataReqType.UNKNOWN`` 并记录 warning。
    """
    text = f"{req.description} {req.expected_format or ''}".lower()
    cur = req.req_type

    for typ, keywords in _STRONG_TYPE_KEYWORDS.items():
        if any(_kw_in(text, k) for k in keywords):
            return req.model_copy(update={"req_type": typ})

    if cur in _WEAK_ELIGIBLE_TYPES:
        for typ, keywords in _WEAK_TYPE_KEYWORDS.items():
            if any(_kw_in(text, k) for k in keywords):
                return req.model_copy(update={"req_type": typ})
        if cur == DataReqType.UNKNOWN:
            _logger.warning(
                "parse_goal: 无法识别数据需求类型，req_id=%s 标记为 UNKNOWN", req.req_id
            )

    return req


def _extract_object_name_from_text(text: str) -> str:
    """从描述文本提取目标物体名；未识别返回空串。

    规则（按优先级）：
    1. YCB 风格物体 id（如 ``011_banana``）；
    2. 中文抓取语境名词（"banana 的抓取标注" / "抓取标注：banana"），
       排除"数据/文件"等泛化词；
    3. 英文 grasp 语境（如 "grasp pose of banana"）；
    4. YCB 常见物体英文名小列表。
    """
    m = re.search(r"\b(\d{3}_[a-z0-9_]+)\b", text)
    if m:
        return m.group(1)
    for pattern in _OBJECT_NAME_PATTERNS:
        m = re.search(pattern, text)
        if m and m.group(1).lower() not in _OBJECT_NAME_STOPWORDS:
            return m.group(1)
    m = re.search(
        r"grasp(?:ing)? (?:pose|data|annotation)?(?:s)? (?:of|for|on)?\s*([a-z0-9_-]+)",
        text,
        re.IGNORECASE,
    )
    if m:
        return m.group(1)
    lower = text.lower()
    for name in _YCB_COMMON_OBJECT_NAMES:
        if re.search(rf"\b{re.escape(name)}\b", lower):
            return name
    return ""


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
    requirements = [_normalize_datareq(req) for req in requirements]

    # C1: 对 GRASP/MESH 需求从描述文本补充 object_name（先 normalize 再填充，
    # 保证 req_type 已修正为 GRASP/MESH 后才会触发；LLM 已填的 object_name 不覆盖）
    requirements = [
        req.model_copy(
            update={
                "object_name": _extract_object_name_from_text(
                    f"{req.description} {req.expected_format or ''}"
                )
            }
        )
        if req.req_type in (DataReqType.GRASP, DataReqType.MESH)
        and not (getattr(req, "object_name", "") or "").strip()
        else req
        for req in requirements
    ]

    return {
        "parsed_goal": result.goal,
        "data_requirements": requirements,
        "provenance": [
            f"[{now}] parse_goal: LLM 解析成功，生成 {len(requirements)} 条数据需求"
            f" (model={settings.llm_model})"
        ],
    }
