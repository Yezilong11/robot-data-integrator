# src/rdi/logging.py
"""全局结构化日志配置（Task 16 / E2）。

LOG_LEVEL / LOG_FORMAT 从 settings 读取并接线到 structlog（项目既有依赖）：
- ``log_format=json``（默认）→ 单行 JSON，便于机器解析；
- ``log_format=console`` → 人类可读 key=value 输出。

底层走标准库 logging（``structlog.stdlib`` 后端），因此 pytest 的 caplog
能直接断言记录；``configure_logging`` 幂等，可在入口（builder.build_graph）
与测试中反复调用。
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import structlog

from rdi.config.settings import settings

_LEVEL_NAMES = ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG", "NOTSET")


def configure_logging(level: str | None = None, fmt: str | None = None) -> None:
    """按 settings.log_level / log_format 配置全局日志（幂等，可重复调用）。

    Args:
        level: 日志级别名，缺省读 ``settings.log_level``（如 "INFO"）。
        fmt: 输出格式，json 或 console，缺省读 ``settings.log_format``。
    """
    level_name = (level or settings.log_level or "INFO").upper()
    fmt_name = (fmt or settings.log_format or "json").lower()
    if level_name not in _LEVEL_NAMES:
        level_name = "INFO"
    level_num = getattr(logging, level_name, logging.INFO)

    if fmt_name == "json":
        renderer: Any = structlog.processors.JSONRenderer(ensure_ascii=False)
    else:
        renderer = structlog.dev.ConsoleRenderer()

    # root 无 handler 时挂一个 stderr handler，保证脱离 pytest 环境也有输出
    root = logging.getLogger()
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        handler = logging.StreamHandler(sys.stderr)
        handler.setFormatter(logging.Formatter("%(message)s"))
        root.addHandler(handler)
    root.setLevel(level_num)

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            renderer,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> Any:
    """返回结构化日志器。

    底层固定为标准库 logger，事件经 structlog 处理器链渲染后由 logging 输出，
    因此 caplog 可捕获、JSON/console 渲染由 ``configure_logging`` 控制。
    """
    return structlog.stdlib.get_logger(name)
