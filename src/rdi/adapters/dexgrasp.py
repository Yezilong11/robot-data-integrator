# src/rdi/adapters/dexgrasp.py
"""DexGraspNet 灵巧手数据集源 Adapter。

基于 HuggingFace API 镜像搜索 dexgraspnet 相关数据集。
文档：https://huggingface.co/docs/hub/api
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class DexGraspAdapter(BaseAdapter):
    """DexGraspNet Adapter，搜索和获取灵巧手抓取数据集。"""

    source = DataSource.DEXGRASP

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.huggingface_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 DexGraspNet 相关数据集。

        Args:
            query: 搜索词（自动追加 dexgrasp 关键词）

        Returns:
            SearchResult 列表
        """
        data = await self._request(
            "GET",
            "/datasets",
            params={"search": f"dexgrasp {query}", "sort": "downloads", "direction": "-1"},
        )
        results: list[SearchResult] = []
        for item in data:
            item_id = item.get("id", "")
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=item.get("id", item_id),
                    source=DataSource.DEXGRASP,
                    url=f"https://huggingface.co/datasets/{item_id}",
                    metadata={
                        "downloads": item.get("downloads", 0),
                        "likes": item.get("likes", 0),
                        "tags": item.get("tags", []),
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载数据文件（npz 格式）。

        Args:
            item_id: 数据集 ID（如 "dexgraspnet/dexgraspnet"）

        Returns:
            RawData 包含 npz 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        # 默认尝试下载首个 npz 数据文件
        file_url = f"https://huggingface.co/datasets/{item_id}/resolve/main/data.npz"
        content = await self._download_bytes(file_url)
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format="npz",
            data=content,
            url=file_url,
            size_bytes=len(content),
        )
