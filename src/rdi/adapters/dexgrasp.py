"""DexGraspNet 灵巧手数据集源 Adapter。

基于 HuggingFace API 镜像搜索 dexgraspnet 相关数据集。
文档：https://huggingface.co/docs/hub/api
"""

import json
from typing import Any

from rdi.adapters._graspnet_objects import find_object_grasp_file, norm_object_name
from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, SearchResult

# 按 DataReqType 匹配的扩展名
_MESH_EXTS = (".obj", ".ply", ".stl", ".dae")
# .npy 为 DexGraspNet 官方单物体 grasp 文件格式（每文件含一批 grasp 样本）
_GRASP_EXTS = (".npz", ".pkl", ".npy")

# DexGraspNet 官方 GitHub 仓库 data/dataset/ 下的单物体 grasp 文件兜底。
# 已实测可达（curl HTTP 200）：raw.githubusercontent.com 主链与 cdn.jsdelivr.net
# 镜像均返回约 175KB 的真实 grasp 标注（205 个样本，每个含手部关节 qpos 与 scale）。
# 用于 HF 仓库 grasp 数据仅存在于大体积 tar.gz 归档时的兜底下载。
_DEXGRASP_RAW_REPO = "PKU-EPIC/DexGraspNet"
_DEXGRASP_RAW_REF = "main"
_DEXGRASP_DATASET_DIR = "data/dataset"
# 物体名（规范化后）→ data/dataset/ 下文件名
# plant 与 plate 映射同一文件并非笔误：已实测 DexGraspNet 官方 GitHub 文件树
# （API: repos/PKU-EPIC/DexGraspNet/git/trees/main?recursive=1），data/dataset/
# 与 data/meshdata/ 均只有 5 个条目，其中 "mujoco-Ecoforms_Plant_Plate_S11Turquoise"
# 是单一物体实例（MuJoCo Ecoforms 集合的 "Plant Plate S11 Turquoise"，植物+托盘
# 一体），物体名同时含 plant 与 plate，官方不存在独立的 plate 文件。
_DEXGRASP_DATASET_FILES: dict[str, str] = {
    "banana": "ddg-gd_banana_poisson_002.npy",
    "mug": "core-mug-8570d9a8d24cb0acbebd3c0c0c70fb03.npy",
    "bottle": "sem-Bottle-437678d4bc6be981c8724d5673a063a6.npy",
    "camera": "sem-Camera-7bff4fd4dc53de7496dece3f86cb5dd5.npy",
    "plant": "mujoco-Ecoforms_Plant_Plate_S11Turquoise.npy",
    # ponytail: plate 语义为"植物托盘"而非纯盘子，仅近似匹配；纯盘子 grasp 需
    # 扩展其他源（如 GraspNet bowl 类或 EGAD plate 类），当前保留映射优于删键
    # 后走 _find_file_by_ext 拿到任意不相关物体的 grasp 文件。
    "plate": "mujoco-Ecoforms_Plant_Plate_S11Turquoise.npy",
}


class DexGraspAdapter(BaseAdapter):
    """DexGraspNet Adapter，搜索和获取灵巧手抓取数据集。"""

    source = DataSource.DEXGRASP

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.huggingface_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 DexGraspNet 相关数据集。

        Args:
            query: 搜索词（自动追加 dexgrasp 关键词）

        Returns:
            SearchResult 列表
        """
        data = await self._request(
            "GET",
            "/datasets",
            params={"search": f"dexgrasp {query}", "sort": "downloads", "direction": "-1"},
        )
        results: list[SearchResult] = []
        for item in data:
            item_id = item.get("id", "")
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=item.get("id", item_id),
                    source=DataSource.DEXGRASP,
                    url=f"https://huggingface.co/datasets/{item_id}",
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
        req_type: DataReqType | None = None,
        object_name: str | None = None,
    ) -> RawData:
        """按 DataReqType 返回单个 mesh/grasp 文件或 metadata JSON。

        - MESH: 只下载仓库中首个 ``.obj/.ply/.stl/.dae`` mesh 文件
        - GRASP: 优先按 ``object_name``（物体名或 GraspNet object id）定位真实
          ``.pkl``；找不到回退仓库中首个 ``.npz/.pkl`` 抓取文件
        - DATASET / None: 返回 metadata JSON（不下载整个 tar）

        若仓库中不存在对应类型的单个文件（如 DexGraspNet2.0 全为大体积
        .tar.gz 归档），返回 metadata JSON 并说明原因，避免触发整数据集下载。
        """
        # D3: 来源级本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）
        local = self._try_local_fetch(item_id, req_type=req_type, object_name=object_name)
        if local is not None:
            return local
        # C2: 通过 HF API 列出仓库文件树
        tree = await self._request(
            "GET",
            f"/datasets/{item_id}/tree/main",
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
            "mesh 数据仅存在于大体积 tar.gz 归档中",
        )

    async def _fetch_grasp(
        self,
        item_id: str,
        tree: list[dict[str, Any]],
        object_name: str | None = None,
    ) -> RawData:
        """返回物体对应或首个单个 grasp 文件；无则返回 metadata JSON。

        提供 ``object_name``（或 item_id 本身为物体 id）时优先按物体名定位
        真实 ``.pkl``，找不到回退 ``_find_file_by_ext``。
        """
        file_path = self._find_object_grasp_file(tree, object_name or item_id)
        if file_path is None:
            file_path = self._find_file_by_ext(tree, _GRASP_EXTS)
        if file_path:
            return await self._download_single(item_id, file_path)
        # 兜底：HF 仓库无单文件时，尝试 DexGraspNet 官方 GitHub raw 单物体 grasp 文件
        raw_file = self._find_dexgrasp_raw_file(object_name or item_id)
        if raw_file:
            try:
                return await self._download_dexgrasp_raw(raw_file, item_id)
            except AdapterError:
                pass  # raw 兜底失败时静默降级为 metadata JSON
        return self._build_metadata(
            item_id,
            tree,
            reason="仓库中无单个 grasp 文件 (.npz/.pkl/.npy)，且官方 raw 兜底不可用；"
            "grasp 数据仅存在于大体积 tar.gz 归档中",
        )

    def _find_object_grasp_file(self, tree: list[dict[str, Any]], object_name: str) -> str | None:
        """按物体名定位真实 ``.pkl`` 抓取文件；找不到返回 None。"""
        return find_object_grasp_file(tree, object_name, _GRASP_EXTS)

    def _try_local_fetch(
        self,
        item_id: str,
        req_type: DataReqType | None = None,
        object_name: str | None = None,
    ) -> RawData | None:
        """本地数据集挂载命中检查（D3）。

        本地目录即 HF repo 根（settings.local_datasets["dexgrasp"]）：递归扫描构造
        与 tree API 同构的条目列表，用与网络相同的定位逻辑（_find_object_grasp_file
        / _find_file_by_ext）选相对路径，命中读取本地文件返回 source=LOCAL 的
        RawData（不发网络请求），未命中返回 None 走网络。DATASET 类型不参与本地
        单文件命中（本地挂载不改变 metadata 引用语义）。
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

    def _find_dexgrasp_raw_file(self, object_name: str) -> str | None:
        """按规范化物体名查找 DexGraspNet 官方 ``data/dataset/`` 下对应单物体 grasp 文件。

        命中返回仓库内文件名；未命中返回 None（调用方保持既有降级路径）。
        """
        return _DEXGRASP_DATASET_FILES.get(norm_object_name(object_name))

    async def _download_dexgrasp_raw(self, filename: str, item_id: str) -> RawData:
        """从 DexGraspNet 官方 GitHub 仓库下载单物体 grasp 文件（.npy）。

        走 ``raw.githubusercontent.com`` 主链，失败时由 ``_download_bytes`` 自动转
        jsdelivr 镜像；文件约 175-212KB 无需体积预检。缓存键用 ``_dexgrasp_raw/``
        前缀，与 HF repo 缓存键（``{item_id}/{path}``）隔离。
        """
        url = (
            f"https://raw.githubusercontent.com/{_DEXGRASP_RAW_REPO}/"
            f"{_DEXGRASP_RAW_REF}/{_DEXGRASP_DATASET_DIR}/{filename}"
        )
        cache_id = f"_dexgrasp_raw/{filename}"
        if self.is_cached(cache_id):
            data_bytes = self.load_from_cache(cache_id)
            assert data_bytes is not None  # is_cached 已保证非空
        else:
            data_bytes = await self._download_bytes(url)
            self.save_to_cache(cache_id, data_bytes)
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format="npy",
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            metadata=self._file_metadata("npy"),
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
                source=DataSource.DEXGRASP,
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

        content = await self._download_bytes(url)
        self.save_to_cache(cache_id, content)
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format=fmt,
            data=content,
            url=url,
            size_bytes=len(content),
            metadata=self._file_metadata(fmt),
        )

    @staticmethod
    def _file_metadata(fmt: str) -> dict[str, Any]:
        """真实 grasp 文件标注（.npz/.pkl/.npy 为真实抓取标注，mesh 等无标注）。"""
        return {"is_real_grasp": True} if fmt in ("npz", "pkl", "npy") else {}

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
            "source": "dexgraspnet",
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
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format="json",
            data=data_bytes,
            url=f"https://huggingface.co/datasets/{item_id}",
            size_bytes=len(data_bytes),
        )

    def _find_file_by_ext(self, tree: list[dict[str, Any]], exts: tuple[str, ...]) -> str | None:
        """在文件树中按扩展名匹配首个文件路径。"""
        for item in tree:
            if isinstance(item, dict):
                path = item.get("path", "")
                if path.lower().endswith(exts):
                    return str(path)
        return None
