# src/rdi/adapters/paperswithcode.py
"""Papers with Code 论文-代码关联源 Adapter。

文档：https://paperswithcode.com/api/v1/
速率限制：无官方限制，建议每秒不超过 5 次
无需 API Key。
"""

import json
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class PapersWithCodeAdapter(BaseAdapter):
    """Papers with Code API Adapter。

    提供：
    - search: 搜索论文-代码关联
    - fetch: 获取论文详情及代码关联
    """

    source = DataSource.PAPERSWITHCODE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.paperswithcode_base_url
            if hasattr(settings, "paperswithcode_base_url") and settings.paperswithcode_base_url
            else "https://paperswithcode.com/api/v1",
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Papers with Code 论文。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表，包含论文与代码关联信息
        """
        data = await self._request(
            "GET",
            "/search/",
            params={"q": query},
        )
        return self._parse_search_results(data)

    async def fetch(self, paper_id: str) -> RawData:
        """获取论文详情及代码关联。

        Args:
            paper_id: 论文 ID（如 "graspnet"）

        Returns:
            RawData 包含论文详情与代码关联 JSON

        Raises:
            AdapterError: 获取失败
        """
        # 获取论文基本信息
        paper_data = await self._request("GET", f"/papers/{paper_id}")

        # 尝试获取关联的代码实现列表
        try:
            implementations_data = await self._request(
                "GET", f"/papers/{paper_id}/implementations/"
            )
        except AdapterError:
            implementations_data = {}

        # 合并论文详情与代码关联
        combined = {
            "paper": paper_data,
            "implementations": implementations_data.get("results", []),
        }
        raw_bytes = json.dumps(combined, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.PAPERSWITHCODE,
            item_id=paper_id,
            format="json",
            data=raw_bytes,
            url=f"{self.base_url}/papers/{paper_id}",
        )

    @staticmethod
    def _parse_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析 Papers with Code 搜索返回的 JSON 数据。"""
        results: list[SearchResult] = []
        for item in data.get("results", []):
            paper = item.get("paper", item)
            paper_id = paper.get("id", "")
            title = paper.get("title", "")
            # 提取代码关联信息
            code_url = ""
            framework = ""
            repo = paper.get("repository", {})
            if repo:
                code_url = repo.get("url", "")
                framework = repo.get("framework", "")
            results.append(
                SearchResult(
                    item_id=paper_id,
                    title=title,
                    source=DataSource.PAPERSWITHCODE,
                    url=paper.get("url", f"https://paperswithcode.com/paper/{paper_id}"),
                    metadata={
                        "paper_id": paper_id,
                        "code_url": code_url,
                        "framework": framework,
                    },
                )
            )
        return results
