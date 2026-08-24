# src/rdi/adapters/github.py
"""GitHub 代码与模型源 Adapter。

文档：https://docs.github.com/en/rest
速率限制：认证用户 5000次/小时，未认证 60次/小时
建议配置 GITHUB_TOKEN 环境变量。
"""

import base64
import json
import re
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.adapters.selectors import build_download_guide, select_target_file
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, RawReference, SearchResult

# 走「contents 文件树 → 定位 → HEAD 预检 → 下载/引用」链路的"数据类需求"；
# CODE/PAPER 等非数据需求仍返回 README（不改变既有检索行为）。
_DATA_REQ_TYPES = frozenset({"policy_model", "sensor_data", "grasp", "dataset"})
# contents API 每目录一次调用（未认证 60 次/时），递归深度上限防止异常深目录
# 耗尽速率配额（ponytail: 超深仓库视为无子目录候选，不做无限递归）。
_MAX_TREE_DEPTH = 5
# RawReference 引用原因（与 huggingface/graspnet 超限文案一致）
_REF_REASON = "超过 max_fetch_bytes 自动下载上限"


class GitHubAdapter(BaseAdapter):
    """GitHub API Adapter。

    提供：
    - search: 搜索仓库（按 stars 排序）
    - fetch: 获取仓库 README
    - fetch_releases: 获取 Release 资产（模型权重）
    - fetch_file: 下载仓库指定文件
    """

    source = DataSource.GITHUB

    def __init__(self) -> None:
        super().__init__(
            base_url="https://api.github.com",
            rate_limit=30,
        )
        self.token = settings.github_token

    @property
    def headers(self) -> dict[str, str]:
        """请求头，含 GitHub API 版本和可选 Token。"""
        h: dict[str, str] = {"Accept": "application/vnd.github.v3+json"}
        if self.token:
            h["Authorization"] = f"token {self.token}"
        return h

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 GitHub 仓库。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表，按 stars 降序
        """
        data = await self._request(
            "GET",
            "/search/repositories",
            params={"q": query, "sort": "stars", "order": "desc"},
            headers=self.headers,
        )
        return [
            SearchResult(
                item_id=repo["full_name"],
                title=repo["name"],
                source=DataSource.GITHUB,
                url=repo["html_url"],
                metadata={
                    "stars": repo["stargazers_count"],
                    "description": repo.get("description", ""),
                    "language": repo.get("language", ""),
                    "topics": repo.get("topics", []),
                },
            )
            for repo in data.get("items", [])
        ]

    async def fetch(self, repo_name: str, req_type: str | None = None) -> RawData:
        """获取仓库内容。

        - ROBOT_URDF 需求：从仓库文件树定位 ``.urdf`` 文件并下载（避免拿到 README
          markdown 导致类型错配）；无 URDF 时回退 README
        - 数据类需求（POLICY_MODEL/SENSOR_DATA/GRASP/DATASET）：contents API 列仓库
          文件树 → select_target_file 定位候选 → HEAD 预检体积：≤ max_fetch_bytes
          真实下载落盘（downloaded=True）；超限返回 RawReference 引用（wget 提示）
        - 其他/默认：获取仓库 README 内容

        Args:
            repo_name: 仓库全名（如 "NVlabs/6-DOF-GraspNet"）
            req_type: 数据需求类型（DataReqType 枚举或值字符串），可空

        Returns:
            RawData 包含 README markdown、URDF 二进制或目标数据文件

        Raises:
            AdapterError: 获取失败
        """
        req = str(req_type).lower()
        if req == "robot_urdf":
            found = await self._find_urdf_file(repo_name)
            if found is not None:
                urdf_path, ref = found
                data_bytes = await self.fetch_file(repo_name, urdf_path, ref=ref)
                # D4 修复：URDF 随包抓取引用的外部网格/texture 资产（数据包自包含，
                # P0-3）。此前只下载 URDF 字节，包内无 mesh，yourdfpy 加载报 11 处
                # 'Unable to resolve filename: package://meshes/...'（ss_franka_002/003
                # 网格缺失根因，与 FrankaAdapter 的 _fetch_* 同模式）。
                raw_url = f"https://raw.githubusercontent.com/{repo_name}/{ref}/{urdf_path}"
                assets, missing_assets = await self._download_xml_with_assets(raw_url, data_bytes)
                # 与 franka 等源一致：剥离 package:// 前缀，使网格引用与资产键
                # （_resolve_asset_rel 剥离后的相对路径）一致，离线可加载。
                data_bytes = re.sub(rb"package://", b"", data_bytes)
                return RawData(
                    source=DataSource.GITHUB,
                    item_id=repo_name,
                    format="urdf",
                    data=data_bytes,
                    url=raw_url,
                    size_bytes=len(data_bytes),
                    assets=assets,
                    metadata={"assets_missing": missing_assets} if missing_assets else {},
                )
        # 数据类需求走「contents 树 → 定位 → HEAD 预检 → 下载/引用」链路；
        # 无候选/树不可用时回退 README（保持 fetch 稳定，不抛错）。
        if req in _DATA_REQ_TYPES:
            data_raw = await self._fetch_data_file(repo_name, req)
            if data_raw is not None:
                return data_raw
        data = await self._request(
            "GET",
            f"/repos/{repo_name}/readme",
            headers=self.headers,
        )
        readme_bytes = base64.b64decode(data["content"])
        return RawData(
            source=DataSource.GITHUB,
            item_id=repo_name,
            format="markdown",
            data=readme_bytes,
            url=data.get("html_url", ""),
            size_bytes=len(readme_bytes),
            # P1-A：明确标记"无数据候选回退 README"（CODE/PAPER 等非数据需求
            # 的 README 交付不受影响），供 retrieve_data 对 SENSOR_DATA 判定
            # 本源失败、继续下一候选源（如 Zenodo），避免消费成 <200B 占位。
            metadata={
                "degraded": "readme_fallback",
                "title": repo_name,
            },
        )

    async def _fetch_data_file(self, repo_name: str, req_type: str) -> RawData | None:
        """数据类需求的「文件树 → 定位 → HEAD 预检 → 下载/引用」链路。

        经 contents API 递归列树，select_target_file 定位目标候选；HEAD 预检
        ≤ max_fetch_bytes 则真实下载落盘（metadata["downloaded"]=True），超限
        返回 RawReference 引用（download_url/wget 提示，Reference 由 registry
        透传到 ParsedItem），data 保留本库统一引用 payload 结构并注明未下载。

        返回 None 表示无候选/树不可用（调用方回退 README，不抛错）。
        """
        try:
            req_enum = DataReqType(req_type)
        except ValueError:
            return None
        try:
            tree = await self._list_contents_tree(repo_name)
        except AdapterError:
            return None
        candidates = select_target_file(tree, req_enum)
        if not candidates:
            return None
        candidate = candidates[0]
        path = str(candidate.get("path") or candidate.get("name") or "")
        # 优先 contents API 的 download_url；缺省时用 raw.githubusercontent 直链
        url = str(
            candidate.get("url") or f"https://raw.githubusercontent.com/{repo_name}/HEAD/{path}"
        )
        contents_size = int(candidate.get("size") or 0)
        # HEAD 预检：超限 → RawReference；HEAD 未知视为未超限 → 真实下载
        head_size = await self._head_content_length(url)
        if head_size is not None and head_size > settings.max_fetch_bytes:
            return self._data_reference(
                repo_name,
                candidate,
                url,
                contents_size or head_size,
                req_enum,
            )
        cache_id = f"{repo_name}/{path}"
        data_bytes = self.load_from_cache(cache_id) if self.is_cached(cache_id) else None
        if data_bytes is None:
            data_bytes = await self._download_bytes(url)
            self.save_to_cache(cache_id, data_bytes)
        # POLICY_MODEL：与 HF success 分支同构，data 返回 meta JSON（含
        # download_guide + downloaded=true），不传裸权重字节——权重内容按产品
        # 原则不在本地解析（policy_interface 对无法 json 解析的字节会降级为空壳）。
        # 其余数据类需求保持原始字节交付（csv/npz 等需 skill 解析内容）。
        if req_enum == DataReqType.POLICY_MODEL:
            guide = build_download_guide(
                {**candidate, "url": url},
                "权重已自动下载（≤ max_fetch_bytes），指引供手动复现",
                req_enum,
            )
            payload: dict[str, Any] = {
                "model_id": repo_name,
                "repo": repo_name,
                "file_path": path,
                "downloaded": True,
                "file_size": len(data_bytes),
                "download_guide": guide,
            }
            content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            return RawData(
                source=DataSource.GITHUB,
                item_id=repo_name,
                format="json",
                data=content,
                url=url,
                size_bytes=len(content),
                metadata={"downloaded": True, "title": repo_name},
            )
        fmt = path.rsplit(".", 1)[-1].lower() if "." in path else "bin"
        return RawData(
            source=DataSource.GITHUB,
            item_id=repo_name,
            format=fmt,
            data=data_bytes,
            url=url,
            size_bytes=len(data_bytes),
            metadata={"downloaded": True, "title": repo_name},
        )

    async def _list_contents_tree(
        self, repo_name: str, path: str = "", depth: int = 0
    ) -> list[dict[str, Any]]:
        """递归列出仓库文件树（GitHub contents API）。

        contents API 不递归（每层目录一次调用）；条目保留 type/file|dir、name、
        path、size，并把 download_url 映射为 ``url`` 字段，与 select_target_file /
        build_download_guide 的输入约定一致。子目录列表失败跳过不阻断；根目录
        失败抛 AdapterError（由调用方回退 README）。
        """
        entries = await self._request(
            "GET",
            f"/repos/{repo_name}/contents/{path}".rstrip("/"),
            headers=self.headers,
        )
        if not isinstance(entries, list):
            return []
        tree: list[dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            tree.append({**item, "url": str(item.get("download_url") or "")})
            if item.get("type") == "dir" and depth < _MAX_TREE_DEPTH:
                sub_path = str(item.get("path") or "")
                try:
                    tree.extend(await self._list_contents_tree(repo_name, sub_path, depth + 1))
                except AdapterError:
                    continue
        return tree

    def _data_reference(
        self,
        repo_name: str,
        candidate: dict[str, Any],
        url: str,
        file_size: int,
        req_enum: DataReqType,
    ) -> RawData:
        """候选文件超 max_fetch_bytes：构造 RawReference（download_url + wget 提示）。

        data 保留引用 payload 结构（downloaded=False + download_guide），
        reference 字段由 registry 无条件透传到 ParsedItem 供手动获取。
        """
        guide = build_download_guide({**candidate, "url": url}, _REF_REASON, req_enum)
        path = str(candidate.get("path") or candidate.get("name") or "")
        payload: dict[str, Any] = {
            "repo": repo_name,
            "file_path": path,
            "downloaded": False,
            "file_size": file_size,
            "download_guide": guide,
        }
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.GITHUB,
            item_id=repo_name,
            format="json",
            data=content,
            url=f"https://github.com/{repo_name}",
            size_bytes=len(content),
            metadata={"downloaded": False, "title": repo_name},
            reference=RawReference(
                url=url,
                download_hint=guide["method_hint"],
                file_size=file_size,
                reason=_REF_REASON,
            ),
        )

    async def _find_urdf_file(self, repo_name: str) -> tuple[str, str] | None:
        """递归列出仓库文件树，返回首个 ``.urdf``/``.xacro`` 文件的 (路径, 分支)；无则 None。

        D4 修复：GitHub ``git/trees`` API 固定查 ``main`` 分支对默认分支非 main 的
        仓库（如 ``Kinovarobotics/ros_kortex`` default_branch=noetic-devel）抛 404
        AdapterError，导致 Kinova 等仓库永远回退 README（ms_003 req_000 P2_RETRIEVE
        根因）。改为分支回退：main → master → 仓库 default_branch（``/repos/{repo}``
        API 探测），任一分支找到 URDF 即返回。tree 过大被截断（truncated）时视为
        该分支无结果，继续下一分支。
        """
        for ref in ("main", "master"):
            found = await self._urdf_in_branch(repo_name, ref)
            if found is not None:
                return found, ref
        # 默认分支探测（避免额外 API 调用：main/master 均无结果时才请求）
        default_ref = ""
        try:
            repo_info = await self._request(
                "GET",
                f"/repos/{repo_name}",
                headers=self.headers,
            )
            default_ref = str(repo_info.get("default_branch") or "")
        except AdapterError:
            return None
        if default_ref and default_ref not in ("main", "master"):
            found = await self._urdf_in_branch(repo_name, default_ref)
            if found is not None:
                return found, default_ref
        return None

    async def _urdf_in_branch(self, repo_name: str, ref: str) -> str | None:
        """列出指定分支文件树，返回首个 .urdf/.xacro 路径；无/失败/截断返回 None。"""
        try:
            tree_data = await self._request(
                "GET",
                f"/repos/{repo_name}/git/trees/{ref}?recursive=1",
                headers=self.headers,
            )
        except AdapterError:
            return None
        if tree_data.get("truncated"):
            return None
        for entry in tree_data.get("tree", []):
            if not isinstance(entry, dict) or entry.get("type") != "blob":
                continue
            path = str(entry.get("path", ""))
            lower = path.lower()
            if lower.endswith(".urdf") or lower.endswith(".xacro"):
                return path
        return None

    async def fetch_releases(self, repo_name: str) -> list[dict[str, Any]]:
        """获取 Release 资产（模型权重、预训练文件）。

        Args:
            repo_name: 仓库全名

        Returns:
            资产列表，每个包含 release_tag, name, url, size
        """
        data = await self._request(
            "GET",
            f"/repos/{repo_name}/releases",
            headers=self.headers,
        )
        assets: list[dict[str, Any]] = []
        for release in data:
            for asset in release.get("assets", []):
                assets.append(
                    {
                        "release_tag": release["tag_name"],
                        "name": asset["name"],
                        "url": asset["browser_download_url"],
                        "size": asset["size"],
                    }
                )
        return assets

    async def fetch_file(self, repo_name: str, file_path: str, ref: str = "main") -> bytes:
        """下载仓库中的指定文件。

        Args:
            repo_name: 仓库全名
            file_path: 文件路径（相对于仓库根目录）
            ref: Git 引用（分支/标签），默认 main

        Returns:
            文件二进制内容
        """
        url = f"https://raw.githubusercontent.com/{repo_name}/{ref}/{file_path}"
        return await self._download_bytes(url)
