# src/rdi/adapters/graspnet.py
"""GraspNet 抓取数据集 Adapter。

数据集包含 190+ 物体的 3D 模型、抓取标注和场景数据。
GraspNet 不提供 REST API，search 使用硬编码模型列表，
fetch 从 HuggingFace 镜像下载数据。
无需 API Key，但需遵守速率限制。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL（HuggingFace 镜像）
_DEFAULT_BASE_URL = "https://huggingface.co"

# GraspNet 已知数据集
_KNOWN_DATASETS: list[dict[str, str]] = [
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

    提供：
    - search: 搜索 GraspNet 数据集（硬编码列表 + 关键词过滤）
    - fetch: 根据 dataset_id 从 HuggingFace 镜像下载数据
    """

    source = DataSource.GRASPNET

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.graspnet_base_url or _DEFAULT_BASE_URL,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 GraspNet 数据集。

        Args:
            query: 搜索词（如 "mug"、"benchmark"、"scene"）

        Returns:
            SearchResult 列表，metadata 含 description
        """
        query_lower = query.lower()
        matched = [
            d
            for d in _KNOWN_DATASETS
            if query_lower in d["id"]
            or query_lower in d["title"].lower()
            or query_lower in d["description"].lower()
        ]
        if not matched:
            matched = _KNOWN_DATASETS
        return [
            SearchResult(
                item_id=d["id"],
                title=d["title"],
                source=DataSource.GRASPNET,
                url=f"https://graspnet.net/datasets/{d['id']}",
                metadata={"description": d["description"]},
            )
            for d in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """根据 dataset_id 下载物体数据（NPZ 格式）。

        数据从 HuggingFace 镜像下载。

        Args:
            item_id: 数据集 ID（如 "graspnet-benchmark"）

        Returns:
            RawData 包含 NPZ 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        # TODO: 验证 HuggingFace 镜像 URL 是否可解析，若不可用需切换到 graspnet.net 官方下载
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
