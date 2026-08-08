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

# 降级回退：MuJoCo 已知示例场景（C9/C10 修复：使用 mujoco_menagerie 实际存在的机器人）
_FALLBACK_SCENES: list[dict[str, str]] = [
    {
        "id": "franka_emika_panda",
        "title": "Franka Emika Panda",
        "description": "Franka Panda 7-DOF 机械臂 MJCF",
    },
    {
        "id": "agility_cassie",
        "title": "Agility Cassie",
        "description": "Agility Robotics Cassie 双足机器人",
    },
    {"id": "aloha", "title": "ALOHA", "description": "ALOHA 双臂操作系统"},
    {
        "id": "anybotics_anymal_b",
        "title": "ANYmal B",
        "description": "ANYbotics ANYmal B 四足机器人",
    },
    {
        "id": "boston_dynamics_spot",
        "title": "BD Spot",
        "description": "Boston Dynamics Spot 四足机器人",
    },
    {
        "id": "berkeley_humanoid",
        "title": "Berkeley Humanoid",
        "description": "UC Berkeley 人形机器人",
    },
]

# C10 修复：item_id → mujoco_menagerie 仓库 main 分支实际 XML 路径
# （已 curl 验证：mujoco_menagerie 的 XML 文件名不统一，需逐个映射）
_FETCH_XML: dict[str, str] = {
    "franka_emika_panda": "franka_emika_panda/panda.xml",
    "agility_cassie": "agility_cassie/cassie.xml",
    "aloha": "aloha/aloha.xml",
    "anybotics_anymal_b": "anybotics_anymal_b/anymal_b.xml",
    "boston_dynamics_spot": "boston_dynamics_spot/spot.xml",
    "berkeley_humanoid": "berkeley_humanoid/humanoid.xml",
}


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
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        tokens = query.lower().split()
        matched = [
            s
            for s in _FALLBACK_SCENES
            if any(
                token in s["id"].lower()
                or token in s["title"].lower()
                or token in s["description"].lower()
                for token in tokens
            )
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
        """下载 MJCF XML 配置文件。

        C10 修复：删除虚构的 _fetch_primary（readthedocs _static/{id}.xml 不存在），
        直接走 mujoco_menagerie GitHub raw URL。XML 文件名不统一，用 _FETCH_XML 映射。
        """
        rel_path = _FETCH_XML.get(item_id)
        if not rel_path:
            raise AdapterError(
                message=f"Unknown mujoco scene: {item_id} (no path mapping)",
                source=self.source.value,
            )
        xml_url = f"{self.base_url}/{rel_path}"
        content = await self._download_bytes(xml_url)
        return RawData(
            source=DataSource.MUJOCO,
            item_id=item_id,
            format="xml",
            data=content,
            url=xml_url,
            size_bytes=len(content),
        )
