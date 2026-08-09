# src/rdi/adapters/franka.py
"""Franka Panda 机械臂 URDF Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 franka.de 网页获取 URDF 链接）
降级回退方式：GitHub raw URL（frankaemika/franka_ros 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：GitHub raw 仓库 URL
_FALLBACK_BASE_URL = "https://raw.githubusercontent.com/frankaemika/franka_ros/develop"

# C2 修复：已展开纯 URDF 源（pybullet_robots 内置 Panda）
_PANDA_PLAIN_URDF_URL = (
    "https://raw.githubusercontent.com/erwincoumans/pybullet_robots/master"
    "/data/franka_panda/panda.urdf"
)

# 降级回退：Franka 机器人已知型号
_FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "panda", "title": "Franka Panda", "description": "7-DOF 灵巧操作臂"},
    {"id": "fr3", "title": "Franka Research 3", "description": "新一代研究平台"},
    {"id": "emika_panda", "title": "Emika Panda", "description": "协作机器人"},
]


class FrankaAdapter(BaseAdapter):
    """Franka Panda 机械臂 URDF Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：网页抓取 — BeautifulSoup 解析 franka.de 获取 URDF 下载链接
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.FRANKA

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.franka_base_url,
            rate_limit=5,
        )
        self._web_url = settings.franka_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Franka 机器人模型。优先网页抓取，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：网页抓取方式（文档原始对接方式）— 解析 franka.de 网页。"""
        url = f"{self._web_url}/models"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析页面中的机器人型号链接
        for link in soup.select("a[href*='panda'], a[href*='fr3'], a[href*='urdf']"):
            model_name = self._attr_str(link, "href").rstrip("/").split("/")[-1]
            if not model_name:
                continue
            title = link.get_text(strip=True) or model_name
            query_lower = query.lower()
            if query_lower in model_name.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=model_name,
                        title=title,
                        source=DataSource.FRANKA,
                        url=f"{self._web_url}/models/{model_name}",
                        metadata={"model_name": model_name},
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
            if query_lower in m["id"]
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
        ]
        return [
            SearchResult(
                item_id=m["id"],
                title=m["title"],
                source=DataSource.FRANKA,
                url=f"{self.base_url}/franka_description/robots/{m['id']}",
                metadata={"model_name": m["id"], "description": m["description"]},
            )
            for m in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件。优先 franka.de 网页，失败降级 GitHub raw URL。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方页面路径模式）。"""
        # 从 franka.de 页面路径构造 URDF 下载链接
        url = f"{self._web_url}/models/{item_id}/{item_id}.urdf"
        if not self.is_cached(item_id, suffix=".urdf"):
            data_bytes = await self._download_bytes(url)
            self.save_to_cache(item_id, data_bytes, suffix=".urdf")
        else:
            cached = self.load_from_cache(item_id, suffix=".urdf")
            assert cached is not None  # is_cached 已保证非空
            data_bytes = cached
        return RawData(
            source=DataSource.FRANKA,
            item_id=item_id,
            format="urdf",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：GitHub raw URL 降级回退。

        C2 修复：panda 使用已展开纯 URDF；fr3/emika_panda 等仍走 xacro，
        但 format 明确标记为 xacro，便于 URDFSkill 做 xacro 兜底。
        """
        if item_id == "panda":
            url = _PANDA_PLAIN_URDF_URL
            fmt = "urdf"
        else:
            url = f"{self.base_url}/franka_description/robots/{item_id}/{item_id}.urdf.xacro"
            fmt = "xacro"
        if not self.is_cached(item_id, suffix=f".{fmt}"):
            data_bytes = await self._download_bytes(url)
            self.save_to_cache(item_id, data_bytes, suffix=f".{fmt}")
        else:
            cached = self.load_from_cache(item_id, suffix=f".{fmt}")
            assert cached is not None  # is_cached 已保证非空
            data_bytes = cached
        return RawData(
            source=DataSource.FRANKA,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
