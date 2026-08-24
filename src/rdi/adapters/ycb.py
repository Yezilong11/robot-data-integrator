"""YCB Objects 数据集 Adapter。

文档原始对接方式：官方下载（rse-lab... 网页解析）
降级回退方式：硬编码物体列表 + HuggingFace 镜像下载
无需 API Key，直接 HTTP 下载。
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataReqType, DataSource
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

# 语义别名：查询词 → 收录词。仅在命中判定时做归一，不改变返回条目本身
_SEMANTIC_ALIASES: dict[str, str] = {"cup": "mug"}


def _normalize_terms(text: str) -> set[str]:
    """分词并对命中的语义别名做双向展开（如 cup→mug），返回匹配用 term 集合。"""
    terms = {t for t in text.lower().replace("_", " ").split() if t}
    for t in list(terms):
        target = _SEMANTIC_ALIASES.get(t)
        if target:
            terms.add(target)
    return terms


# MeshSkill 优先支持的格式（小体积、无额外纹理依赖）
_PREFERRED_MESH_EXTS = (".obj", ".stl", ".ply", ".dae")
# 兼容兜底格式
_FALLBACK_MESH_EXTS = (".glb", ".gltf")

# YCB 在 HF 上的固定网格镜像（ll4ma-lab/ycb-fixed-meshes）
# 提供 google_16k/textured.obj、nontextured.stl 等 MeshSkill 可直接消化的格式
_YCB_FIXED_MESHES_REPO = "ll4ma-lab/ycb-fixed-meshes"

# YCB 抓取标注备选源（YCB-Video/ll4ma 镜像模板，{item_id}.mat）。
# 已实测（2026-08）：该 HF 仓库 ll4ma-lab/ycb-video-annotations 为私有/gated
# （hf-mirror 308 → huggingface.co 401），死路径保留仅为文档；下载失败时静默
# 降级为 mesh（保持二联行为不回归）。
_GRASP_ANNOTATION_REPO = "ll4ma-lab/ycb-video-annotations"


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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。"""
        query_terms = _normalize_terms(query)
        matched = [
            obj
            for obj in _FALLBACK_OBJECTS
            if query_terms & _normalize_terms(f"{obj['id']} {obj['title']} {obj['category']}")
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_OBJECTS)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
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

    async def fetch(
        self,
        item_id: str,
        req_type: DataReqType | None = None,
        object_name: str | None = None,
    ) -> RawData:
        """按需求类型返回 YCB 数据。

        - GRASP: 优先尝试 YCB 抓取标注（``{item_id}.mat``）；标注源不可用时
          静默降级为 mesh，并在 metadata 标注 ``grasp_annotation_available: False``
        - 其他 / None: 返回物体 mesh（优先 .obj/.stl）

        ``object_name`` 为兼容统一 fetch 签名保留：YCB 的物体匹配由 search 的
        query 完成，不改变取数逻辑。
        """
        # D3: 来源级本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）
        local = self._try_local_fetch(item_id, req_type=req_type)
        if local is not None:
            return local
        if req_type == DataReqType.GRASP:
            annotation = await self._fetch_grasp_annotation(item_id)
            if annotation is not None:
                return annotation
        return await self._fetch_mesh(item_id)

    def _try_local_fetch(
        self,
        item_id: str,
        req_type: DataReqType | None = None,
    ) -> RawData | None:
        """本地数据集挂载命中检查（D3）。

        本地目录即 ycb-fixed-meshes 镜像 repo 根（settings.local_datasets["ycb"]）：
        GRASP 命中 ``{item_id}.mat`` 抓取标注（与 _fetch_grasp_annotation 的 URL 同
        构）；mesh 扫描 ``{item_id}/google_16k`` 子树（与 _list_mesh_subtree 同构），
        复用 _pick_mesh_path 选文件，``{item_id}`` 不存在时 ``{item_id}-1`` 兜底。
        命中返回 source=LOCAL 的 RawData（不发网络请求），未命中返回 None 走网络。
        """
        root = self.local_dataset_root()
        if root is None:
            return None
        if req_type == DataReqType.GRASP:
            mat_path = self._find_local_file([f"{item_id}.mat"])
            if mat_path is not None:
                data = mat_path.read_bytes()
                return RawData(
                    source=DataSource.LOCAL,
                    item_id=item_id,
                    format="mat",
                    data=data,
                    url=f"local://{self.source.value}/{item_id}.mat",
                    size_bytes=len(data),
                    metadata={"grasp_annotation_available": True, "is_real_grasp": True},
                )
        subtree = self._walk_local_tree(root, f"{item_id}/google_16k")
        if not subtree:
            # 与网络版一致：{item_id} 不存在时尝试 {item_id}-1 兜底
            subtree = self._walk_local_tree(root, f"{item_id}-1/google_16k")
        if not subtree:
            return None
        mesh_path = self._pick_mesh_path(subtree)
        if not mesh_path:
            return None
        path = self._find_local_file([mesh_path])
        if path is None:
            return None
        data = path.read_bytes()
        fmt = mesh_path.rsplit(".", 1)[-1].lower()
        return RawData(
            source=DataSource.LOCAL,
            item_id=item_id,
            format=fmt,
            data=data,
            url=f"local://{self.source.value}/{mesh_path}",
            size_bytes=len(data),
            metadata={"grasp_annotation_available": False},
        )

    async def _fetch_grasp_annotation(self, item_id: str) -> RawData | None:
        """尝试下载 YCB 抓取标注（.mat）；下载失败或不可用时返回 None（静默降级）。"""
        download_base = settings.huggingface_download_base_url.rstrip("/")
        url = f"{download_base}/datasets/{_GRASP_ANNOTATION_REPO}/resolve/main/{item_id}.mat"
        if self.is_cached(item_id, suffix=".mat"):
            data_bytes = self.load_from_cache(item_id, suffix=".mat")
            assert data_bytes is not None  # is_cached 已保证非空
        else:
            try:
                data_bytes = await self._download_bytes(url)
            except AdapterError:
                return None
            self.save_to_cache(item_id, data_bytes, suffix=".mat")
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format="mat",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            metadata={"grasp_annotation_available": True, "is_real_grasp": True},
        )

    async def _fetch_mesh(self, item_id: str) -> RawData:
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
        if not self.is_cached(item_id, suffix=f".{fmt}"):
            data_bytes = await self._download_bytes(url)
            self.save_to_cache(item_id, data_bytes, suffix=f".{fmt}")
        else:
            cached = self.load_from_cache(item_id, suffix=f".{fmt}")
            assert cached is not None  # is_cached 已保证非空
            data_bytes = cached
        return RawData(
            source=DataSource.YCB,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            metadata={"grasp_annotation_available": False},
        )

    async def _list_mesh_subtree(self, repo_id: str, item_id: str) -> list[dict[str, Any]] | None:
        """列出 repo 中 {item_id}/google_16k 子目录；不存在时返回 None。"""
        try:
            return await self._request(  # type: ignore[no-any-return]
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
                        return str(path)
        for ext in _FALLBACK_MESH_EXTS:
            for item in subtree:
                if isinstance(item, dict):
                    path = item.get("path", "")
                    if path.lower().endswith(ext):
                        return str(path)
        return None
