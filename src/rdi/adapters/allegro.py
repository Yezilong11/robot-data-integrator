# src/rdi/adapters/allegro.py
"""Allegro 灵巧手 URDF 模型源 Adapter。

从配置的 Allegro 仓库获取灵巧手 URDF 模型文件。
需配置 ALLEGRO_BASE_URL 环境变量指向可用的 URDF 仓库。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class AllegroAdapter(BaseAdapter):
    """Allegro 灵巧手 Adapter，搜索和下载 URDF 模型文件。"""

    source = DataSource.ALLEGRO

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.allegro_base_url,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Allegro 手模型。

        Args:
            query: 搜索词（如 "allegro", "4-finger"）

        Returns:
            SearchResult 列表
        """
        # 预定义的 Allegro 手模型列表
        known_models = [
            {
                "id": "allegro_hand_v4",
                "title": "Allegro Hand v4",
                "desc": "Allegro 4 指灵巧手 v4 版本",
            },
            {
                "id": "allegro_hand_v3",
                "title": "Allegro Hand v3",
                "desc": "Allegro 4 指灵巧手 v3 版本",
            },
            {
                "id": "allegro_hand_right",
                "title": "Allegro Hand Right",
                "desc": "Allegro 右手 URDF 模型",
            },
            {
                "id": "allegro_hand_left",
                "title": "Allegro Hand Left",
                "desc": "Allegro 左手 URDF 模型",
            },
        ]
        results: list[SearchResult] = []
        query_lower = query.lower()
        for model in known_models:
            if query_lower in model["id"].lower() or query_lower in model["desc"].lower():
                results.append(
                    SearchResult(
                        item_id=model["id"],
                        title=model["title"],
                        source=DataSource.ALLEGRO,
                        url=f"{self.base_url}/{model['id']}",
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
                        source=DataSource.ALLEGRO,
                        url=f"{self.base_url}/{model['id']}",
                        metadata={"description": model["desc"]},
                    )
                )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件。

        Args:
            item_id: 手模型 ID（如 "allegro_hand_v4"）

        Returns:
            RawData 包含 URDF 文件二进制数据

        Raises:
            AdapterError: 下载失败
        """
        urdf_url = f"{self.base_url}/{item_id}/{item_id}.urdf"
        content = await self._download_bytes(urdf_url)
        return RawData(
            source=DataSource.ALLEGRO,
            item_id=item_id,
            format="urdf",
            data=content,
            url=urdf_url,
        )
