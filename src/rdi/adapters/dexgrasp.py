"""DexGraspNet 灵巧手数据集源 Adapter。

基于 HuggingFace API 镜像搜索 dexgraspnet 相关数据集。
文档：https://huggingface.co/docs/hub/api
"""

import json
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, SearchResult

# 按 DataReqType 匹配的扩展名
_MESH_EXTS = (".obj", ".ply", ".stl", ".dae")
_GRASP_EXTS = (".npz", ".pkl")


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
    ) -> RawData:
        """按 DataReqType 返回单个 mesh/grasp 文件或 metadata JSON。

        - MESH: 只下载仓库中首个 ``.obj/.ply/.stl/.dae`` mesh 文件
        - GRASP: 只下载仓库中首个 ``.npz/.pkl`` 抓取文件
        - DATASET / None: 返回 metadata JSON（不下载整个 tar）

        若仓库中不存在对应类型的单个文件（如 DexGraspNet2.0 全为大体积
        .tar.gz 归档），返回 metadata JSON 并说明原因，避免触发整数据集下载。
        """
        # C2: 通过 HF API 列出仓库文件树
        tree = await self._request(
            "GET",
            f"/datasets/{item_id}/tree/main",
        )

        if req_type == DataReqType.MESH:
            return await self._fetch_mesh(item_id, tree)
        if req_type == DataReqType.GRASP:
            return await self._fetch_grasp(item_id, tree)

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

    async def _fetch_grasp(self, item_id: str, tree: list[dict[str, Any]]) -> RawData:
        """返回首个单个 grasp 文件；无则返回 metadata JSON。"""
        file_path = self._find_file_by_ext(tree, _GRASP_EXTS)
        if file_path:
            return await self._download_single(item_id, file_path)
        return self._build_metadata(
            item_id,
            tree,
            reason="仓库中无单个 grasp 文件 (.npz/.pkl)；grasp 数据仅存在于大体积 tar.gz 归档中",
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
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format=fmt,
            data=content,
            url=url,
            size_bytes=len(content),
        )

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
                    return path
        return None
