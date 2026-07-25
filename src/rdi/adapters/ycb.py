# src/rdi/adapters/ycb.py
"""YCB Objects 数据集 Adapter。

文档：https://rse-lab.cs.washington.edu/projects/ycb/
YCB 物体集包含 77 个日常物体的精确 3D 扫描模型（STL/OBJ/PLY）。
无需 API Key，直接 HTTP 下载。
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL，可通过 settings.ycb_base_url 覆盖
_DEFAULT_BASE_URL = "https://rse-lab.cs.washington.edu"

# YCB 物体 mesh 文件格式后缀映射
_FORMAT_MAP: dict[str, str] = {
    "stl": "stl",
    "obj": "obj",
    "ply": "ply",
}


class YCBAdapter(BaseAdapter):
    """YCB Objects 数据集 Adapter。

    提供：
    - search: 搜索 YCB 物体模型
    - fetch: 根据 object_name 下载物体 mesh 文件
    """

    source = DataSource.YCB

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.ycb_base_url or _DEFAULT_BASE_URL,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 YCB 物体模型。

        Args:
            query: 搜索词（如 "mug"、"banana"、"002"）

        Returns:
            SearchResult 列表，metadata 含 object_name、format
        """
        data = await self._request(
            "GET",
            "/api/ycb/objects",
            params={"keyword": query, "limit": "20"},
        )
        return self._parse_search_results(data)

    async def fetch(self, item_id: str) -> RawData:
        """根据 object_name 下载物体 mesh 文件（STL 格式）。

        Args:
            item_id: 物体名称（如 "002_master_chef_can"）

        Returns:
            RawData 包含 STL 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        url = f"{self.base_url}/projects/ycb/{item_id}/textured.obj"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format="stl",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    @staticmethod
    def _parse_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析搜索 API 返回的 JSON。"""
        results: list[SearchResult] = []
        for item in data.get("objects", []):
            object_name = item.get("name", "")
            fmt = item.get("format", "stl").lower()
            results.append(
                SearchResult(
                    item_id=object_name,
                    title=item.get("label", object_name),
                    source=DataSource.YCB,
                    url=f"{_DEFAULT_BASE_URL}/projects/ycb/{object_name}",
                    metadata={
                        "object_name": object_name,
                        "format": _FORMAT_MAP.get(fmt, fmt),
                        "category": item.get("category", ""),
                    },
                )
            )
        return results
