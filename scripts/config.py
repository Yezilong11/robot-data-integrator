"""
脚本配置模块

功能：
- 从环境变量或 .env 文件加载配置
- 统一管理 API Key、网络参数、目录路径

作者：挑战杯团队
创建日期：2026-07-14
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# 加载 .env 文件（从项目根目录）
_project_root = Path(__file__).resolve().parent.parent
load_dotenv(_project_root / ".env")


class Config:
    """全局脚本配置。"""

    # ─── API Keys ───
    QWEN_API_KEY: str = os.getenv("QWEN_API_KEY", "")
    GITHUB_TOKEN: str = os.getenv("GITHUB_TOKEN", "")
    IEEE_API_KEY: str = os.getenv("IEEE_API_KEY", "")

    # ─── 网络配置 ───
    ADAPTER_TIMEOUT: float = float(os.getenv("ADAPTER_TIMEOUT", "30.0"))
    ADAPTER_MAX_RETRY: int = int(os.getenv("ADAPTER_MAX_RETRY", "3"))
    ADAPTER_RATE_LIMIT: int = int(os.getenv("ADAPTER_RATE_LIMIT", "10"))

    # ─── 目录配置 ───
    PROJECT_ROOT: Path = _project_root
    DATA_DIR: Path = _project_root / "data" / "sources"
    REPORT_DIR: Path = _project_root / "data"

    # ─── 下载数量配置 ───
    ARXIV_PAPER_COUNT: int = int(os.getenv("ARXIV_PAPER_COUNT", "50"))
    GITHUB_REPO_COUNT: int = int(os.getenv("GITHUB_REPO_COUNT", "30"))
    HUGGINGFACE_MODEL_COUNT: int = int(os.getenv("HUGGINGFACE_MODEL_COUNT", "10"))
    ZENODO_RECORD_COUNT: int = int(os.getenv("ZENODO_RECORD_COUNT", "10"))
    IEEE_PAPER_COUNT: int = int(os.getenv("IEEE_PAPER_COUNT", "20"))

    # ─── GitHub API 配置 ───
    @property
    def github_headers(self) -> dict[str, str]:
        """GitHub API 请求头。"""
        headers = {"Accept": "application/vnd.github.v3+json"}
        if self.GITHUB_TOKEN:
            headers["Authorization"] = f"token {self.GITHUB_TOKEN}"
        return headers


config = Config()
