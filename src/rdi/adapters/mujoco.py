# src/rdi/adapters/mujoco.py
"""MuJoCo 仿真配置示例源 Adapter。

从配置的 MuJoCo 仓库获取 MJCF XML 场景配置文件。
需配置 MUJOCO_BASE_URL 环境变量指向可用的模型仓库。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class MuJoCoAdapter(BaseAdapter):
    """MuJoCo 仿真 Adapter，搜索和下载 MJCF XML 配置文件。"""

    source = DataSource.MUJOCO

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.mujoco_base_url,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 MuJoCo 示例场景。

        Args:
            query: 搜索词（如 "ant", "humanoid", "manipulation"）

        Returns:
            SearchResult 列表
        """
        # 预定义的 MuJoCo 示例场景列表
        known_scenes = [
            {"id": "ant", "title": "Ant", "desc": "MuJoCo Ant 四足机器人场景"},
            {"id": "humanoid", "title": "Humanoid", "desc": "MuJoCo 人形机器人场景"},
            {"id": "grasp", "title": "Grasp", "desc": "MuJoCo 机械臂抓取场景"},
            {"id": "manipulation", "title": "Manipulation", "desc": "MuJoCo 操作任务场景"},
            {"id": "hand", "title": "Hand", "desc": "MuJoCo 灵巧手场景"},
            {"id": "cart_pole", "title": "CartPole", "desc": "MuJoCo 倒立摆经典场景"},
        ]
        results: list[SearchResult] = []
        query_lower = query.lower()
        for scene in known_scenes:
            if query_lower in scene["id"] or query_lower in scene["desc"].lower():
                results.append(
                    SearchResult(
                        item_id=scene["id"],
                        title=scene["title"],
                        source=DataSource.MUJOCO,
                        url=f"{self.base_url}/{scene['id']}",
                        metadata={"description": scene["desc"]},
                    )
                )
        # 无匹配时返回全部场景
        if not results:
            for scene in known_scenes:
                results.append(
                    SearchResult(
                        item_id=scene["id"],
                        title=scene["title"],
                        source=DataSource.MUJOCO,
                        url=f"{self.base_url}/{scene['id']}",
                        metadata={"description": scene["desc"]},
                    )
                )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 MJCF XML 配置文件。

        Args:
            item_id: 场景 ID（如 "ant"）

        Returns:
            RawData 包含 XML 配置文件二进制数据

        Raises:
            AdapterError: 下载失败
        """
        xml_url = f"{self.base_url}/{item_id}/{item_id}.xml"
        content = await self._download_bytes(xml_url)
        return RawData(
            source=DataSource.MUJOCO,
            item_id=item_id,
            format="xml",
            data=content,
            url=xml_url,
        )
