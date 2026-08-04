# tests/unit/test_settings.py
"""Settings 模块冒烟测试。"""

import os
from unittest.mock import patch

from rdi.config.settings import Settings


def test_settings_defaults() -> None:
    """Settings 在未配置环境变量时应使用默认值。"""
    with patch.dict(os.environ, {}, clear=True):
        cfg = Settings(_env_file=None)
    assert cfg.llm_model == "qwen-plus"
    assert cfg.log_level == "INFO"
    assert cfg.adapter_timeout == 30.0
