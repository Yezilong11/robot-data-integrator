# src/rdi/adapters/graspnet.py
"""GraspNet 抓取数据集 Adapter。

文档：https://graspnet.net/api
数据集包含 190+ 物体的 3D 模型、抓取标注和场景数据。
无需 API Key，但需遵守速率限制。
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL，可通过 settings.graspnet_base_url 覆盖
_DEFAULT_BASE_URL = "https://graspnet.net"


class GraspNetAdapter(BaseAdapter):
    """GraspNet 数据集 Adapter。

    提供：
    - search: 搜索 GraspNet 数据集物体
    - fetch: 根据 model_id 下载物体 mesh 或抓取标注
    - fetch_models: 获取物体 3D 模型列表
    - fetch_grasps: 获取抓取标注
    """

    source = DataSource.GRASPNET

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.graspnet_base_url or _DEFAULT_BASE_URL,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 GraspNet 数据集物体。

        Args:
            query: 搜索词（如 "mug"、"bottle"）

        Returns:
            SearchResult 列表，metadata 含 model_id、grasp_count、scene_count
        """
        data = await self._request(
            "GET",
            "/api/models",
            params={"keyword": query, "limit": "20"},
        )
        return self._parse_search_results(data)

    async def fetch(self, item_id: str) -> RawData:
        """根据 model_id 下载物体抓取标注（NPZ 格式）。

        Args:
            item_id: 物体模型 ID（如 "1"）

        Returns:
            RawData 包含 NPZ 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        url = f"{self.base_url}/api/models/{item_id}/grasps"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format="npz",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    async def fetch_models(self, offset: int = 0, limit: int = 50) -> list[dict[str, Any]]:
        """获取物体 3D 模型列表。

        Args:
            offset: 分页偏移量
            limit: 每页数量

        Returns:
            模型信息列表，每项含 model_id、name、category 等
        """
        data = await self._request(
            "GET",
            "/api/models",
            params={"offset": str(offset), "limit": str(limit)},
        )
        return data.get("models", [])

    async def fetch_grasps(self, model_id: str) -> list[dict[str, Any]]:
        """获取指定物体的抓取标注。

        Args:
            model_id: 物体模型 ID

        Returns:
            抓取标注列表，每项含 grasp_pose、width、quality 等
        """
        data = await self._request("GET", f"/api/models/{model_id}/grasps")
        grasps = data.get("grasps", [])
        if not grasps:
            raise AdapterError(
                message=f"未找到模型 {model_id} 的抓取标注",
                source=self.source.value,
            )
        return grasps

    @staticmethod
    def _parse_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析搜索 API 返回的 JSON。"""
        results: list[SearchResult] = []
        for item in data.get("models", []):
            model_id = str(item.get("id", ""))
            results.append(
                SearchResult(
                    item_id=model_id,
                    title=item.get("name", ""),
                    source=DataSource.GRASPNET,
                    url=f"{_DEFAULT_BASE_URL}/models/{model_id}",
                    metadata={
                        "model_id": model_id,
                        "grasp_count": item.get("grasp_count", 0),
                        "scene_count": item.get("scene_count", 0),
                        "category": item.get("category", ""),
                    },
                )
            )
        return results
