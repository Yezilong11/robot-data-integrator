# src/rdi/adapters/franka.py
"""Franka Panda 机械臂 URDF Adapter。

提供 Franka Panda 等机器人的 URDF 模型文件下载。
URDF 文件托管在 GitHub 仓库（frankaemika/franka_ros）。
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL，指向 GitHub raw 仓库
_DEFAULT_BASE_URL = "https://raw.githubusercontent.com/frankaemika/franka_ros/develop"

# Franka 机器人已知型号
_KNOWN_MODELS: list[dict[str, str]] = [
    {"name": "panda", "label": "Franka Panda", "description": "7-DOF 灵巧操作臂"},
    {"name": "fr3", "label": "Franka Research 3", "description": "新一代研究平台"},
    {"name": "emika_panda", "label": "Emika Panda", "description": "协作机器人"},
]


class FrankaAdapter(BaseAdapter):
    """Franka Panda 机械臂 URDF Adapter。

    提供：
    - search: 搜索 Franka 机器人模型（硬编码列表）
    - fetch: 根据 model_name 从 GitHub 下载 URDF 文件
    """

    source = DataSource.FRANKA

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.franka_base_url or _DEFAULT_BASE_URL,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Franka 机器人模型。

        Args:
            query: 搜索词（如 "panda"、"fr3"、"arm"）

        Returns:
            SearchResult 列表
        """
        query_lower = query.lower()
        matched = [
            m
            for m in _KNOWN_MODELS
            if query_lower in m["name"] or query_lower in m["label"].lower()
        ]
        if not matched:
            matched = _KNOWN_MODELS
        return [
            SearchResult(
                item_id=m["name"],
                title=m["label"],
                source=DataSource.FRANKA,
                url=f"{self.base_url}/franka_description/robots/{m['name']}",
                metadata={"model_name": m["name"], "description": m["description"]},
            )
            for m in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """根据 model_name 从 GitHub 下载 URDF 文件。

        Args:
            item_id: 机器人型号名称（如 "panda"）

        Returns:
            RawData 包含 URDF XML 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        url = f"{self.base_url}/franka_description/robots/{item_id}/{item_id}.urdf"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.FRANKA,
            item_id=item_id,
            format="urdf",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
