# src/rdi/adapters/graspnet.py
"""GraspNet 抓取数据集 Adapter。

文档原始对接方式：官方下载（graspnet.net 网页解析下载链接）
降级回退方式：硬编码数据集列表 + HuggingFace 镜像下载
无需 API Key，但需遵守速率限制。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：GraspNet 已知数据集
_FALLBACK_DATASETS: list[dict[str, str]] = [
    {
        "id": "graspnet-benchmark",
        "title": "GraspNet-1Billion Benchmark",
        "description": "GraspNet-1Billion 大规模抓取基准数据集",
    },
    {
        "id": "graspnet-scene",
        "title": "GraspNet Scene Data",
        "description": "GraspNet 场景数据，包含点云和标注",
    },
    {
        "id": "graspnet-model",
        "title": "GraspNet Model Library",
        "description": "GraspNet 物体 3D 模型库",
    },
    {
        "id": "graspnet-grasp",
        "title": "GraspNet Grasp Label",
        "description": "GraspNet 抓取标注数据",
    },
]


class GraspNetAdapter(BaseAdapter):
    """GraspNet 数据集 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：官方下载 — 解析 graspnet.net 网页获取下载链接
    - 路径 B（降级）：硬编码数据集列表 + HuggingFace 镜像下载
    """

    source = DataSource.GRASPNET

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.graspnet_base_url,
            rate_limit=5,
        )
        self._web_url = settings.graspnet_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 GraspNet 数据集。优先官方网页，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：官方下载方式（文档原始对接方式）— 解析 graspnet.net 页面。"""
        url = f"{self._web_url}/datasets.html"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析数据集下载页面中的条目
        for item in soup.select("div.dataset-item, div.card, section.dataset"):
            title_el = item.select_one("h2, h3, .title, .card-title")
            if not title_el:
                continue
            title = title_el.get_text(strip=True)
            link_el = item.select_one("a[href]")
            dataset_id = ""
            if link_el:
                href = self._attr_str(link_el, "href")
                dataset_id = href.rstrip("/").split("/")[-1] if href else ""
            if not dataset_id:
                continue
            desc_el = item.select_one("p, .description, .card-text")
            description = desc_el.get_text(strip=True) if desc_el else ""
            query_lower = query.lower()
            if (
                query_lower in dataset_id.lower()
                or query_lower in title.lower()
                or query_lower in description.lower()
            ):
                results.append(
                    SearchResult(
                        item_id=dataset_id,
                        title=title,
                        source=DataSource.GRASPNET,
                        url=f"{self._web_url}/datasets/{dataset_id}",
                        metadata={"description": description},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Official site returned no datasets for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            d
            for d in _FALLBACK_DATASETS
            if query_lower in d["id"]
            or query_lower in d["title"].lower()
            or query_lower in d["description"].lower()
        ]
        return [
            SearchResult(
                item_id=d["id"],
                title=d["title"],
                source=DataSource.GRASPNET,
                url=f"{self._web_url}/datasets/{d['id']}",
                metadata={"description": d["description"]},
            )
            for d in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载数据集。优先官方源，失败降级 HuggingFace 镜像。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方下载路径模式）。"""
        url = f"{self._web_url}/datasets/{item_id}/download/data.npz"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format="npz",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：HuggingFace 镜像降级回退。"""
        url = f"{self.base_url}/datasets/graspnet/{item_id}/resolve/main/data.npz"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format="npz",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
