"""YCB Objects 数据集 Adapter。

文档原始对接方式：官方下载（rse-lab... 网页解析）
降级回退方式：硬编码物体列表 + HuggingFace 镜像下载
无需 API Key，直接 HTTP 下载。
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：YCB 已知物体列表
_FALLBACK_OBJECTS: list[dict[str, str]] = [
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

# MeshSkill 优先支持的格式（小体积、无额外纹理依赖）
_PREFERRED_MESH_EXTS = (".obj", ".stl", ".ply", ".dae")
# 兼容兜底格式
_FALLBACK_MESH_EXTS = (".glb", ".gltf")

# YCB 在 HF 上的固定网格镜像（ll4ma-lab/ycb-fixed-meshes）
# 提供 google_16k/textured.obj、nontextured.stl 等 MeshSkill 可直接消化的格式
_YCB_FIXED_MESHES_REPO = "ll4ma-lab/ycb-fixed-meshes"


class YCBAdapter(BaseAdapter):
    """YCB Objects 数据集 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：官方下载 — 解析华盛顿大学官方页面获取下载链接
    - 路径 B（降级）：硬编码物体列表 + HuggingFace 镜像下载
    """

    source = DataSource.YCB

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.ycb_base_url,
            rate_limit=5,
        )
        self._web_url = settings.ycb_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 YCB 物体模型。优先官方网页，失败降级硬编码列表。"""
        try:
            return await self._search_primary(query)
        except AdapterError:
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：官方下载方式（文档原始对接方式）— 解析官方页面。"""
        soup = await self._scrape_html(self._web_url)
        results: list[SearchResult] = []
        # 解析页面中的物体链接
        for link in soup.select("a[href*='ycb'], a[href*='object']"):
            obj_id = self._attr_str(link, "href").rstrip("/").split("/")[-1]
            if not obj_id:
                continue
            title = link.get_text(strip=True) or obj_id
            query_lower = query.lower()
            if query_lower in obj_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=obj_id,
                        title=title,
                        source=DataSource.YCB,
                        url=f"{self._web_url}/{obj_id}",
                        metadata={"object_name": obj_id, "format": "obj"},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Official site returned no objects for: {query}",
                source=self.source.value,
            )
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            obj
            for obj in _FALLBACK_OBJECTS
            if query_lower in obj["id"]
            or query_lower in obj["title"].lower()
            or query_lower in obj["category"].lower()
        ]
        return [
            SearchResult(
                item_id=obj["id"],
                title=obj["title"],
                source=DataSource.YCB,
                url=f"{self._web_url}/projects/ycb/{obj['id']}",
                metadata={
                    "object_name": obj["id"],
                    "format": "obj",
                    "category": obj["category"],
                },
            )
            for obj in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载物体 mesh 文件（优先 .obj/.stl）。

        改为从 ``ll4ma-lab/ycb-fixed-meshes`` 镜像拉取，该镜像提供
        ``{item_id}/google_16k/textured.obj`` 等 MeshSkill 可直接加载的格式。
        若 {item_id} 在镜像中不存在（如 005_tomato_soup_can 实际为
        005_tomato_soup_can-1），尝试 ``{item_id}-1`` 兜底。
        """
        repo_id = _YCB_FIXED_MESHES_REPO
        subtree = await self._list_mesh_subtree(repo_id, item_id)
        if subtree is None:
            subtree = await self._list_mesh_subtree(repo_id, f"{item_id}-1")
            if subtree is None:
                raise AdapterError(
                    message=f"No mesh subtree found for {item_id} in {repo_id}",
                    source=self.source.value,
                )

        mesh_path = self._pick_mesh_path(subtree)
        if not mesh_path:
            raise AdapterError(
                message=f"No mesh file found in {repo_id}/{item_id}/google_16k",
                source=self.source.value,
            )

        fmt = mesh_path.rsplit(".", 1)[-1].lower()
        download_base = settings.huggingface_download_base_url.rstrip("/")
        url = f"{download_base}/datasets/{repo_id}/resolve/main/{mesh_path.lstrip('/')}"
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )

    async def _list_mesh_subtree(self, repo_id: str, item_id: str) -> list[dict[str, Any]] | None:
        """列出 repo 中 {item_id}/google_16k 子目录；不存在时返回 None。"""
        try:
            return await self._request(
                "GET",
                f"/api/datasets/{repo_id}/tree/main/{item_id}/google_16k",
            )
        except AdapterError as e:
            status = getattr(e, "status_code", None)
            if status == 404:
                return None
            raise

    def _pick_mesh_path(self, subtree: list[dict[str, Any]]) -> str | None:
        """按优先级从文件树中挑选一个 mesh 文件路径。"""
        for ext in _PREFERRED_MESH_EXTS:
            for item in subtree:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    if path.lower().endswith(ext):
                        return path
        for ext in _FALLBACK_MESH_EXTS:
            for item in subtree:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    if path.lower().endswith(ext):
                        return path
        return None
