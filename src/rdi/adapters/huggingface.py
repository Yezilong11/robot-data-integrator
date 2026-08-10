# src/rdi/adapters/huggingface.py
"""HuggingFace 模型/数据集源 Adapter。

文档：https://huggingface.co/docs/hub/api
速率限制：匿名用户受限制，建议配置 HF_TOKEN。
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataReqType, DataSource
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

    async def fetch(self, item_id: str, req_type: DataReqType | str | None = None) -> RawData:
        """从 HuggingFace 获取模型数据。

        根据需求类型选择获取的资源：
        - ``POLICY_MODEL``：调用 ``/api/models/{id}`` 获取 model_info.json，
          含 modelId/tags/siblings 等，供 PolicyInterfaceSkill 解析。
        - 其他类型（默认）：拉取仓库内 ``config.json``（向后兼容）。

        Args:
            item_id: 模型 ID（如 "bert-base-uncased" 或 "aloha-ct/aloha"）
            req_type: 需求类型，决定拉取的资源格式；None 时使用默认 config.json

        Returns:
            RawData 包含获取到的原始字节（JSON 格式）

        Raises:
            AdapterError: 获取失败
        """
        # 规范化 req_type 为字符串值
        req_type_value: str | None = None
        if isinstance(req_type, DataReqType):
            req_type_value = req_type.value
        elif isinstance(req_type, str):
            req_type_value = req_type

        if req_type_value == DataReqType.POLICY_MODEL.value:
            # POLICY_MODEL: 拉取 /api/models/{repo_id}，即 model_info.json
            api_base = settings.huggingface_api_url.rstrip("/")
            model_info_url = f"{api_base}/models/{item_id}"
            content = await self._download_bytes(model_info_url)
            return RawData(
                source=DataSource.HUGGINGFACE,
                item_id=item_id,
                format="json",
                data=content,
                url=model_info_url,
                size_bytes=len(content),
            )

        # 默认：拉取 config.json（向后兼容）
        # C1: 走可配置的下载镜像（默认 hf-mirror.com），避免硬编码 huggingface.co
        download_base = settings.huggingface_download_base_url.rstrip("/")
        config_url = f"{download_base}/{item_id}/resolve/main/config.json"
        content = await self._download_bytes(config_url)
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=config_url,
            size_bytes=len(content),
        )
