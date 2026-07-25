# src/rdi/adapters/github.py
"""GitHub 代码与模型源 Adapter。

文档：https://docs.github.com/en/rest
速率限制：认证用户 5000次/小时，未认证 60次/小时
建议配置 GITHUB_TOKEN 环境变量。
"""

import base64
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class GitHubAdapter(BaseAdapter):
    """GitHub API Adapter。

    提供：
    - search: 搜索仓库（按 stars 排序）
    - fetch: 获取仓库 README
    - fetch_releases: 获取 Release 资产（模型权重）
    - fetch_file: 下载仓库指定文件
    """

    source = DataSource.GITHUB

    def __init__(self) -> None:
        super().__init__(
            base_url="https://api.github.com",
            rate_limit=30,
        )
        self.token = settings.github_token

    @property
    def headers(self) -> dict[str, str]:
        """请求头，含 GitHub API 版本和可选 Token。"""
        h: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            h["Authorization"] = f"token {self.token}"
        return h

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 GitHub 仓库。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表，按 stars 降序
        """
        data = await self._request(
            "GET",
            "/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc"},
            headers=self.headers,
        )
        return [
            SearchResult(
                item_id=repo["full_name"],
                title=repo["name"],
                source=DataSource.GITHUB,
                url=repo["html_url"],
                metadata={
                    "stars": repo["stargazers_count"],
                    "description": repo.get("description", ""),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                },
            )
            for repo in data.get("items", [])
        ]

    async def fetch(self, repo_name: str) -> RawData:
        """获取仓库的 README 内容。

        Args:
            repo_name: 仓库全名（如 "NVlabs/6-DOF-GraspNet"）

        Returns:
            RawData 包含 README markdown 二进制数据

        Raises:
            AdapterError: 获取失败
        """
        data = await self._request(
            "GET",
            f"/repos/{repo_name}/readme",
            headers=self.headers,
        )
        readme_bytes = base64.b64decode(data["content"])
        return RawData(
            source=DataSource.GITHUB,
            item_id=repo_name,
            format="markdown",
            data=readme_bytes,
            url=data.get("html_url", ""),
        )

    async def fetch_releases(self, repo_name: str) -> list[dict[str, Any]]:
        """获取 Release 资产（模型权重、预训练文件）。

        Args:
            repo_name: 仓库全名

        Returns:
            资产列表，每个包含 release_tag, name, url, size
        """
        data = await self._request(
            "GET",
            f"/repos/{repo_name}/releases",
            headers=self.headers,
        )
        assets: list[dict[str, Any]] = []
        for release in data:
            for asset in release.get("assets", []):
                assets.append(
                    {
                        "release_tag": release["tag_name"],
                        "name": asset["name"],
                        "url": asset["browser_download_url"],
                        "size": asset["size"],
                    }
                )
        return assets

    async def fetch_file(self, repo_name: str, file_path: str, ref: str = "main") -> bytes:
        """下载仓库中的指定文件。

        Args:
            repo_name: 仓库全名
            file_path: 文件路径（相对于仓库根目录）
            ref: Git 引用（分支/标签），默认 main

        Returns:
            文件二进制内容
        """
        url = f"https://raw.githubusercontent.com/{repo_name}/{ref}/{file_path}"
        return await self._download_bytes(url)
