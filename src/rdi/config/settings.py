# src/rdi/config/settings.py
"""全局配置管理模块。

所有配置通过环境变量或 .env 文件注入，禁止在代码中硬编码
API key、路径或 URL。
"""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """全局配置，从环境变量或 .env 文件加载。

    优先级：环境变量 > .env 文件 > 默认值。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ─── 千问模型配置 ───
    qwen_api_key: str = Field(
        default="",
        description="阿里云百炼平台 API Key",
    )
    qwen_model: str = Field(
        default="qwen-plus",
        description="千问模型名称",
    )
    qwen_embedding_model: str = Field(
        default="text-embedding-v3",
        description="Embedding 模型",
    )
    qwen_max_retries: int = Field(
        default=3,
        description="LLM 调用最大重试次数",
    )
    qwen_temperature: float = Field(
        default=0.3,
        description="LLM 生成温度，目标解析用低温度",
    )

    # ─── 数据源配置 ───
    github_token: str = Field(
        default="",
        description="GitHub API Token",
    )
    ieee_api_key: str = Field(
        default="",
        description="IEEE Xplore API Key",
    )
    adapter_timeout: float = Field(
        default=30.0,
        description="HTTP 请求超时秒数",
    )
    adapter_max_retry: int = Field(
        default=3,
        description="Adapter 最大重试次数",
    )
    adapter_rate_limit: int = Field(
        default=10,
        description="每秒最大并发请求数",
    )
    adapter_cache_ttl: int = Field(
        default=3600,
        description="缓存 TTL 秒数",
    )

    # ─── ChromaDB 配置 ───
    chromadb_path: str = Field(
        default="./data/experience_db",
        description="ChromaDB 持久化路径",
    )

    # ─── 输出配置 ───
    output_dir: str = Field(
        default="./data/output_packages",
        description="数据包输出目录",
    )

    # ─── 日志配置 ───
    log_level: str = Field(
        default="INFO",
        description="日志级别",
    )
    log_format: str = Field(
        default="json",
        description="日志格式：json 或 console",
    )


# 全局单例
settings = Settings()
