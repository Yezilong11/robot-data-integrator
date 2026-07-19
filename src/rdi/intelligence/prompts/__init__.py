# src/rdi/intelligence/prompts/__init__.py
"""Intelligence Prompt 模板包。"""

from .goal_parsing import (
    GOAL_PARSING_SYSTEM,
    GOAL_PARSING_USER_TEMPLATE,
    build_goal_parsing_prompt,
)

__all__ = [
    "GOAL_PARSING_SYSTEM",
    "GOAL_PARSING_USER_TEMPLATE",
    "build_goal_parsing_prompt",
]
