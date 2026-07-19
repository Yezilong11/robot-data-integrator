# src/rdi/intelligence/__init__.py
"""智能决策层：LLM 客户端与 Prompt 模板。"""

from .client import LLMClient
from .prompts import build_goal_parsing_prompt

__all__ = ["LLMClient", "build_goal_parsing_prompt"]
