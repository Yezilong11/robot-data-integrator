# src/rdi/adapters/mujoco.py
"""MuJoCo 仿真配置示例源 Adapter。

文档原始对接方式：文档解析（BeautifulSoup 解析 mujoco.readthedocs.io 文档页面）
降级回退方式：GitHub raw URL（google-deepmind/mujoco_menagerie 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：MuJoCo 已知示例场景
_FALLBACK_SCENES: list[dict[str, str]] = [
    {"id": "ant", "title": "Ant", "description": "MuJoCo Ant 四足机器人场景"},
    {"id": "humanoid", "title": "Humanoid", "description": "MuJoCo 人形机器人场景"},
    {"id": "grasp", "title": "Grasp", "description": "MuJoCo 机械臂抓取场景"},
    {"id": "manipulation", "title": "Manipulation", "description": "MuJoCo 操作任务场景"},
    {"id": "hand", "title": "Hand", "description": "MuJoCo 灵巧手场景"},
    {"id": "cart_pole", "title": "CartPole", "description": "MuJoCo 倒立摆经典场景"},
]


class MuJoCoAdapter(BaseAdapter):
    """MuJoCo 仿真 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：文档解析 — BeautifulSoup 解析 MuJoCo 文档页面获取示例配置
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.MUJOCO

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.mujoco_base_url,
            rate_limit=5,
        )
        self._web_url = settings.mujoco_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 MuJoCo 示例场景。优先文档解析，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：文档解析方式（文档原始对接方式）— 解析 MuJoCo 文档页面。"""
        url = f"{self._web_url}/en/latest/modeling.html"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析文档页面中的示例链接
        for link in soup.select("a[href*='xml'], a[href*='model'], a[href*='example']"):
            scene_id = link.get("href", "").rstrip("/").split("/")[-1].replace(".xml", "")
            if not scene_id:
                continue
            title = link.get_text(strip=True) or scene_id
            query_lower = query.lower()
            if query_lower in scene_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=scene_id,
                        title=title,
                        source=DataSource.MUJOCO,
                        url=f"{self._web_url}/en/latest/modeling/{scene_id}",
                        metadata={"description": title},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Documentation parsing returned no results for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            s
            for s in _FALLBACK_SCENES
            if query_lower in s["id"]
            or query_lower in s["title"].lower()
            or query_lower in s["description"].lower()
        ]
        return [
            SearchResult(
                item_id=s["id"],
                title=s["title"],
                source=DataSource.MUJOCO,
                url=f"{self.base_url}/{s['id']}",
                metadata={"description": s["description"]},
            )
            for s in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载 MJCF XML 配置文件。优先文档页面，失败降级 GitHub raw URL。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（文档静态资源路径）。"""
        url = f"{self._web_url}/en/latest/_static/{item_id}.xml"
        content = await self._download_bytes(url)
        return RawData(
            source=DataSource.MUJOCO,
            item_id=item_id,
            format="xml",
            data=content,
            url=url,
            size_bytes=len(content),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：GitHub raw URL 降级回退。"""
        xml_url = f"{self.base_url}/{item_id}/{item_id}.xml"
        content = await self._download_bytes(xml_url)
        return RawData(
            source=DataSource.MUJOCO,
            item_id=item_id,
            format="xml",
            data=content,
            url=xml_url,
            size_bytes=len(content),
        )
