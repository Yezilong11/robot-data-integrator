# src/rdi/adapters/huggingface.py
"""HuggingFace 模型/数据集源 Adapter。

文档：https://huggingface.co/docs/hub/api
速率限制：匿名用户受限制，建议配置 HF_TOKEN。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class HuggingFaceAdapter(BaseAdapter):
    """HuggingFace API Adapter，搜索模型与数据集。"""

    source = DataSource.HUGGINGFACE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.huggingface_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 HuggingFace 模型。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表，metadata 含 downloads、likes、tags
        """
        data = await self._request(
            "GET",
            "/models",
            params={"search": query, "sort": "downloads", "direction": "-1"},
        )
        results: list[SearchResult] = []
        for item in data:
            item_id = item.get("id", "")
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=item.get("modelId", item_id),
                    source=DataSource.HUGGINGFACE,
                    url=f"https://huggingface.co/{item_id}",
                    metadata={
                        "downloads": item.get("downloads", 0),
                        "likes": item.get("likes", 0),
                        "tags": item.get("tags", []),
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载模型 config.json。

        Args:
            item_id: 模型 ID（如 "bert-base-uncased"）

        Returns:
            RawData 包含 config.json 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        config_url = f"https://huggingface.co/{item_id}/resolve/main/config.json"
        content = await self._download_bytes(config_url)
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=config_url,
            size_bytes=len(content),
        )
