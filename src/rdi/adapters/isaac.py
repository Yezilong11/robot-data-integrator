# src/rdi/adapters/isaac.py
"""Isaac Sim 仿真配置示例源 Adapter。

文档原始对接方式：文档解析（BeautifulSoup 解析 docs.isaacsim.omniverse.nvidia.com 文档页面）
降级回退方式：GitHub raw URL（NVIDIA-Omniverse/IsaacSim 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Isaac Sim 已知示例（C11 修复：isaac-sim/IsaacLab 的资产配置是 Python 文件）
_FALLBACK_EXAMPLES: list[dict[str, str]] = [
    {
        "id": "franka",
        "title": "Franka Emika Panda",
        "description": "Franka Panda 机械臂 USD 资产配置",
    },
    {"id": "allegro", "title": "Allegro Hand", "description": "Allegro 灵巧手 USD 资产配置"},
    {"id": "ant", "title": "MuJoCo Ant", "description": "Ant 四足机器人 USD 资产配置"},
    {"id": "cassie", "title": "Agility Cassie", "description": "Cassie 双足机器人 USD 资产配置"},
    {"id": "anymal", "title": "ANYmal", "description": "ANYmal 四足机器人 USD 资产配置"},
    {"id": "cartpole", "title": "Cartpole", "description": "倒立摆经典场景 USD 资产配置"},
]


class IsaacSimAdapter(BaseAdapter):
    """Isaac Sim 仿真 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：文档解析 — BeautifulSoup 解析 Isaac Sim 文档页面获取示例配置
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.ISAAC

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.isaac_base_url,
            rate_limit=5,
        )
        self._web_url = settings.isaac_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Isaac Sim 示例。优先文档解析，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：文档解析方式（文档原始对接方式）— 解析 Isaac Sim 文档页面。"""
        url = f"{self._web_url}/latest/tutorials.html"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析文档页面中的教程/示例链接
        for link in soup.select("a[href*='tutorial'], a[href*='example'], a[href*='sample']"):
            example_id = self._attr_str(link, "href").rstrip("/").split("/")[-1]
            if not example_id:
                continue
            title = link.get_text(strip=True) or example_id
            query_lower = query.lower()
            if query_lower in example_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=example_id,
                        title=title,
                        source=DataSource.ISAAC,
                        url=f"{self._web_url}/latest/{example_id}",
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
            e
            for e in _FALLBACK_EXAMPLES
            if query_lower in e["id"]
            or query_lower in e["title"].lower()
            or query_lower in e["description"].lower()
        ]
        return [
            SearchResult(
                item_id=e["id"],
                title=e["title"],
                source=DataSource.ISAAC,
                url=f"{self.base_url}/examples/{e['id']}",
                metadata={"description": e["description"]},
            )
            for e in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载资产配置文件。

        C11 修复：NVIDIA-Omniverse/IsaacSim 已 archived 且无资产；
        改用 isaac-sim/IsaacLab，资产通过 Python 配置文件引用 USD。
        删除虚构的 _fetch_primary（docs/_static/{id}.usd 不存在），
        直接走 IsaacLab 的 robots/{id}.py（已 curl 验证 franka.py/allegro.py 可达）。
        """
        py_url = f"{self.base_url}/source/isaaclab_assets/isaaclab_assets/robots/{item_id}.py"
        content = await self._download_bytes(py_url)
        return RawData(
            source=DataSource.ISAAC,
            item_id=item_id,
            format="python",
            data=content,
            url=py_url,
            size_bytes=len(content),
        )
