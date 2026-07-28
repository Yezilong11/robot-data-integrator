# src/rdi/adapters/robotiq.py
"""Robotiq 夹爪 URDF 模型源 Adapter。

从 GitHub 仓库（ros-industrial/robotiq）获取夹爪 URDF 模型文件。
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL，指向 GitHub raw 仓库
_DEFAULT_BASE_URL = "https://raw.githubusercontent.com/ros-industrial/robotiq/kinetic-devel"


class RobotiqAdapter(BaseAdapter):
    """Robotiq 夹爪 Adapter，搜索和下载 URDF 模型文件。"""

    source = DataSource.ROBOTIQ

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.robotiq_base_url
            if settings.robotiq_base_url != "https://robotiq.com"
            else _DEFAULT_BASE_URL,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Robotiq 夹爪模型。

        Args:
            query: 搜索词（如 "2f-85", "2f-140"）

        Returns:
            SearchResult 列表
        """
        known_models = [
            {"id": "robotiq_2f_85", "title": "Robotiq 2F-85", "desc": "Robotiq 2 指夹爪 85mm 行程"},
            {
                "id": "robotiq_2f_140",
                "title": "Robotiq 2F-140",
                "desc": "Robotiq 2 指夹爪 140mm 行程",
            },
            {
                "id": "robotiq_3f_gripper",
                "title": "Robotiq 3F-Gripper",
                "desc": "Robotiq 3 指自适应夹爪",
            },
            {"id": "robotiq_epick", "title": "Robotiq EPick", "desc": "Robotiq 真空吸盘"},
        ]
        results: list[SearchResult] = []
        query_lower = query.lower()
        for model in known_models:
            if query_lower in model["id"].lower() or query_lower in model["desc"].lower():
                results.append(
                    SearchResult(
                        item_id=model["id"],
                        title=model["title"],
                        source=DataSource.ROBOTIQ,
                        url=f"{self.base_url}/robotiq_description/urdf/{model['id']}",
                        metadata={"description": model["desc"]},
                    )
                )
        # 无匹配时返回全部模型
        if not results:
            for model in known_models:
                results.append(
                    SearchResult(
                        item_id=model["id"],
                        title=model["title"],
                        source=DataSource.ROBOTIQ,
                        url=f"{self.base_url}/robotiq_description/urdf/{model['id']}",
                        metadata={"description": model["desc"]},
                    )
                )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件。

        Args:
            item_id: 夹爪模型 ID（如 "robotiq_2f_85"）

        Returns:
            RawData 包含 URDF 文件二进制数据

        Raises:
            AdapterError: 下载失败
        """
        urdf_url = f"{self.base_url}/robotiq_description/urdf/{item_id}.urdf"
        content = await self._download_bytes(urdf_url)
        return RawData(
            source=DataSource.ROBOTIQ,
            item_id=item_id,
            format="urdf",
            data=content,
            url=urdf_url,
            size_bytes=len(content),
        )
