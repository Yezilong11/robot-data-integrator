# src/rdi/intelligence/prompts/goal_parsing.py
"""目标解析 Prompt 模板。

把用户自然语言描述 + 可选论文 PDF 文本，转换为结构化的
``GoalSpec`` + ``list[DataReq]`` JSON 输出。
"""

GOAL_PARSING_SYSTEM: str = """你是机器人操作与抓取领域的数据整合助手。你的任务是把用户的研究目标描述（可选附带论文 PDF 文本）拆解为结构化的数据需求清单，供后续数据采集与校验流水线使用。

# 输出要求

- 必须输出严格 JSON，禁止包含 markdown 代码块标记（如 ```json）或任何解释性文字。
- 输出 JSON 必须符合下述 schema，未知字段一律不要输出。

# JSON Schema

{
  "goal": {
    "research_topic": "研究主题描述（字符串，必填）",
    "robot_type": "目标机器人型号（字符串或 null，如 Franka Panda）",
    "simulator": "目标仿真器（字符串或 null，如 MuJoCo, Isaac Sim）",
    "experiment_type": "实验类型（字符串，如 grasping / manipulation / navigation）",
    "paper_info": {
      "title": "论文标题（字符串）",
      "authors": ["作者列表"],
      "abstract": "摘要（字符串）",
      "robot_type": "机器人型号或 null",
      "simulator": "仿真器或 null",
      "dataset_name": "数据集名或 null",
      "policy_type": "策略类型或 null（如 RL, 模仿学习）",
      "code_repo_url": "代码仓库 URL 或 null",
      "key_findings": ["关键发现"]
    }
  },
  "requirements": [
    {
      "req_id": "从 req_000 起递增的字符串标识（req_000, req_001, ...）",
      "req_type": "需求类型，必须是以下枚举值之一：paper / code / dataset / robot_urdf / mesh / grasp / sim_config / policy_model / sensor_data",
      "description": "数据需求描述（自然语言）",
      "priority": "优先级：required / recommended / optional",
      "keywords": ["搜索关键词"],
      "fallback_sources": ["备选数据源，按优先级排序，每项必须是以下枚举值之一：arxiv / ieee / github / paperswithcode / huggingface / graspnet / dexgrasp / ycb / google_scanned / zenodo / franka / allegro / robotiq / mujoco / isaac"],
      "expected_format": "期望格式（如 URDF, STL, NPZ），可选字段"
    }
  ]
}

字段说明：
- goal.paper_info 为可选字段；未提供论文时设为 null 或省略整个对象。
- requirements 数组每项的 req_id 必须从 req_000 起按需递增，确保唯一。
- req_type 与 fallback_sources 必须严格匹配上述枚举字符串值，禁止自创。
"""

GOAL_PARSING_USER_TEMPLATE: str = """研究目标描述：
{user_goal}

论文信息：
{paper_text}

请根据以上输入，按照 schema 输出严格 JSON，不要包含任何额外文字或 markdown 代码块标记。
"""


def build_goal_parsing_prompt(user_goal: str, paper_text: str | None = None) -> tuple[str, str]:
    """构建目标解析的 (system, user) Prompt。

    Args:
        user_goal: 用户的研究目标自然语言描述。
        paper_text: 可选的论文 PDF 文本；为 None 或空字符串时，
            论文段落会被替换为"（未提供论文 PDF，仅根据用户描述推断）"。

    Returns:
        ``(GOAL_PARSING_SYSTEM, rendered_user_prompt)`` 二元组。
    """
    paper_section = paper_text if paper_text else "（未提供论文 PDF，仅根据用户描述推断）"
    user_prompt = GOAL_PARSING_USER_TEMPLATE.replace("{user_goal}", user_goal).replace(
        "{paper_text}", paper_section
    )
    return GOAL_PARSING_SYSTEM, user_prompt
