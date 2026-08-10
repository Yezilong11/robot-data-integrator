# src/rdi/adapters/allegro.py
"""Allegro 灵巧手 URDF 模型源 Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 wonikrobotics.com 网页）
降级回退方式：GitHub raw URL（simlabor/allegro_hand_ros 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# C2 修复：已展开纯 URDF 源（dexsuite/dex-urdf）
# 钉 commit f5e7132f22108164577fea4c25ef99b5cc0e1900（2026-08-10 pin）
_PLAIN_URDF_BASE = "https://raw.githubusercontent.com/dexsuite/dex-urdf/f5e7132f22108164577fea4c25ef99b5cc0e1900"
_PLAIN_URDF_PATHS: dict[str, str] = {
    "allegro_hand_v4": "robots/hands/allegro_hand/allegro_hand_right.urdf",
    "allegro_hand_right": "robots/hands/allegro_hand/allegro_hand_right.urdf",
    "allegro_hand_left": "robots/hands/allegro_hand/allegro_hand_left.urdf",
}

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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。"""
        query_lower = query.lower()
        matched = [
            m
            for m in _FALLBACK_MODELS
            if query_lower in m["id"].lower()
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_MODELS)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
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
        """下载 URDF 文件。

        D3：本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）。
        C2 修复：优先使用 dexsuite/dex-urdf 已展开纯 URDF；
        v3 等无稳定纯 URDF 型号仍走 pal-robotics xacro，format 明确标记为 xacro。
        """
        # D3: 本地挂载目录即 dex-urdf/pal-robotics 仓库根镜像，相对路径与 raw URL 同构
        local = self._local_raw(item_id, self._local_candidates(item_id))
        if local is not None:
            return local
        plain_path = _PLAIN_URDF_PATHS.get(item_id)
        if plain_path is not None:
            urdf_url = f"{_PLAIN_URDF_BASE}/{plain_path}"
            fmt = "urdf"
        else:
            urdf_url = f"{self.base_url}/allegro_hand_description/urdf/allegro_hand.urdf.xacro"
            fmt = "xacro"
        content = await self._download_bytes(urdf_url)
        assets = await self._download_xml_with_assets(urdf_url, content)
        return RawData(
            source=DataSource.ALLEGRO,
            item_id=item_id,
            format=fmt,
            data=content,
            url=urdf_url,
            size_bytes=len(content),
            assets=assets,
        )

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与 fetch 的 URL 路径同构。"""
        plain_path = _PLAIN_URDF_PATHS.get(item_id)
        if plain_path is not None:
            return [(plain_path, "urdf")]
        return [("allegro_hand_description/urdf/allegro_hand.urdf.xacro", "xacro")]
