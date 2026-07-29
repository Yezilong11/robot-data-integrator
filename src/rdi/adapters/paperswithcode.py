# src/rdi/adapters/paperswithcode.py
"""Papers with Code 论文-代码关联源 Adapter。

文档原始对接方式：网页解析（BeautifulSoup 解析 paperswithcode.com 搜索页）
降级回退方式：REST API（/search/ 和 /papers/ 端点，返回 JSON）
无需 API Key。
"""

import json
from typing import Any
from urllib.parse import quote_plus

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class PapersWithCodeAdapter(BaseAdapter):
    """Papers with Code Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：网页解析 — BeautifulSoup 解析 paperswithcode.com 搜索结果页
    - 路径 B（降级）：REST API — 调用 Papers with Code REST API
    """

    source = DataSource.PAPERSWITHCODE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.paperswithcode_base_url,
            rate_limit=5,
        )
        self._web_url = settings.paperswithcode_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Papers with Code 论文。

        优先网页解析，失败时降级到 REST API。
        """
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：网页解析方式（文档原始对接方式）。"""
        url = f"{self._web_url}/search?q={quote_plus(query)}"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析搜索结果页中的论文条目
        for article in soup.select("div.paper-card, div.search-result, article"):
            title_el = article.select_one("h1 a, h2 a, .title a")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            href = title_el.get("href", "")
            paper_id = href.rstrip("/").split("/")[-1] if href else ""
            if not paper_id:
                continue
            # 尝试提取代码关联链接
            code_url = ""
            code_el = article.select_one("a[href*='github.com']")
            if code_el:
                code_url = code_el.get("href", "")
            results.append(
                SearchResult(
                    item_id=paper_id,
                    title=title,
                    source=DataSource.PAPERSWITHCODE,
                    url=f"{self._web_url}/paper/{paper_id}",
                    metadata={"paper_id": paper_id, "code_url": code_url},
                )
            )
        if not results:
            raise AdapterError(
                message=f"Web scraping returned no results for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：REST API 降级回退。"""
        data = await self._request("GET", "/search/", params={"q": query})
        return self._parse_search_results(data)

    async def fetch(self, paper_id: str) -> RawData:
        """获取论文详情及代码关联。优先网页解析，失败降级 REST API。"""
        try:
            return await self._fetch_primary(paper_id)
        except AdapterError:
            return await self._fetch_fallback(paper_id)

    async def _fetch_primary(self, paper_id: str) -> RawData:
        """路径 A：网页解析方式（文档原始对接方式）。"""
        url = f"{self._web_url}/paper/{paper_id}"
        soup = await self._scrape_html(url)
        # 提取论文标题
        title_el = soup.select_one("h1, .paper-title")
        title = title_el.get_text(strip=True) if title_el else paper_id
        # 提取代码关联
        implementations: list[dict[str, str]] = []
        for link in soup.select("a[href*='github.com']"):
            implementations.append({"url": link.get("href", "")})
        combined = {"paper_title": title, "implementations": implementations}
        raw_bytes = json.dumps(combined, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.PAPERSWITHCODE,
            item_id=paper_id,
            format="json",
            data=raw_bytes,
            url=url,
            size_bytes=len(raw_bytes),
        )

    async def _fetch_fallback(self, paper_id: str) -> RawData:
        """路径 B：REST API 降级回退。"""
        paper_data = await self._request("GET", f"/papers/{paper_id}")
        implementations: list[Any] = []
        implementations_fetch_failed = False
        try:
            implementations_data = await self._request(
                "GET", f"/papers/{paper_id}/implementations/"
            )
            implementations = implementations_data.get("results", [])
        except AdapterError:
            # implementations 接口失败不阻塞 fetch 主流程，但在 metadata 标记
            implementations_fetch_failed = True
        combined = {
            "paper": paper_data,
            "implementations": implementations,
            "metadata": {
                "implementations_fetch_failed": implementations_fetch_failed,
            },
        }
        raw_bytes = json.dumps(combined, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.PAPERSWITHCODE,
            item_id=paper_id,
            format="json",
            data=raw_bytes,
            url=f"{self.base_url}/papers/{paper_id}",
            size_bytes=len(raw_bytes),
        )

    @staticmethod
    def _parse_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析 Papers with Code REST API 搜索返回的 JSON 数据。"""
        results: list[SearchResult] = []
        for item in data.get("results", []):
            paper = item.get("paper", item)
            paper_id = paper.get("id", "")
            title = paper.get("title", "")
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
