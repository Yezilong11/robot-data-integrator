# src/rdi/adapters/mujoco.py
"""MuJoCo 仿真配置示例源 Adapter。

文档原始对接方式：文档解析（BeautifulSoup 解析 mujoco.readthedocs.io 文档页面）
降级回退方式：GitHub raw URL（google-deepmind/mujoco_menagerie 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

import asyncio
from typing import cast

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：MuJoCo 已知示例场景（C9/C10 修复：使用 mujoco_menagerie 实际存在的机器人）
# C13：每条记录增加 keywords（小写）供 token 匹配，提升查询命中率
_FALLBACK_SCENES: list[dict[str, str | list[str]]] = [
    {
        "id": "franka_emika_panda",
        "title": "Franka Emika Panda",
        "description": "Franka Panda 7-DOF 机械臂 MJCF",
        "keywords": ["franka", "panda", "arm"],
    },
    {
        "id": "agility_cassie",
        "title": "Agility Cassie",
        "description": "Agility Robotics Cassie 双足机器人",
        "keywords": ["cassie", "agility", "biped"],
    },
    {
        "id": "aloha",
        "title": "ALOHA",
        "description": "ALOHA 双臂操作系统",
        "keywords": ["aloha", "viperx", "bimanual"],
    },
    {
        "id": "anybotics_anymal_b",
        "title": "ANYmal B",
        "description": "ANYbotics ANYmal B 四足机器人",
        "keywords": ["anymal", "anybotics", "quadruped"],
    },
    {
        "id": "boston_dynamics_spot",
        "title": "BD Spot",
        "description": "Boston Dynamics Spot 四足机器人",
        "keywords": ["spot", "boston dynamics", "quadruped"],
    },
    {
        "id": "berkeley_humanoid",
        "title": "Berkeley Humanoid",
        "description": "UC Berkeley 人形机器人",
        "keywords": ["berkeley", "humanoid", "biped"],
    },
    {
        "id": "unitree_go2",
        "title": "Unitree Go2",
        "description": "Unitree Go2 四足机器人",
        "keywords": ["unitree", "go2", "quadruped"],
    },
]

# C10 修复：item_id → mujoco_menagerie 仓库 main 分支实际 XML 路径
# （已 curl 验证：mujoco_menagerie 的 XML 文件名不统一，需逐个映射）
# C13：franka_emika_panda 与 unitree_go2 改用规范的 scene.xml（场景文件，
# include 机器人本体 + 相机/地面，是完整的可渲染场景；已通过 GitHub API 验证存在）
_FETCH_XML: dict[str, str] = {
    "franka_emika_panda": "franka_emika_panda/scene.xml",
    "agility_cassie": "agility_cassie/cassie.xml",
    "aloha": "aloha/aloha.xml",
    "anybotics_anymal_b": "anybotics_anymal_b/anymal_b.xml",
    "boston_dynamics_spot": "boston_dynamics_spot/spot.xml",
    "berkeley_humanoid": "berkeley_humanoid/humanoid.xml",
    "unitree_go2": "unitree_go2/scene.xml",
}


class MuJoCoAdapter(BaseAdapter):
    """MuJoCo 仿真 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：文档解析 — BeautifulSoup 解析 MuJoCo 文档页面获取示例配置
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.MUJOCO

    # 国外主路径（readthedocs）访问国内常挂起，主尝试用短超时快速放弃，
    # 转走 fallback（命中集合不变，只缩短耗时）。
    _PRIMARY_FAST_TIMEOUT_S = 10.0

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.mujoco_base_url,
            rate_limit=5,
        )
        self._web_url = settings.mujoco_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 MuJoCo 示例场景。优先文档解析，失败降级硬编码列表。"""
        try:
            async with asyncio.timeout(self._PRIMARY_FAST_TIMEOUT_S):
                return await self._search_primary(query)
        except (AdapterError, TimeoutError):
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：文档解析方式（文档原始对接方式）— 解析 MuJoCo 文档页面。

        C9 修复：CSS 选择器收紧到 a[href$='.xml']（仅 .xml 文件链接），
        且过滤含 # 的 href（文档锚点如 #Saint_Venant-Kirchhoff_model 不是场景）。
        """
        url = f"{self._web_url}/en/latest/modeling.html"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # C9: 仅匹配 .xml 文件链接，过滤文档锚点
        for link in soup.select("a[href$='.xml']"):
            href = self._attr_str(link, "href")
            if "#" in href or not href:
                continue
            scene_id = href.rstrip("/").split("/")[-1].replace(".xml", "")
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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。

        C13：匹配维度扩展 id/title/description + keywords 列表（任一 token
        命中任一字段/关键词即返回）。
        """
        tokens = query.lower().split()
        matched = [
            s
            for s in _FALLBACK_SCENES
            if any(
                token in cast("str", s["id"]).lower()
                or token in cast("str", s["title"]).lower()
                or token in cast("str", s["description"]).lower()
                or any(token in kw for kw in s.get("keywords", []))
                for token in tokens
            )
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_SCENES)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
        return [
            SearchResult(
                item_id=cast("str", s["id"]),
                title=cast("str", s["title"]),
                source=DataSource.MUJOCO,
                url=f"{self.base_url}/{cast('str', s['id'])}",
                metadata={"description": cast("str", s["description"])},
            )
            for s in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载 MJCF XML 配置文件。

        D3：本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）。
        C10 修复：删除虚构的 _fetch_primary（readthedocs _static/{id}.xml 不存在），
        直接走 mujoco_menagerie GitHub raw URL。XML 文件名不统一，用 _FETCH_XML 映射。
        """
        # D3: 本地挂载目录即 mujoco_menagerie 仓库根镜像，相对路径即 _FETCH_XML
        local = self._local_raw(item_id, self._local_candidates(item_id))
        if local is not None:
            return local
        rel_path = _FETCH_XML.get(item_id)
        if not rel_path:
            raise AdapterError(
                message=f"Unknown mujoco scene: {item_id} (no path mapping)",
                source=self.source.value,
            )
        xml_url = f"{self.base_url}/{rel_path}"
        content = await self._download_bytes(xml_url)
        assets, missing_assets = await self._download_xml_with_assets(xml_url, content)
        return RawData(
            source=DataSource.MUJOCO,
            item_id=item_id,
            format="xml",
            data=content,
            url=xml_url,
            size_bytes=len(content),
            assets=assets,
            metadata={"assets_missing": missing_assets} if missing_assets else {},
        )

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与 fetch 的 URL 路径同构。"""
        rel_path = _FETCH_XML.get(item_id)
        if not rel_path:
            return []
        return [(rel_path, "xml")]
