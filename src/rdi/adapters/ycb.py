# src/rdi/adapters/ycb.py
"""YCB Objects 数据集 Adapter。

YCB 物体集包含 77 个日常物体的精确 3D 扫描模型（STL/OBJ/PLY）。
YCB 不提供 REST API，search 使用硬编码物体列表，
fetch 从 HuggingFace 镜像或官方地址下载数据。
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认基础 URL（HuggingFace 镜像）
_DEFAULT_BASE_URL = "https://huggingface.co"

# YCB 物体 mesh 文件格式后缀映射
_FORMAT_MAP: dict[str, str] = {
    "stl": "stl",
    "obj": "obj",
    "ply": "ply",
}

# YCB 已知物体列表
_KNOWN_OBJECTS: list[dict[str, str]] = [
    {"id": "002_master_chef_can", "title": "Master Chef Can", "category": "can"},
    {"id": "003_cracker_box", "title": "Cracker Box", "category": "box"},
    {"id": "004_sugar_box", "title": "Sugar Box", "category": "box"},
    {"id": "005_tomato_soup_can", "title": "Tomato Soup Can", "category": "can"},
    {"id": "006_mustard_bottle", "title": "Mustard Bottle", "category": "bottle"},
    {"id": "007_tuna_fish_can", "title": "Tuna Fish Can", "category": "can"},
    {"id": "008_pudding_box", "title": "Pudding Box", "category": "box"},
    {"id": "009_gelatin_box", "title": "Gelatin Box", "category": "box"},
    {"id": "010_potted_meat_can", "title": "Potted Meat Can", "category": "can"},
    {"id": "011_banana", "title": "Banana", "category": "fruit"},
    {"id": "019_pitcher_base", "title": "Pitcher Base", "category": "container"},
    {"id": "021_bleach_cleanser", "title": "Bleach Cleanser", "category": "bottle"},
    {"id": "024_bowl", "title": "Bowl", "category": "bowl"},
    {"id": "025_mug", "title": "Mug", "category": "mug"},
    {"id": "035_power_drill", "title": "Power Drill", "category": "tool"},
    {"id": "036_wood_block", "title": "Wood Block", "category": "block"},
    {"id": "037_scissors", "title": "Scissors", "category": "tool"},
    {"id": "040_large_marker", "title": "Large Marker", "category": "tool"},
    {"id": "051_large_clamp", "title": "Large Clamp", "category": "tool"},
    {"id": "052_extra_large_clamp", "title": "Extra Large Clamp", "category": "tool"},
]


class YCBAdapter(BaseAdapter):
    """YCB Objects 数据集 Adapter。

    提供：
    - search: 搜索 YCB 物体模型（硬编码列表 + 关键词过滤）
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
            query: 搜索词（如 "mug"、"banana"、"can"）

        Returns:
            SearchResult 列表，metadata 含 object_name、format、category
        """
        query_lower = query.lower()
        matched = [
            obj
            for obj in _KNOWN_OBJECTS
            if query_lower in obj["id"]
            or query_lower in obj["title"].lower()
            or query_lower in obj["category"]
        ]
        if not matched:
            matched = _KNOWN_OBJECTS
        return [
            SearchResult(
                item_id=obj["id"],
                title=obj["title"],
                source=DataSource.YCB,
                url=f"https://rse-lab.cs.washington.edu/projects/ycb/{obj['id']}",
                metadata={
                    "object_name": obj["id"],
                    "format": "stl",
                    "category": obj["category"],
                },
            )
            for obj in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """根据 object_name 下载物体 mesh 文件（STL 格式）。

        数据从 HuggingFace 镜像下载。

        Args:
            item_id: 物体名称（如 "002_master_chef_can"）

        Returns:
            RawData 包含 STL 二进制数据

        Raises:
            AdapterError: 下载失败
        """
        # TODO: 验证 HuggingFace 镜像 URL 是否可解析，若不可用需切换到华盛顿大学官方源
        url = f"{self.base_url}/datasets/ycb/{item_id}/resolve/main/textured.obj"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format="stl",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
