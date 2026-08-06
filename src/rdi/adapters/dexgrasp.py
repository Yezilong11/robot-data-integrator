# src/rdi/adapters/dexgrasp.py
"""DexGraspNet 灵巧手数据集源 Adapter。

基于 HuggingFace API 镜像搜索 dexgraspnet 相关数据集。
文档：https://huggingface.co/docs/hub/api
"""

import json

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


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

    async def fetch(self, item_id: str) -> RawData:
        """下载数据文件。

        C2 修复：原 fetch 硬编码 `data.npz` 路径，但 HF 上 dexgrasp 仓库
        实际文件名不固定（如 lhrlhr/DexGraspNet2.0 无 .npz）。
        改为先调 HF API 列文件树，再下载首个 .npz/.h5/.tar 文件。

        C2 + E1 修复：lhrlhr/DexGraspNet2.0 文件为多 GB 归档，
        30s 探活超时。下载前 HEAD 预检 Content-Length，超 max_fetch_bytes
        阈值时改返回 metadata JSON（含 file_url/size_bytes/file_list）。

        Args:
            item_id: 数据集 ID（如 "lhrlhr/DexGraspNet2.0"）

        Raises:
            AdapterError: 下载失败或仓库无可用数据文件
        """
        # C2: 通过 HF API 列出仓库文件树
        tree = await self._request(
            "GET",
            f"/datasets/{item_id}/tree/main",
        )
        # C2 修订：首轮 target_exts 漏了 .tar.gz，实测 lhrlhr/DexGraspNet2.0
        # 仓库下全为 .tar.gz 归档。补 .tar.gz/.gz，并按优先级排序匹配。
        target_exts = (".npz", ".h5", ".hdf5", ".tar.gz", ".tar", ".gz")
        file_path = next(
            (
                item.get("path", "")
                for item in tree
                if isinstance(item, dict)
                and item.get("path", "").lower().endswith(target_exts)
            ),
            None,
        )
        if not file_path:
            raise AdapterError(
                message=f"No data file ({target_exts}) found in dataset {item_id}",
                source=self.source.value,
            )
        # 确定格式：取主扩展名（.tar.gz → tar.gz，.npz → npz）
        lower_path = file_path.lower()
        if lower_path.endswith(".tar.gz"):
            fmt = "tar.gz"
        else:
            ext = lower_path.rsplit(".", 1)[-1]
            fmt = {"npz": "npz", "h5": "hdf5", "hdf5": "hdf5", "tar": "tar", "gz": "gz"}.get(
                ext, "binary"
            )
        # C2: 下载走 huggingface_download_base_url（默认 hf-mirror.com）
        download_base = settings.huggingface_download_base_url.rstrip("/")
        file_url = f"{download_base}/datasets/{item_id}/resolve/main/{file_path.lstrip('/')}"
        # E1: HEAD 预检体积，超阈值改返回 metadata
        size = await self._head_content_length(file_url)
        if size is not None and size > settings.max_fetch_bytes:
            file_list = [
                {
                    "path": item.get("path", ""),
                    "size": item.get("size", 0),
                }
                for item in tree
                if isinstance(item, dict)
            ]
            payload = {
                "url": file_url,
                "size_bytes": size,
                "file_path": file_path,
                "format": fmt,
                "dataset_id": item_id,
                "file_list": file_list,
                "note": "file exceeds max_fetch_bytes; returning metadata only",
            }
            data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return RawData(
                source=DataSource.DEXGRASP,
                item_id=item_id,
                format="json",
                data=data_bytes,
                url=file_url,
                size_bytes=size,
            )
        content = await self._download_bytes(file_url)
        return RawData(
            source=DataSource.DEXGRASP,
            item_id=item_id,
            format=fmt,
            data=content,
            url=file_url,
            size_bytes=len(content),
        )
