"""GraspNet 抓取数据集 Adapter。

文档原始对接方式：官方下载（graspnet.net 网页解析下载链接）
降级回退方式：硬编码数据集列表 + HuggingFace 镜像下载
无需 API Key，但需遵守速率限制。
"""

import json
from typing import Any

from rdi.adapters._graspnet_objects import find_object_grasp_file
from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, RawReference, SearchResult

# 降级回退：GraspNet 已知数据集（C3 修复：id 改为真实 HF repo）
# 已 curl 验证：DravenALG/GraspNet-1Billion 公开可达，含 grasp_label.tar/models.tar 等
_FALLBACK_DATASETS: list[dict[str, str]] = [
    {
        "id": "DravenALG/GraspNet-1Billion",
        "title": "GraspNet-1Billion Benchmark",
        "description": "GraspNet-1Billion 大规模抓取基准数据集（HF 镜像托管）",
    },
    {
        "id": "hushell/graspnet-h5",
        "title": "GraspNet H5 Labels",
        "description": "GraspNet 抓取标注 HDF5 格式",
    },
]

# 按 DataReqType 匹配的扩展名
_MESH_EXTS = (".obj", ".ply", ".stl", ".dae")
_GRASP_EXTS = (".npz", ".pkl")


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
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。"""
        query_lower = query.lower()
        matched = [
            d
            for d in _FALLBACK_DATASETS
            if query_lower in d["id"]
            or query_lower in d["title"].lower()
            or query_lower in d["description"].lower()
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_DATASETS)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
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

    async def fetch(
        self,
        item_id: str,
        req_type: DataReqType | None = None,
        object_name: str | None = None,
    ) -> RawData:
        """按 DataReqType 返回单个 mesh/grasp 文件或 metadata JSON。

        - MESH: 只下载 ``models/`` 或仓库中首个 ``.obj/.ply/.stl/.dae`` mesh 文件
        - GRASP: 优先按 ``object_name``（物体名或 GraspNet object id，如 "banana"/
          "003_cracker_box"）定位 ``grasp_label/`` 下的真实 ``.npz``；找不到回退仓库中
          首个 ``.npz/.pkl`` 抓取文件
        - DATASET / None: 返回 metadata JSON（不下载整个 tar）

        若仓库中不存在对应类型的单个文件（如 GraspNet-1Billion 全为大体积
        .tar 归档），返回 metadata JSON 并说明原因，避免触发整数据集下载。
        """
        # D3: 来源级本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）
        local = self._try_local_fetch(item_id, req_type=req_type, object_name=object_name)
        if local is not None:
            return local
        # C3: 通过 HF 镜像 API 列出仓库文件树（base_url 默认 hf-mirror.com）
        tree = await self._request(
            "GET",
            f"/api/datasets/{item_id}/tree/main",
        )

        if req_type == DataReqType.MESH:
            return await self._fetch_mesh(item_id, tree)
        if req_type == DataReqType.GRASP:
            return await self._fetch_grasp(item_id, tree, object_name=object_name)

        # DATASET 或未知类型：返回 metadata
        return self._build_metadata(item_id, tree)

    async def _fetch_mesh(self, item_id: str, tree: list[dict[str, Any]]) -> RawData:
        """返回首个单个 mesh 文件；无则返回 metadata JSON。"""
        file_path = self._find_file_by_ext(tree, _MESH_EXTS)
        if file_path:
            return await self._download_single(item_id, file_path)
        return self._build_metadata(
            item_id,
            tree,
            reason="仓库中无单个 mesh 文件 (.obj/.ply/.stl/.dae)；"
            "mesh 数据仅存在于大体积 tar 归档中",
        )

    async def _fetch_grasp(
        self,
        item_id: str,
        tree: list[dict[str, Any]],
        object_name: str | None = None,
    ) -> RawData:
        """返回物体对应或首个单个 grasp 文件；无则返回 metadata JSON。

        提供 ``object_name``（或 item_id 本身为物体 id）时优先按物体名定位
        ``grasp_label/`` 下的真实 ``.npz``，找不到回退 ``_find_file_by_ext``。
        """
        file_path = self._find_object_grasp_file(tree, object_name or item_id)
        if file_path is None:
            file_path = self._find_file_by_ext(tree, _GRASP_EXTS)
        if file_path:
            return await self._download_single(item_id, file_path)
        return self._build_metadata(
            item_id,
            tree,
            reason="仓库中无单个 grasp 文件 (.npz/.pkl)；grasp 标注仅存在于大体积 tar/hdf5 归档中",
        )

    def _find_object_grasp_file(self, tree: list[dict[str, Any]], object_name: str) -> str | None:
        """按物体名定位 ``grasp_label/`` 下的真实 ``.npz``；找不到返回 None。"""
        return find_object_grasp_file(tree, object_name, _GRASP_EXTS)

    def _try_local_fetch(
        self,
        item_id: str,
        req_type: DataReqType | None = None,
        object_name: str | None = None,
    ) -> RawData | None:
        """本地数据集挂载命中检查（D3）。

        本地目录即 HF repo 根（settings.local_datasets["graspnet"]）：递归扫描构造
        与 tree API 同构的条目列表，再用与网络相同的定位逻辑（_find_object_grasp_
        file / _find_file_by_ext）选相对路径，命中读取本地文件返回 source=LOCAL
        的 RawData（不发网络请求），未命中返回 None 走网络。DATASET 类型不参与
        本地单文件命中（本地挂载不改变 metadata 引用语义）。
        """
        root = self.local_dataset_root()
        if root is None:
            return None
        tree = self._walk_local_tree(root)
        if not tree:
            return None
        if req_type == DataReqType.MESH:
            file_path = self._find_file_by_ext(tree, _MESH_EXTS)
        elif req_type == DataReqType.GRASP:
            file_path = self._find_object_grasp_file(tree, object_name or item_id)
            if file_path is None:
                file_path = self._find_file_by_ext(tree, _GRASP_EXTS)
        else:
            return None
        if not file_path:
            return None
        path = self._find_local_file([file_path])
        if path is None:
            return None
        data = path.read_bytes()
        fmt = file_path.rsplit(".", 1)[-1].lower()
        return RawData(
            source=DataSource.LOCAL,
            item_id=item_id,
            format=fmt,
            data=data,
            url=f"local://{self.source.value}/{file_path}",
            size_bytes=len(data),
            metadata=self._file_metadata(fmt),
        )

    async def _download_single(self, item_id: str, file_path: str) -> RawData:
        """下载仓库中指定路径的单个文件。"""
        lower_path = file_path.lower()
        if lower_path.endswith(".tar.gz"):
            fmt = "tar.gz"
        else:
            ext = lower_path.rsplit(".", 1)[-1]
            fmt = {
                "npz": "npz",
                "pkl": "pkl",
                "obj": "obj",
                "ply": "ply",
                "stl": "stl",
                "dae": "dae",
                "h5": "hdf5",
                "hdf5": "hdf5",
                "tar": "tar",
            }.get(ext, "binary")

        download_base = settings.huggingface_download_base_url.rstrip("/")
        url = f"{download_base}/datasets/{item_id}/resolve/main/{file_path.lstrip('/')}"

        # 缓存命中直接返回；缓存键用 item_id + 文件路径区分（同一 repo 下不同文件）
        cache_id = f"{item_id}/{file_path}"
        if self.is_cached(cache_id):
            data_bytes = self.load_from_cache(cache_id)
            assert data_bytes is not None  # is_cached 已保证非空
            return RawData(
                source=DataSource.GRASPNET,
                item_id=item_id,
                format=fmt,
                data=data_bytes,
                url=url,
                size_bytes=len(data_bytes),
                metadata=self._file_metadata(fmt),
            )

        # HEAD 预检体积，超阈值改返回 metadata
        size = await self._head_content_length(url)
        if size is not None and size > settings.max_fetch_bytes:
            return self._build_metadata(
                item_id,
                [],
                reason=f"单个文件 {file_path} 体积 {size}B 超过 max_fetch_bytes"
                f" ({settings.max_fetch_bytes}B)，不下载",
                file_path=file_path,
                file_url=url,
                file_size=size,
            )

        data_bytes = await self._download_bytes(url)
        self.save_to_cache(cache_id, data_bytes)
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            metadata=self._file_metadata(fmt),
        )

    @staticmethod
    def _file_metadata(fmt: str) -> dict[str, Any]:
        """真实 grasp 文件标注（.npz/.pkl 为真实抓取标注，mesh 等无标注）。"""
        return {"is_real_grasp": True} if fmt in ("npz", "pkl") else {}

    def _build_metadata(
        self,
        item_id: str,
        tree: list[dict[str, Any]],
        reason: str | None = None,
        file_path: str | None = None,
        file_url: str | None = None,
        file_size: int | None = None,
    ) -> RawData:
        """构造并返回 metadata JSON RawData。"""
        file_list = [
            {
                "path": item.get("path", ""),
                "size": item.get("size", 0),
            }
            for item in tree
            if isinstance(item, dict)
        ]
        payload: dict[str, Any] = {
            "dataset_id": item_id,
            "file_list": file_list,
            "source": "graspnet",
        }
        if reason:
            payload["reason"] = reason
        if file_path:
            payload["file_path"] = file_path
        if file_url:
            payload["file_url"] = file_url
        if file_size is not None:
            payload["file_size"] = file_size
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        # P0-4：未下载的大文件引用（体积超限或仅 tar 归档时走此分支）
        ref_url = file_url or f"https://huggingface.co/datasets/{item_id}"
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format="json",
            data=data_bytes,
            url=f"https://huggingface.co/datasets/{item_id}",
            size_bytes=len(data_bytes),
            reference=RawReference(
                url=ref_url,
                download_hint=ref_url,
                file_size=file_size or 0,
                reason=reason or "数据集为超大归档，未自动下载，返回 metadata 引用",
            ),
        )

    def _find_file_by_ext(self, tree: list[dict[str, Any]], exts: tuple[str, ...]) -> str | None:
        """在文件树中按扩展名匹配首个文件路径。"""
        for item in tree:
            if isinstance(item, dict):
                path = item.get("path", "")
                if path.lower().endswith(exts):
                    return str(path)
        return None
