# src/rdi/adapters/ycb.py
"""YCB Objects 数据集 Adapter。

文档原始对接方式：官方下载（rse-lab.cs.washington.edu 网页解析）
降级回退方式：硬编码物体列表 + HuggingFace 镜像下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：HuggingFace 镜像基础 URL
_FALLBACK_BASE_URL = "https://huggingface.co"

# 降级回退：YCB 已知物体列表
_FALLBACK_OBJECTS: list[dict[str, str]] = [
    {"id": "002_master_chef_can", "title": "Master Chef Can", "category": "can"},
    {"id": "003_cracker_box", "title": "Cracker Box", "category": "box"},
    {"id": "004_sugar_box", "title": "Sugar Box", "category": "box"},
    {"id": "005_tomato_soup_can", "title": "Tomato Soup Can", "category": "can"},
    {"id": "006_mustard_bottle", "title": "Mustard Bottle", "category": "bottle"},
    {"id": "007_tuna_fish_can", "title": "Tuna Fish Can", "category": "can"},
    {"id": "008_pudding_box", "title": "Pudding Box", "category": "box"},
    {"id": "009_gelatin_box", "title": "Gelatin Box", "category": "box"},
    {"id": "010_potted_meat_can", "title": "Potted Meat Can", "category": "can"},
    {"id": "011_banana", "title": "Banana", "category": "fruit"},
    {"id": "019_pitcher_base", "title": "Pitcher Base", "category": "container"},
    {"id": "021_bleach_cleanser", "title": "Bleach Cleanser", "category": "bottle"},
    {"id": "024_bowl", "title": "Bowl", "category": "bowl"},
    {"id": "025_mug", "title": "Mug", "category": "mug"},
    {"id": "035_power_drill", "title": "Power Drill", "category": "tool"},
    {"id": "036_wood_block", "title": "Wood Block", "category": "block"},
    {"id": "037_scissors", "title": "Scissors", "category": "tool"},
    {"id": "040_large_marker", "title": "Large Marker", "category": "tool"},
    {"id": "051_large_clamp", "title": "Large Clamp", "category": "tool"},
    {"id": "052_extra_large_clamp", "title": "Extra Large Clamp", "category": "tool"},
]


class YCBAdapter(BaseAdapter):
    """YCB Objects 数据集 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：官方下载 — 解析华盛顿大学官方页面获取下载链接
    - 路径 B（降级）：硬编码物体列表 + HuggingFace 镜像下载
    """

    source = DataSource.YCB

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.ycb_base_url or _FALLBACK_BASE_URL,
            rate_limit=5,
        )
        self._web_url = settings.ycb_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 YCB 物体模型。优先官方网页，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：官方下载方式（文档原始对接方式）— 解析官方页面。"""
        soup = await self._scrape_html(self._web_url)
        results: list[SearchResult] = []
        # 解析页面中的物体链接
        for link in soup.select("a[href*='ycb'], a[href*='object']"):
            obj_id = link.get("href", "").rstrip("/").split("/")[-1]
            if not obj_id:
                continue
            title = link.get_text(strip=True) or obj_id
            query_lower = query.lower()
            if query_lower in obj_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=obj_id,
                        title=title,
                        source=DataSource.YCB,
                        url=f"{self._web_url}/{obj_id}",
                        metadata={"object_name": obj_id, "format": "stl"},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Official site returned no objects for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            obj
            for obj in _FALLBACK_OBJECTS
            if query_lower in obj["id"]
            or query_lower in obj["title"].lower()
            or query_lower in obj["category"].lower()
        ]
        return [
            SearchResult(
                item_id=obj["id"],
                title=obj["title"],
                source=DataSource.YCB,
                url=f"{self._web_url}/projects/ycb/{obj['id']}",
                metadata={
                    "object_name": obj["id"],
                    "format": "stl",
                    "category": obj["category"],
                },
            )
            for obj in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载物体 mesh。优先官方源，失败降级 HuggingFace 镜像。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方下载路径模式）。"""
        url = f"{self._web_url}/{item_id}/textured.obj"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format="stl",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：HuggingFace 镜像降级回退。"""
        url = f"{self.base_url}/datasets/ycb/{item_id}/resolve/main/textured.obj"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format="stl",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
