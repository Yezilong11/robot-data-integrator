# src/rdi/adapters/isaac.py
"""Isaac Sim 仿真配置示例源 Adapter。

从配置的 Isaac Sim 仓库获取 USD 场景配置文件。
需配置 ISAAC_BASE_URL 环境变量指向可用的模型仓库。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class IsaacSimAdapter(BaseAdapter):
    """Isaac Sim 仿真 Adapter，搜索和下载 USD 配置文件。"""

    source = DataSource.ISAAC

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.isaac_base_url,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Isaac Sim 示例。

        Args:
            query: 搜索词（如 "franka", "ur10", "grasping"）

        Returns:
            SearchResult 列表
        """
        # 预定义的 Isaac Sim 示例列表
        known_examples = [
            {
                "id": "franka_cabinet",
                "title": "Franka Cabinet",
                "desc": "Isaac Sim Franka 开柜门任务",
            },
            {
                "id": "franka_pick_place",
                "title": "Franka Pick Place",
                "desc": "Isaac Sim Franka 抓放任务",
            },
            {
                "id": "ur10_bin_pick",
                "title": "UR10 Bin Pick",
                "desc": "Isaac Sim UR10 箱体拾取场景",
            },
            {
                "id": "allegro_grasp",
                "title": "Allegro Grasp",
                "desc": "Isaac Sim Allegro 手灵巧抓取",
            },
            {"id": "multi_robot", "title": "Multi Robot", "desc": "Isaac Sim 多机器人协作场景"},
            {"id": "rl_games", "title": "RL Games", "desc": "Isaac Sim 强化学习训练示例"},
        ]
        results: list[SearchResult] = []
        query_lower = query.lower()
        for example in known_examples:
            if query_lower in example["id"] or query_lower in example["desc"].lower():
                results.append(
                    SearchResult(
                        item_id=example["id"],
                        title=example["title"],
                        source=DataSource.ISAAC,
                        url=f"{self.base_url}/{example['id']}",
                        metadata={"description": example["desc"]},
                    )
                )
        # 无匹配时返回全部示例
        if not results:
            for example in known_examples:
                results.append(
                    SearchResult(
                        item_id=example["id"],
                        title=example["title"],
                        source=DataSource.ISAAC,
                        url=f"{self.base_url}/{example['id']}",
                        metadata={"description": example["desc"]},
                    )
                )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 USD 配置文件。

        Args:
            item_id: 示例 ID（如 "franka_cabinet"）

        Returns:
            RawData 包含 USD 配置文件二进制数据

        Raises:
            AdapterError: 下载失败
        """
        usd_url = f"{self.base_url}/{item_id}/{item_id}.usd"
        content = await self._download_bytes(usd_url)
        return RawData(
            source=DataSource.ISAAC,
            item_id=item_id,
            format="usd",
            data=content,
            url=usd_url,
        )
