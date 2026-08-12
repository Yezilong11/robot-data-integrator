# src/rdi/adapters/zenodo.py
"""Zenodo 科研数据存储源 Adapter。

文档：https://developers.zenodo.org/
速率限制：匿名用户较宽松，建议配置 ZENODO_TOKEN。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class ZenodoAdapter(BaseAdapter):
    """Zenodo API Adapter，搜索和获取科研数据记录。"""

    source = DataSource.ZENODO

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.zenodo_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Zenodo 记录。

        Args:
            query: 搜索词（如 "robot grasp dataset"）

        Returns:
            SearchResult 列表，metadata 含 doi、size、created
        """
        data = await self._request(
            "GET",
            "/records",
            params={"q": query, "sort": "mostrecent"},
        )
        results: list[SearchResult] = []
        for item in data.get("hits", {}).get("hits", []):
            item_id = str(item.get("id", ""))
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=item.get("title", ""),
                    source=DataSource.ZENODO,
                    url=item.get("links", {}).get("self_html", ""),
                    metadata={
                        "doi": item.get("doi", ""),
                        "size": item.get("files", [{}])[0].get("size", 0)
                        if item.get("files")
                        else 0,
                        "created": item.get("created", ""),
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """获取记录元数据。

        Args:
            item_id: Zenodo 记录 ID

        Returns:
            RawData 包含记录元数据 JSON

        Raises:
            AdapterError: 获取失败
        """
        import json

        data = await self._request("GET", f"/records/{item_id}")
        content = json.dumps(data, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.ZENODO,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://zenodo.org/records/{item_id}",
            size_bytes=len(content),
        )
