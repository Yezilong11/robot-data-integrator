# src/rdi/adapters/google_scanned.py
"""Google Scanned Objects 3D 模型源 Adapter。

基于 Gazebo Fuel API 搜索和获取 3D 扫描物体模型。
文档：https://fuel.gazebosim.org/1.0/API
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class GoogleScannedAdapter(BaseAdapter):
    """Google Scanned Objects Adapter，搜索和获取 3D 扫描物体 mesh。"""

    source = DataSource.GOOGLE_SCANNED

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.google_scanned_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 3D 扫描物体模型。

        Args:
            query: 搜索词（如 "mug", "bottle"）

        Returns:
            SearchResult 列表
        """
        data = await self._request("GET", "/models", params={"q": query})
        results: list[SearchResult] = []
        for item in data:
            model_name = item.get("name", "")
            results.append(
                SearchResult(
                    item_id=model_name,
                    title=item.get("displayName", model_name),
                    source=DataSource.GOOGLE_SCANNED,
                    url=item.get("links", {}).get("self", ""),
                    metadata={
                        "description": item.get("description", ""),
                        "tags": item.get("tags", []),
                        "version": item.get("version", 0),
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 3D 模型的 mesh 文件（obj 格式）。

        Args:
            item_id: 模型名称（如 "Mug"）

        Returns:
            RawData 包含 obj mesh 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        mesh_url = f"{self.base_url}/models/{item_id}/mesh"
        content = await self._download_bytes(mesh_url)
        return RawData(
            source=DataSource.GOOGLE_SCANNED,
            item_id=item_id,
            format="obj",
            data=content,
            url=mesh_url,
        )
