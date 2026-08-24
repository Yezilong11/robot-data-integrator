# src/rdi/adapters/kinova.py
"""Kinova 机械臂 URDF Adapter（D4 新增）。

降级回退方式：GitHub raw URL（Kinovarobotics/ros_kortex 仓库，default_branch=
noetic-devel）直接下载纯 URDF + 随包抓取 mesh 资产。无需 API Key，直接 HTTP。

D4 背景：ms_003（Kinova Gen3 picks up EGAD mug in Isaac Sim）req_000 的
ROBOT_URDF 检索失败——registry 无 kinova 专用 adapter，通用 GitHubAdapter 返回
markdown 被 C4 格式预检拦截，franka/robotiq 明确「有源但未收录 Kinova Gen3」。
本 Adapter 按已知型号（gen3/gen3_lite）token 匹配查询并下载已展开的纯 URDF
（无 xacro 标签），规避 xacro 展开依赖。
"""

import asyncio
import re

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Kinova 已知型号
_FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "gen3", "title": "Kinova Gen3", "description": "7-DOF 协作机械臂"},
    {"id": "gen3_lite", "title": "Kinova Gen3 Lite", "description": "6-DOF 轻量协作臂"},
]

# item_id → (仓库相对路径, format)。均为纯 URDF（无 xacro），可直接下载；
# 网格资产以 package://kortex_description/... 引用（仓库根相对，见 fetch 剥离）
_FETCH_PATHS: dict[str, tuple[str, str]] = {
    "gen3": (
        "kortex_description/arms/gen3/6dof/urdf/GEN3-6DOF_VISION_URDF_ARM_V01.urdf",
        "urdf",
    ),
    "gen3_lite": (
        "kortex_description/arms/gen3_lite/6dof/urdf/GEN3-LITE.urdf",
        "urdf",
    ),
}


class KinovaAdapter(BaseAdapter):
    """Kinova 机械臂 Adapter（直连已知型号的纯 URDF 下载）。"""

    source = DataSource.KINOVA

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.kinova_base_url,
            rate_limit=5,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Kinova 机械臂模型。token 级匹配已知型号；无匹配抛 AdapterCatalogError。

        与 franka/robotiq 的 fallback 搜索同语义（D3 修复沿用）：整串口语化 query
        无法命中 id/title 时，按词元交集判定「是否收录」，未收录明确报有源但未收录。
        """
        query_lower = query.lower()
        query_tokens = {t for t in re.findall(r"[a-z0-9]+", query_lower) if len(t) >= 3}
        matched = [
            m
            for m in _FALLBACK_MODELS
            if query_lower in m["id"]
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
            or query_tokens
            & set(
                re.findall(
                    r"[a-z0-9]+",
                    f"{m['id']} {m['title']} {m['description']}".lower(),
                )
            )
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_MODELS)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
        return [
            SearchResult(
                item_id=m["id"],
                title=m["title"],
                source=DataSource.KINOVA,
                url=f"{self.base_url}/{_FETCH_PATHS[m['id']][0]}",
                metadata={"model_name": m["id"], "description": m["description"]},
            )
            for m in matched
        ]

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与网络 URL 路径同构。"""
        entry = _FETCH_PATHS.get(item_id)
        return [entry] if entry else []

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件（含网格资产，数据包自包含，P0-3）。"""
        # D3: 本地挂载目录即 ros_kortex 仓库根镜像，相对路径与 GitHub raw URL 同构
        local = self._local_raw(item_id, self._local_candidates(item_id))
        if local is not None:
            return local
        entry = _FETCH_PATHS.get(item_id)
        if entry is None:
            raise AdapterError(
                message=f"Unknown kinova model: {item_id} (no path mapping)",
                source=self.source.value,
            )
        rel_path, fmt = entry
        url = f"{self.base_url}/{rel_path}"
        data_bytes = await self._download_bytes(url)
        # 网格引用 package://kortex_description/arms/gen3/6dof/meshes/xxx.STL 为
        # 仓库根相对路径（package://<pkg>/ 后的路径即相对仓库根）。仅剥离
        # "package://" 前缀、保留包名 kortex_description/...，保证：1) 资产下载
        # URL = {base_url}/{ref} 可命中真实文件；2) 包内资产落盘 robots/{ref}，
        # URDF 按 robots/ 下相对路径引用可自洽加载。
        data_bytes = re.sub(rb"package://", b"", data_bytes)
        assets, missing_assets = await self._download_assets(data_bytes, self.base_url)
        return RawData(
            source=DataSource.KINOVA,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            assets=assets,
            # P0-C：下载失败的 mesh/texture 引用显性化（无缺失时不写该键，
            # 保持修复前行为不变）；本地挂载分支已在 ``_local_raw`` 写入同键。
            metadata={"assets_missing": missing_assets} if missing_assets else {},
        )

    async def _download_assets(
        self, urdf_bytes: bytes, repo_root_url: str
    ) -> tuple[dict[str, bytes], list[str]]:
        """下载 URDF 中引用的 mesh/texture 资产（仓库根相对路径，并发）。

        引用已剥离 package:// 前缀（如 ``kortex_description/arms/gen3/6dof/
        meshes/base_link.STL``，即仓库根相对路径），直接从仓库根 URL 下载；
        单个资产失败只跳过该资产（不阻塞整体），并把失败引用随返回值透出
        （``missing``），供 fetch 写入 ``RawData.metadata["assets_missing"]``
        显性化缺失（与 ``_download_xml_with_assets`` 的降级策略一致）。

        Returns:
            (assets, missing)：assets 为 引用路径 → 字节；missing 为下载失败的
            引用路径列表（全部成功时为空列表）。
        """
        refs = set(re.findall(rb'<mesh\s+filename="([^"]+)"', urdf_bytes))
        refs |= set(re.findall(rb'<texture\s+filename="([^"]+)"', urdf_bytes))
        refs = {
            ref.decode("utf-8")
            for ref in refs
            if ref and not (ref.startswith((b"http://", b"https://", b"/")) or b"$(" in ref)
        }
        contents = await asyncio.gather(
            *(self._download_bytes(f"{repo_root_url}/{ref}") for ref in refs),
            return_exceptions=True,
        )
        assets: dict[str, bytes] = {}
        missing: list[str] = []
        for ref, content in zip(refs, contents, strict=False):
            if isinstance(content, BaseException):
                missing.append(ref)
            else:
                assets[ref] = content
        return assets, sorted(missing)
