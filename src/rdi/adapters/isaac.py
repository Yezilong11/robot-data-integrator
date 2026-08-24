# src/rdi/adapters/isaac.py
"""Isaac Sim 仿真配置示例源 Adapter。

文档原始对接方式：文档解析（BeautifulSoup 解析 docs.isaacsim.omniverse.nvidia.com 文档页面）
降级回退方式：GitHub raw URL（NVIDIA-Omniverse/IsaacSim 仓库）直接下载
无需 API Key，直接 HTTP 下载。

Isaac 官方场景到 MJCF/USD 的映射说明（C13）：
- IsaacLab 资产为 Python 配置（isaaclab_assets/robots/{id}.py），通过
  ``XxxCfg`` 引用 ``usd`` 资产，本身不是 MJCF/XML；
- 本 Adapter 不转换格式：``fetch`` 返回原始 Python 配置字节，并在
  ``RawData.metadata`` 标注 ``isaac_requires_native_processing=True`` 提示下游
  需在 Isaac Sim 环境内用原生 USD/MJCF 管线处理（pxr 未安装，无法在此转换）；
- 同源机器人在 mujoco_menagerie 有对应 MJCF 场景，可交叉参考：
  franka → franka_emika_panda/scene.xml、cassie → agility_cassie/cassie.xml、
  anymal → anybotics_anymal_b/anymal_b.xml（见 rdi.adapters.mujoco._FETCH_XML）。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Isaac Sim 已知示例（C11 修复：isaac-sim/IsaacLab 的资产配置是 Python 文件。
# T4 核实：release/3.0.0-beta2 robots/ 目录经 GitHub API+raw 探活实证，
# 无 ur5/ur5e 等独立文件；UR 工业臂载体为 universal_robots.py（仅 UR10/UR10e），
# kinova.py 为 Gen3 7-Dof 与 Jaco2。仅补实际存在型号，id 与 fetch URL robots/{id}.py 对齐。）
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
    {
        "id": "universal_robots",
        "title": "Universal Robots UR10/UR10e",
        "description": "UR10/UR10e 工业机械臂 USD 资产配置（含 Robotiq/吸入式夹爪变体）",
    },
    {
        "id": "kinova",
        "title": "Kinova Gen3 / Jaco2",
        "description": "Kinova Gen3 7-Dof 与 Jaco2 协作机械臂 USD 资产配置",
    },
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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。"""
        tokens = query.lower().split()
        matched = [
            e
            for e in _FALLBACK_EXAMPLES
            if any(
                token in e["id"].lower()
                or token in e["title"].lower()
                or token in e["description"].lower()
                for token in tokens
            )
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_EXAMPLES)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
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

        D3：本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）。
        C11 修复：NVIDIA-Omniverse/IsaacSim 已 archived 且无资产；
        改用 isaac-sim/IsaacLab，资产通过 Python 配置文件引用 USD。
        删除虚构的 _fetch_primary（docs/_static/{id}.usd 不存在），
        直接走 IsaacLab 的 robots/{id}.py（已 curl 验证 franka.py/allegro.py 可达）。
        """
        # D3: 本地挂载目录即 IsaacLab 仓库根镜像，相对路径与 raw URL 同构
        local = self._local_raw(item_id, self._local_candidates(item_id))
        if local is not None:
            return local
        py_url = f"{self.base_url}/source/isaaclab_assets/isaaclab_assets/robots/{item_id}.py"
        content = await self._download_bytes(py_url)
        return RawData(
            source=DataSource.ISAAC,
            item_id=item_id,
            format="python",
            data=content,
            url=py_url,
            size_bytes=len(content),
            metadata={
                "isaac_requires_native_processing": True,
                "suggestion": (
                    "IsaacLab 资产为 Python 配置，引用 USD 场景；转 MJCF/XML 需在 "
                    "Isaac Sim 环境内用原生 USD/MJCF 管线处理（pxr 未安装，无法在此转换）"
                ),
            },
        )

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与 fetch 的 URL 路径同构。"""
        return [(f"source/isaaclab_assets/isaaclab_assets/robots/{item_id}.py", "python")]
