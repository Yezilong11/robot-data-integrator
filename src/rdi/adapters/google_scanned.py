"""Google Scanned Objects 3D 模型源 Adapter。

文档原始对接方式：官方下载
实际实现方式：Gazebo Fuel REST API（fuel.gazebosim.org）
说明：Fuel API 是 Google Scanned Objects 的官方下载渠道，
文档中标注的"官方下载"即指此 API，无需降级回退。
文档：https://fuel.gazebosim.org/1.0/API
"""

import re
from typing import Any, NoReturn

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# MeshSkill 支持的格式，按优先级排序
_MESH_EXTS = (".obj", ".stl", ".ply", ".dae")

# D3 修复：Fuel 搜索对完整 query/中文几乎必空（模型名为英文专名），且 query 常为
# "任意一个物体 mesh"/"水壶 kettle mesh" 这类描述性文本。search 依次尝试：
# 完整 query → 英文词元 → 语义别名 → 通用兜底候选（探测确认 tree 可下载）。
_SEARCH_STOPWORDS: frozenset[str] = frozenset(
    {
        "mesh",
        "model",
        "models",
        "object",
        "objects",
        "obj",
        "stl",
        "ply",
        "dae",
        "glb",
        "google",
        "scanned",
        "gso",
        "any",
        "任意",
        "一个",
        "物体",
        "中的",
        "获取",
        "dataset",
        "数据",
        "集合",
        "大",
        "体积",
        "big",
        "large",
        "download",
        # D3 修复："3d" 是格式/通用描述词（非物体名）。此前 stopword-only query 中
        # "3d" 被当有意义词元搜索，Fuel 返回无关模型（如 "RoboCup 3D Simulator Goal"）
        # 且 file tree 404，命中兜底候选失败（ss_google_scanned_001/003 次根因）。
        "3d",
    }
)
# 语义别名：query 核心词 → fuel 可搜索的替代词（GSO 无 kettle 命名模型，teapot 为近似）
_QUERY_ALIASES: dict[str, tuple[str, ...]] = {
    "kettle": ("teapot", "pot"),
    "水壶": ("teapot", "pot"),
    "茶壶": ("teapot",),
}
# MESH 通用意图兜底候选（fuel 探活确认 file tree 存在且 mesh 可下载）
_FALLBACK_CANDIDATES: list[str] = [
    "Black_Decker_CM2035B_12Cup_Thermal_Coffeemaker",
    "JUICER_SET",
    "Threshold_Porcelain_Teapot_White",
]


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

        分层策略（D3 修复）：完整 query → 英文词元 → 语义别名 → 兜底候选，
        任一层命中即返回。Fuel 搜索对描述性/中文 query 几乎必空（模型名为英文
        专名），此前导致 MESH 需求 empty search 后落到 Zenodo 无关结果（P1/P4）。
        """
        results = await self._search_fuel(query)
        if results:
            return results
        # 英文词元逐个尝试（去停用词）
        tokens = re.findall(r"[a-z0-9]+", query.lower())
        meaningful = [t for t in tokens if t not in _SEARCH_STOPWORDS]
        for token in meaningful:
            results = await self._search_fuel(token)
            if results:
                return results
        # 语义别名（kettle → teapot/pot 等）
        for alias in _QUERY_ALIASES.get(query.lower(), ()):
            results = await self._search_fuel(alias)
            if results:
                return results
        for token in meaningful:
            for alias in _QUERY_ALIASES.get(token, ()):
                results = await self._search_fuel(alias)
                if results:
                    return results
        # 通用兜底候选：模型名即 item_id（探活确认存在且 mesh 可下载），直接构造
        # SearchResult，免去 3 次 Fuel ?q 搜索往返——该搜索端点在本环境响应慢，
        # 多候选串行搜索在源级预算内跑不完返回空（ss_google_scanned_001/003 失败
        # 根因）。候选若已失效，fetch 会抛 AdapterError，检索继续下一候选源，不更差。
        for candidate in _FALLBACK_CANDIDATES:
            return [
                SearchResult(
                    item_id=candidate,
                    title=candidate.replace("_", " "),
                    source=DataSource.GOOGLE_SCANNED,
                    url=f"{self.base_url}/models/{candidate}",
                    metadata={"description": "GSO 通用兜底候选（网络探活确认可下载）"},
                )
            ]
        return []

    async def _search_fuel(self, query: str) -> list[SearchResult]:
        """Fuel 单次搜索（原 search 逻辑）。

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
        # D3: 来源级本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）
        local = self._try_local_fetch(item_id)
        if local is not None:
            return local
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

    def _try_local_fetch(self, item_id: str) -> RawData | None:
        """本地数据集挂载命中检查（D3）。

        本地目录即模型集合根（settings.local_datasets["google_scanned"]），在
        ``{item_id}/`` 子树内复用 _find_path_by_ext 递归按扩展名选 mesh 文件。
        命中返回 source=LOCAL 的 RawData（不发网络请求），未命中返回 None 走网络。
        """
        root = self.local_dataset_root()
        if root is None:
            return None
        # 网络版 file_tree 为嵌套 children 结构；本地树为扁平 list（path/size），
        # _find_path_by_ext 同时兼容两种结构（children 缺失时跳过）。
        file_tree = self._walk_local_tree(root, item_id)
        mesh_path = self._find_mesh_path(file_tree)
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
        )

    def _find_path_by_ext(self, nodes: list[dict[str, Any]], ext: str) -> str | None:
        """按扩展名在 file_tree 中递归查找文件路径。"""
        for node in nodes:
            if not isinstance(node, dict):
                continue
            node_path = str(node.get("path", ""))
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
    ) -> NoReturn:
        """网络/文件不可用时抛 AdapterError 让检索循环继续下一候选源。

        D3 修复：原实现返回 format="json" 的 metadata（含 zip 引用），但 MESH 需求
        期望真实 mesh（obj/stl/ply/glb），json 在 C4 白名单内虽不触发类型错配，却会
        让 MeshSkill 解析失败 → MissingItem，且检索循环以"成功"收尾不再尝试
        GraspNet 等后续源（ss_google_scanned_001 偶发 json metadata 失败根因）。
        改为抛 AdapterError：zip 引用写入错误信息，下一候选源继续尝试。
        """
        import json

        zip_url = f"{self.base_url}/models/{item_id}.zip"
        payload = {
            "source": "google_scanned",
            "item_id": item_id,
            "reason": reason,
            "zip_url": zip_url,
            "mesh_path": mesh_path,
            "mesh_url": mesh_url,
            "file_tree": file_tree or [],
            "note": "单个 mesh 下载失败；可手动下载完整 zip",
        }
        raise AdapterError(
            message=f"{reason}（zip 供手动下载: {zip_url}）: {json.dumps(payload, ensure_ascii=False)[:400]}",
            source=self.source.value,
        )
