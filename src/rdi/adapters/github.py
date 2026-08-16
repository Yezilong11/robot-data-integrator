# src/rdi/adapters/github.py
"""GitHub 代码与模型源 Adapter。

文档：https://docs.github.com/en/rest
速率限制：认证用户 5000次/小时，未认证 60次/小时
建议配置 GITHUB_TOKEN 环境变量。
"""

import base64
import re
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
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

    async def fetch(self, repo_name: str, req_type: str | None = None) -> RawData:
        """获取仓库内容。

        - ROBOT_URDF 需求：从仓库文件树定位 ``.urdf`` 文件并下载（避免拿到 README
          markdown 导致类型错配）；无 URDF 时回退 README
        - 其他/默认：获取仓库 README 内容

        Args:
            repo_name: 仓库全名（如 "NVlabs/6-DOF-GraspNet"）
            req_type: 数据需求类型字符串（如 "ROBOT_URDF"），可空

        Returns:
            RawData 包含 README markdown 或 URDF 文件二进制数据

        Raises:
            AdapterError: 获取失败
        """
        if str(req_type).lower() == "robot_urdf":
            found = await self._find_urdf_file(repo_name)
            if found is not None:
                urdf_path, ref = found
                data_bytes = await self.fetch_file(repo_name, urdf_path, ref=ref)
                # D4 修复：URDF 随包抓取引用的外部网格/texture 资产（数据包自包含，
                # P0-3）。此前只下载 URDF 字节，包内无 mesh，yourdfpy 加载报 11 处
                # 'Unable to resolve filename: package://meshes/...'（ss_franka_002/003
                # 网格缺失根因，与 FrankaAdapter 的 _fetch_* 同模式）。
                raw_url = f"https://raw.githubusercontent.com/{repo_name}/{ref}/{urdf_path}"
                assets = await self._download_xml_with_assets(raw_url, data_bytes)
                # 与 franka 等源一致：剥离 package:// 前缀，使网格引用与资产键
                # （_resolve_asset_rel 剥离后的相对路径）一致，离线可加载。
                data_bytes = re.sub(rb"package://", b"", data_bytes)
                return RawData(
                    source=DataSource.GITHUB,
                    item_id=repo_name,
                    format="urdf",
                    data=data_bytes,
                    url=raw_url,
                    size_bytes=len(data_bytes),
                    assets=assets,
                )
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
            size_bytes=len(readme_bytes),
        )

    async def _find_urdf_file(self, repo_name: str) -> tuple[str, str] | None:
        """递归列出仓库文件树，返回首个 ``.urdf``/``.xacro`` 文件的 (路径, 分支)；无则 None。

        D4 修复：GitHub ``git/trees`` API 固定查 ``main`` 分支对默认分支非 main 的
        仓库（如 ``Kinovarobotics/ros_kortex`` default_branch=noetic-devel）抛 404
        AdapterError，导致 Kinova 等仓库永远回退 README（ms_003 req_000 P2_RETRIEVE
        根因）。改为分支回退：main → master → 仓库 default_branch（``/repos/{repo}``
        API 探测），任一分支找到 URDF 即返回。tree 过大被截断（truncated）时视为
        该分支无结果，继续下一分支。
        """
        for ref in ("main", "master"):
            found = await self._urdf_in_branch(repo_name, ref)
            if found is not None:
                return found, ref
        # 默认分支探测（避免额外 API 调用：main/master 均无结果时才请求）
        default_ref = ""
        try:
            repo_info = await self._request(
                "GET",
                f"/repos/{repo_name}",
                headers=self.headers,
            )
            default_ref = str(repo_info.get("default_branch") or "")
        except AdapterError:
            return None
        if default_ref and default_ref not in ("main", "master"):
            found = await self._urdf_in_branch(repo_name, default_ref)
            if found is not None:
                return found, default_ref
        return None

    async def _urdf_in_branch(self, repo_name: str, ref: str) -> str | None:
        """列出指定分支文件树，返回首个 .urdf/.xacro 路径；无/失败/截断返回 None。"""
        try:
            tree_data = await self._request(
                "GET",
                f"/repos/{repo_name}/git/trees/{ref}?recursive=1",
                headers=self.headers,
            )
        except AdapterError:
            return None
        if tree_data.get("truncated"):
            return None
        for entry in tree_data.get("tree", []):
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            path = str(entry.get("path", ""))
            lower = path.lower()
            if lower.endswith(".urdf") or lower.endswith(".xacro"):
                return path
        return None

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
