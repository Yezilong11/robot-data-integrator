# src/rdi/adapters/huggingface.py
"""HuggingFace 模型/数据集源 Adapter。

文档：https://huggingface.co/docs/hub/api
速率限制：匿名用户受限制，建议配置 HF_TOKEN。
"""

import json
from typing import Any

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

    async def fetch(
        self,
        item_id: str,
        req_type: str | None = None,
    ) -> RawData:
        """按数据类型下载模型元数据文件。

        - POLICY_MODEL: 优先拉取 ``model_info.json``（PolicyInterfaceSkill 期望的
          数据契约）；404 时降级尝试 ``config.json``；两者均失败返回 metadata 引用
        - 其他类型（默认）: 拉取 ``config.json``

        Args:
            item_id: 模型 ID（如 "bert-base-uncased"）
            req_type: 数据需求类型字符串或 DataReqType（如 POLICY_MODEL），可空

        Returns:
            RawData 包含对应 JSON 元数据
        """
        # C1: 走可配置的下载镜像（默认 hf-mirror.com），避免硬编码 huggingface.co
        download_base = settings.huggingface_download_base_url.rstrip("/")
        # retrieve_data 传 DataReqType 枚举（StrEnum，值小写），统一按值比较
        is_policy = str(req_type).lower() == "policy_model"
        if is_policy:
            return await self._fetch_policy_meta(download_base, item_id)
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

    async def _fetch_policy_meta(self, download_base: str, item_id: str) -> RawData:
        """POLICY_MODEL 元数据拉取：model_info.json 优先，404 降级 config.json。

        实测部分模型仓库没有 model_info.json（HF 官方接口才有该字段）：
        优先尝试下载，404/解析失败时降级尝试 config.json；两者均不可用
        返回结构化的 metadata 引用 JSON（含 model_id + 下载提示），保证
        PolicyInterfaceSkill 可消费（PASS_WITH_FALLBACK 语义）。
        """
        candidates = ["model_info.json", "config.json"]
        last_error = ""
        for filename in candidates:
            url = f"{download_base}/{item_id}/resolve/main/{filename}"
            try:
                content = await self._download_bytes(url)
            except Exception as exc:  # noqa: BLE001 — 单文件失败继续尝试下一候选
                last_error = str(exc)
                continue
            validated = self._validate_model_info(item_id, content, filename)
            if validated is not None:
                return RawData(
                    source=DataSource.HUGGINGFACE,
                    item_id=item_id,
                    format="json",
                    data=validated,
                    url=url,
                    size_bytes=len(validated),
                )
        payload = {
            "model_id": item_id,
            "metadata_only": True,
            "note": f"model_info.json/config.json 均不可用，返回元数据引用: {last_error}",
        }
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://huggingface.co/{item_id}",
            size_bytes=len(content),
        )

    @staticmethod
    def _validate_model_info(item_id: str, content: bytes, filename: str) -> bytes | None:
        """校验模型元数据内容为合法 JSON dict；非法时返回 None（由调用方继续降级）。"""
        try:
            decoded = json.loads(content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(decoded, dict):
            return None
        # config.json 缺少 modelId/tags 等模型标识时补充 item_id，保证下游可识别
        if "modelId" not in decoded and "id" not in decoded and "model_id" not in decoded:
            decoded["model_id"] = item_id
            return json.dumps(decoded, ensure_ascii=False).encode("utf-8")
        return content
