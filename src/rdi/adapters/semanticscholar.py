# src/rdi/adapters/semanticscholar.py
"""Semantic Scholar 论文源 Adapter。

文档：https://api.semanticscholar.org/api-v2/graph
速率限制：无 API Key 时每秒 1 次请求；有 API Key 时每秒 10 次。
API Key 通过环境变量 SEMANTICSCHOLAR_API_KEY 设置（可选）。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class SemanticScholarAdapter(BaseAdapter):
    """Semantic Scholar API Adapter。"""

    source = DataSource.SEMANTIC_SCHOLAR

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.semanticscholar_base_url,
            rate_limit=1,  # 无 API Key 时每秒 1 次
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Semantic Scholar 论文。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表
        """
        params = {
            "query": query,
            "limit": "10",
            "fields": "paperId,title,url,abstract,year,citationCount,authors",
        }
        data = await self._request("GET", "/paper/search", params=params)
        return self._parse_search_results(data)

    async def fetch(self, paper_id: str) -> RawData:
        """获取指定论文的详细元数据（JSON）。

        Args:
            paper_id: Semantic Scholar 论文 ID（如 "649de34c279b58e53900e9e3f556777"）

        Returns:
            RawData 包含论文详情 JSON 二进制数据

        Raises:
            AdapterError: 获取失败
        """
        import json

        params = {
            "fields": "paperId,title,url,abstract,year,citationCount,"
            "authors,references.paperId,embedding",
        }
        data = await self._request("GET", f"/paper/{paper_id}", params=params)
        json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.SEMANTIC_SCHOLAR,
            item_id=paper_id,
            format="json",
            data=json_bytes,
            url=f"https://www.semanticscholar.org/paper/{paper_id}",
            size_bytes=len(json_bytes),
        )

    @staticmethod
    def _parse_search_results(data: dict) -> list[SearchResult]:
        """解析 Semantic Scholar 搜索 API 返回的 JSON。"""
        papers = data.get("data", [])
        results: list[SearchResult] = []
        for paper in papers:
            paper_id = paper.get("paperId", "")
            title = paper.get("title", "")
            if not paper_id or not title:
                continue
            authors = [a.get("name", "") for a in paper.get("authors", []) if a.get("name")]
            results.append(
                SearchResult(
                    item_id=paper_id,
                    title=title,
                    source=DataSource.SEMANTIC_SCHOLAR,
                    url=paper.get("url", f"https://www.semanticscholar.org/paper/{paper_id}"),
                    metadata={
                        "abstract": paper.get("abstract", ""),
                        "year": paper.get("year"),
                        "citation_count": paper.get("citationCount", 0),
                        "authors": authors,
                    },
                )
            )
        return results
