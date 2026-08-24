# src/rdi/adapters/allegro.py
"""Allegro 灵巧手 URDF 模型源 Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 wonikrobotics.com 网页）
降级回退方式：GitHub raw URL（simlabor/allegro_hand_ros 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

import asyncio
import re

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# D3 修复：wonikrobotics.com 网页国内访问常挂起，_search_primary 用短超时快速
# 放弃转走硬编码 fallback（命中集合不变，只缩短耗时）。Franka 同款策略。
_SEARCH_FAST_TIMEOUT_S = 6.0

# C2 修复：已展开纯 URDF 源（dexsuite/dex-urdf）
# 钉 commit f5e7132f22108164577fea4c25ef99b5cc0e1900（2026-08-10 pin）
_PLAIN_URDF_BASE = (
    "https://raw.githubusercontent.com/dexsuite/dex-urdf/f5e7132f22108164577fea4c25ef99b5cc0e1900"
)
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
        """搜索 Allegro 手模型。优先网页抓取，失败/超时降级硬编码列表。"""
        try:
            async with asyncio.timeout(_SEARCH_FAST_TIMEOUT_S):
                return await self._search_primary(query)
        except (AdapterError, TimeoutError):
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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。

        D3 修复：query 常为 "allegro hand urdf" 这类带空格/中文的混合串，而 id 用
        下划线（allegro_hand_v4）。先归一化（去空格/下划线/连字符）整串匹配，
        失败再按英文 token 匹配，避免因分隔符差异漏配。

        D4 修复（误命中）：原实现只要 query 与模型任一字段词元有交集即命中，
        而 right/left 型号描述含英文 "urdf"，导致任意带 "urdf" 的查询（如
        "kinova gen3 urdf"）误命中 Allegro 手爪（ms_003 重测 req_000 拿到
        Allegro 手而非 Kinova Gen3）。收紧为：仅当 query 与模型 **id/title**
        词元有交集（标识性 token），或与描述词元交集 ≥2 个（多词元强信号）
        才算命中，通用单 token（"urdf"）不再触发。

        D4 二次修复（子串旁路）：归一化子串检查的匹配文本仍含 description——
        "URDF" 作为独立 query 时是描述 "Allegro 右手 URDF 模型" 的子串，绕过
        token 收紧规则再次误命中（ms_003 复测 req_000 又拿到 Allegro 手）。
        子串匹配文本收紧为 id/title 拼接（"urdf" 不在标识中、不再命中）；
        "allegro hand" 类查询仍可经子串/标识 token 命中。
        """
        query_lower = query.lower()
        normalized = re.sub(r"[\s_\-]+", "", query_lower)
        tokens = {t for t in re.findall(r"[a-z0-9]+", query_lower) if len(t) >= 3}
        matched = [
            m
            for m in _FALLBACK_MODELS
            if normalized in re.sub(r"[\s_\-]+", "", f"{m['id']} {m['title']}".lower())
            or bool(tokens & set(re.findall(r"[a-z0-9]+", f"{m['id']} {m['title']}".lower())))
            or len(tokens & set(re.findall(r"[a-z0-9]+", f"{m['description']}".lower()))) >= 2
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
        assets, missing_assets = await self._download_xml_with_assets(urdf_url, content)
        return RawData(
            source=DataSource.ALLEGRO,
            item_id=item_id,
            format=fmt,
            data=content,
            url=urdf_url,
            size_bytes=len(content),
            assets=assets,
            metadata={"assets_missing": missing_assets} if missing_assets else {},
        )

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与 fetch 的 URL 路径同构。"""
        plain_path = _PLAIN_URDF_PATHS.get(item_id)
        if plain_path is not None:
            return [(plain_path, "urdf")]
        return [("allegro_hand_description/urdf/allegro_hand.urdf.xacro", "xacro")]
