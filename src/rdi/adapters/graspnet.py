# src/rdi/adapters/graspnet.py
"""GraspNet 抓取数据集 Adapter。

文档原始对接方式：官方下载（graspnet.net 网页解析下载链接）
降级回退方式：硬编码数据集列表 + HuggingFace 镜像下载
无需 API Key，但需遵守速率限制。
"""

import json

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

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
        """下载数据集文件。

        C3+C14 修复：原 `_fetch_primary`（graspnet.net/datasets/{id}/download/data.npz）
        和 `_fetch_fallback`（huggingface.co/datasets/graspnet/{id}/resolve/main/data.npz）
        均为虚构路径。改为先调 HF 镜像 API 列文件树，再下载首个数据文件。
        GraspNet-1Billion 实际是 .tar 归档（每个 12-142GB），非 .npz。

        C3 + E1 修复：rect_labels.tar 达 31.8GB，30s 探活超时不可下载。
        下载前 HEAD 预检 Content-Length，超 max_fetch_bytes 阈值时
        改返回 metadata JSON（含 url/size_bytes/file_list）。
        同时补全 target_exts 的 .tar.gz（原仅 .tar，会匹配并下载全量大归档）。
        """
        # C3: 通过 HF 镜像 API 列出仓库文件树（base_url 默认 hf-mirror.com）
        tree = await self._request(
            "GET",
            f"/api/datasets/{item_id}/tree/main",
        )
        # 找首个数据文件（.npz / .tar / .tar.gz / .h5）
        # E1 修订：补 .tar.gz，避免 .tar 误匹配 .tar.gz 的大归档
        target_exts = (".npz", ".tar.gz", ".tar", ".h5", ".hdf5")
        file_path = next(
            (
                item.get("path", "")
                for item in tree
                if isinstance(item, dict) and item.get("path", "").lower().endswith(target_exts)
            ),
            None,
        )
        if not file_path:
            raise AdapterError(
                message=f"No data file ({target_exts}) found in dataset {item_id}",
                source=self.source.value,
            )
        # 确定格式：.tar.gz → tar.gz，其余取末段扩展名
        lower_path = file_path.lower()
        if lower_path.endswith(".tar.gz"):
            fmt = "tar.gz"
        else:
            ext = lower_path.rsplit(".", 1)[-1]
            fmt = {"npz": "npz", "tar": "tar", "h5": "hdf5", "hdf5": "hdf5"}.get(ext, "binary")
        # C3: 下载走 huggingface_download_base_url（默认 hf-mirror.com）
        download_base = settings.huggingface_download_base_url.rstrip("/")
        url = f"{download_base}/datasets/{item_id}/resolve/main/{file_path.lstrip('/')}"
        # E1: HEAD 预检体积，超阈值改返回 metadata
        size = await self._head_content_length(url)
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
                "url": url,
                "size_bytes": size,
                "file_path": file_path,
                "format": fmt,
                "dataset_id": item_id,
                "file_list": file_list,
                "note": "file exceeds max_fetch_bytes; returning metadata only",
            }
            data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return RawData(
                source=DataSource.GRASPNET,
                item_id=item_id,
                format="json",
                data=data_bytes,
                url=url,
                size_bytes=size,
            )
        data_bytes = await self._download_bytes(url)
        return RawData(
            source=DataSource.GRASPNET,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
        )
