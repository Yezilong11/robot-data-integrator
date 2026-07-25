# src/rdi/intelligence/__init__.py
"""智能决策层：LLM 客户端与 Prompt 模板。"""

from .client import LLMClient
from .embedding import EmbeddingClient, get_embedding
from .prompts import build_goal_parsing_prompt

__all__ = ["LLMClient", "EmbeddingClient", "get_embedding", "build_goal_parsing_prompt"]
