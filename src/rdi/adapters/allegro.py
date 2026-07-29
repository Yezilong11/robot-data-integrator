# src/rdi/adapters/allegro.py
"""Allegro 灵巧手 URDF 模型源 Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 wonikrobotics.com 网页）
降级回退方式：GitHub raw URL（simlabor/allegro_hand_ros 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Allegro 手已知型号
_FALLBACK_MODELS: list[dict[str, str]] = [
    {
        "id": "allegro_hand_v4",
        "title": "Allegro Hand v4",
        "description": "Allegro 4 指灵巧手 v4 版本",
    },
    {
        "id": "allegro_hand_v3",
        "title": "Allegro Hand v3",
        "description": "Allegro 4 指灵巧手 v3 版本",
    },
    {
        "id": "allegro_hand_right",
        "title": "Allegro Hand Right",
        "description": "Allegro 右手 URDF 模型",
    },
    {
        "id": "allegro_hand_left",
        "title": "Allegro Hand Left",
        "description": "Allegro 左手 URDF 模型",
    },
]


class AllegroAdapter(BaseAdapter):
    """Allegro 灵巧手 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：网页抓取 — BeautifulSoup 解析 wonikrobotics.com 获取 URDF 链接
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.ALLEGRO

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.allegro_base_url,
            rate_limit=5,
        )
        self._web_url = settings.allegro_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Allegro 手模型。优先网页抓取，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：网页抓取方式（文档原始对接方式）— 解析 wonikrobotics.com 网页。"""
        url = f"{self._web_url}/allegro-hand"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析页面中的手型号链接
        for link in soup.select("a[href*='allegro'], a[href*='hand'], a[href*='urdf']"):
            model_id = self._attr_str(link, "href").rstrip("/").split("/")[-1]
            if not model_id:
                continue
            title = link.get_text(strip=True) or model_id
            query_lower = query.lower()
            if query_lower in model_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=model_id,
                        title=title,
                        source=DataSource.ALLEGRO,
                        url=f"{self._web_url}/allegro-hand/{model_id}",
                        metadata={"description": title},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Web scraping returned no models for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            m
            for m in _FALLBACK_MODELS
            if query_lower in m["id"].lower()
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
        ]
        return [
            SearchResult(
                item_id=m["id"],
                title=m["title"],
                source=DataSource.ALLEGRO,
                url=f"{self.base_url}/allegro_hand_description/urdf/{m['id']}",
                metadata={"description": m["description"]},
            )
            for m in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件。优先 wonikrobotics.com，失败降级 GitHub raw URL。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方页面路径模式）。"""
        url = f"{self._web_url}/allegro-hand/{item_id}/{item_id}.urdf"
        content = await self._download_bytes(url)
        return RawData(
            source=DataSource.ALLEGRO,
            item_id=item_id,
            format="urdf",
            data=content,
            url=url,
            size_bytes=len(content),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：GitHub raw URL 降级回退。"""
        urdf_url = f"{self.base_url}/allegro_hand_description/urdf/{item_id}.urdf"
        content = await self._download_bytes(urdf_url)
        return RawData(
            source=DataSource.ALLEGRO,
            item_id=item_id,
            format="urdf",
            data=content,
            url=urdf_url,
            size_bytes=len(content),
        )
