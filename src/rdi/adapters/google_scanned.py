# src/rdi/adapters/google_scanned.py
"""Google Scanned Objects 3D 模型源 Adapter。

文档原始对接方式：官方下载
实际实现方式：Gazebo Fuel REST API（fuel.gazebosim.org）
说明：Fuel API 是 Google Scanned Objects 的官方下载渠道，
文档中标注的"官方下载"即指此 API，无需降级回退。
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

        C5 修复：Fuel API 返回的 ``links`` 字段为 None（非 dict），
        原 ``item.get("links", {}).get("self", "")`` 会 AttributeError。
        改为从 name + owner 构造 URL。客户端按 query 过滤 name。
        """
        data = await self._request("GET", "/models", params={"q": query})
        results: list[SearchResult] = []
        query_lower = query.lower()
        for item in data:
            model_name = item.get("name", "")
            # C5: 客户端按 query 过滤（Fuel /models 端点 ?q 过滤不可靠）
            if query_lower not in model_name.lower():
                continue
            owner = item.get("owner", "")
            self_url = f"{self.base_url}/models/{model_name}" if owner else item.get("url_name", "")
            results.append(
                SearchResult(
                    item_id=model_name,
                    title=item.get("displayName", model_name),
                    source=DataSource.GOOGLE_SCANNED,
                    url=self_url,
                    metadata={
                        "description": item.get("description", ""),
                        "tags": item.get("tags", []),
                        "version": item.get("version", 0),
                        "owner": owner,
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 3D 模型的 mesh 压缩包（zip 格式）。

        Args:
            item_id: 模型名称（如 "ACE_Coffee_Mug_Kristen_16_oz_cup"）

        Returns:
            RawData 包含 zip 二进制数据（内含 model.config + meshes/）

        Raises:
            AdapterError: 下载失败

        C5 修复：原 ``/models/{id}/mesh`` 端点不存在（404）。
        Fuel API 实际下载走 ``/1.0/{owner}/models/{name}.zip``（GET 200，
        HEAD 不支持返回 405）。已 curl 验证 ACE_Coffee_Mug...zip 可达。
        """
        zip_url = f"{self.base_url}/models/{item_id}.zip"
        content = await self._download_bytes(zip_url)
        return RawData(
            source=DataSource.GOOGLE_SCANNED,
            item_id=item_id,
            format="zip",
            data=content,
            url=zip_url,
            size_bytes=len(content),
        )
