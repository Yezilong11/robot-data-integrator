# src/rdi/adapters/ieee.py
"""IEEE Xplore 论文源 Adapter。

文档：https://developer.ieee.org/
速率限制：根据 API Key 配额，默认 200 次/天
需要配置 IEEE_API_KEY 环境变量。
"""

import json
import warnings

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class IEEEXploreAdapter(BaseAdapter):
    """IEEE Xplore API Adapter。

    提供：
    - search: 搜索 IEEE 论文
    - fetch: 获取论文详情
    """

    source = DataSource.IEEE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.ieee_base_url
            if hasattr(settings, "ieee_base_url") and settings.ieee_base_url
            else "https://ieeexploreapi.ieee.org/api/v1/search",
            rate_limit=5,
        )
        self.api_key = settings.ieee_api_key
        if not self.api_key:
            warnings.warn(
                "IEEE API Key 未配置，请在 .env 中设置 IEEE_API_KEY",
                stacklevel=2,
            )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 IEEE Xplore 论文。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表

        Raises:
            AdapterError: API Key 未配置或请求失败
        """
        if not self.api_key:
            raise AdapterError(
                message="IEEE API Key 未配置，无法执行搜索",
                source=self.source.value,
            )

        data = await self._request(
            "GET",
            "/",
            params={
                "querytext": query,
                "apikey": self.api_key,
                "max_records": "10",
                "sort_field": "relevance",
            },
        )
        return self._parse_search_results(data)

    async def fetch(self, article_id: str) -> RawData:
        """获取 IEEE 论文详情。

        Args:
            article_id: IEEE 文章 ID

        Returns:
            RawData 包含论文详情 JSON

        Raises:
            AdapterError: API Key 未配置或请求失败
        """
        if not self.api_key:
            raise AdapterError(
                message="IEEE API Key 未配置，无法获取论文详情",
                source=self.source.value,
            )

        data = await self._request(
            "GET",
            "/",
            params={
                "article_number": article_id,
                "apikey": self.api_key,
            },
        )
        raw_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.IEEE,
            item_id=article_id,
            format="json",
            data=raw_bytes,
            url=f"{self.base_url}/?article_number={article_id}",
        )

    @staticmethod
    def _parse_search_results(data: dict) -> list[SearchResult]:
        """解析 IEEE API 搜索返回的 JSON 数据。"""
        results: list[SearchResult] = []
        for item in data.get("results", []):
            article = item.get("article", item)
            article_id = str(article.get("article_number", article.get("doi", "")))
            title = article.get("title", "")
            doi = article.get("doi", "")
            pub_year = article.get("publication_year", "")
            authors = [
                a.get("full_name", a.get("author_name", ""))
                for a in article.get("authors", {}).get("authors", [])
                if a.get("full_name") or a.get("author_name")
            ]
            results.append(
                SearchResult(
                    item_id=article_id,
                    title=title,
                    source=DataSource.IEEE,
                    url=f"https://ieeexplore.ieee.org/document/{article_id}",
                    pdf_url=article.get("pdf_url"),
                    metadata={
                        "doi": doi,
                        "publication_year": pub_year,
                        "authors": authors,
                    },
                )
            )
        return results
