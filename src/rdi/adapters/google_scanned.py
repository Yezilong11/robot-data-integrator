"""Google Scanned Objects 3D 模型源 Adapter。

文档原始对接方式：官方下载
实际实现方式：Gazebo Fuel REST API（fuel.gazebosim.org）
说明：Fuel API 是 Google Scanned Objects 的官方下载渠道，
文档中标注的"官方下载"即指此 API，无需降级回退。
文档：https://fuel.gazebosim.org/1.0/API
"""

from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# MeshSkill 支持的格式，按优先级排序
_MESH_EXTS = (".obj", ".stl", ".ply", ".dae")


class GoogleScannedAdapter(BaseAdapter):
    """Google Scanned Objects Adapter，搜索和获取 3D 扫描物体 mesh。"""

    source = DataSource.GOOGLE_SCANNED

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.google_scanned_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 3D 扫描物体模型。

        Args:
            query: 搜索词（如 "mug", "bottle"）

        Returns:
            SearchResult 列表

        C5 修复：Fuel API 返回的 ``links`` 字段为 None（非 dict），
        原 ``item.get("links", {}).get("self", "")`` 会 AttributeError。
        改为从 name + owner 构造 URL。客户端按 query 过滤 name。
        """
        data = await self._request("GET", "/models", params={"q": query})
        results: list[SearchResult] = []
        query_lower = query.lower()
        for item in data:
            model_name = item.get("name", "")
            # C5: 客户端按 query 过滤（Fuel /models 端点 ?q 过滤不可靠）
            if query_lower not in model_name.lower():
                continue
            owner = item.get("owner", "")
            self_url = f"{self.base_url}/models/{model_name}" if owner else item.get("url_name", "")
            results.append(
                SearchResult(
                    item_id=model_name,
                    title=item.get("displayName", model_name),
                    source=DataSource.GOOGLE_SCANNED,
                    url=self_url,
                    metadata={
                        "description": item.get("description", ""),
                        "tags": item.get("tags", []),
                        "version": item.get("version", 0),
                        "owner": owner,
                    },
                )
            )
        return results

    async def fetch(self, item_id: str) -> RawData:
        """下载 3D 模型的单个 mesh 文件。

        为避免下载完整 zip（常数 MB 且 Fuel 在国内不稳定），先调
        ``/models/{id}/tip/files`` 获取文件树，再只下载 ``meshes/`` 下
        首个支持的 mesh 文件（.obj/.stl/.ply/.dae）。
        若 mesh 文件下载仍失败，返回 metadata JSON（含失败原因与可
        手动下载的完整 zip URL），不抛异常。

        Args:
            item_id: 模型名称（如 "ACE_Coffee_Mug_Kristen_16_oz_cup"）

        Returns:
            RawData 包含 mesh 二进制数据或 metadata JSON
        """
        # 1. 取文件树
        try:
            file_tree_info = await self._request("GET", f"/models/{item_id}/tip/files")
        except AdapterError as e:
            return self._metadata_fallback(
                item_id,
                reason=f"无法获取模型文件树: {e.message}",
            )

        # 2. 在 file_tree 中找首个 mesh 文件路径
        file_tree = file_tree_info.get("file_tree", [])
        mesh_path = self._find_mesh_path(file_tree)
        if not mesh_path:
            return self._metadata_fallback(
                item_id,
                reason="模型中无 MeshSkill 支持的 mesh 文件 (.obj/.stl/.ply/.dae)",
                file_tree=file_tree,
            )

        # 3. 下载单个 mesh 文件（_download_bytes 已含指数退避重试）
        mesh_url = f"{self.base_url}/models/{item_id}/tip/files{mesh_path}"
        try:
            content = await self._download_bytes(mesh_url)
        except AdapterError as e:
            return self._metadata_fallback(
                item_id,
                reason=f"mesh 文件下载失败: {e.message}",
                mesh_path=mesh_path,
                mesh_url=mesh_url,
                file_tree=file_tree,
            )

        fmt = mesh_path.rsplit(".", 1)[-1].lower()
        return RawData(
            source=DataSource.GOOGLE_SCANNED,
            item_id=item_id,
            format=fmt,
            data=content,
            url=mesh_url,
            size_bytes=len(content),
        )

    def _find_mesh_path(self, file_tree: list[dict[str, Any]]) -> str | None:
        """递归遍历 file_tree，返回首个支持的 mesh 文件 path。"""
        for ext in _MESH_EXTS:
            path = self._find_path_by_ext(file_tree, ext)
            if path:
                return path
        return None

    def _find_path_by_ext(self, nodes: list[dict[str, Any]], ext: str) -> str | None:
        """按扩展名在 file_tree 中递归查找文件路径。"""
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_path = node.get("path", "")
            if node_path.lower().endswith(ext):
                return node_path
            children = node.get("children")
            if isinstance(children, list):
                found = self._find_path_by_ext(children, ext)
                if found:
                    return found
        return None

    def _metadata_fallback(
        self,
        item_id: str,
        reason: str,
        mesh_path: str | None = None,
        mesh_url: str | None = None,
        file_tree: list[dict[str, Any]] | None = None,
    ) -> RawData:
        """网络/文件不可用时返回明确降级的 metadata JSON。"""
        import json

        payload = {
            "source": "google_scanned",
            "item_id": item_id,
            "reason": reason,
            "zip_url": f"{self.base_url}/models/{item_id}.zip",
            "mesh_path": mesh_path,
            "mesh_url": mesh_url,
            "file_tree": file_tree or [],
            "note": "单个 mesh 下载失败，返回 metadata；可手动下载完整 zip",
        }
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.GOOGLE_SCANNED,
            item_id=item_id,
            format="json",
            data=data_bytes,
            url=f"{self.base_url}/models/{item_id}.zip",
            size_bytes=len(data_bytes),
        )
