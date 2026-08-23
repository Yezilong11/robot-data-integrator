# src/rdi/adapters/huggingface.py
"""HuggingFace 模型/数据集源 Adapter。

文档：https://huggingface.co/docs/hub/api
速率限制：匿名用户受限制，建议配置 HF_TOKEN。
"""

import json
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.adapters.selectors import build_download_guide, select_target_file
from rdi.config.settings import settings
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, RawReference, SearchResult


class HuggingFaceAdapter(BaseAdapter):
    """HuggingFace API Adapter，搜索模型与数据集。"""

    source = DataSource.HUGGINGFACE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.huggingface_api_url,
            rate_limit=10,
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 HuggingFace 模型。

        Args:
            query: 搜索词（如 "robot grasping"）

        Returns:
            SearchResult 列表，metadata 含 downloads、likes、tags
        """
        data = await self._request(
            "GET",
            "/models",
            params={"search": query, "sort": "downloads", "direction": "-1"},
        )
        results: list[SearchResult] = []
        for item in data:
            item_id = item.get("id", "")
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=item.get("modelId", item_id),
                    source=DataSource.HUGGINGFACE,
                    url=f"https://huggingface.co/{item_id}",
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
        req_type: str | None = None,
    ) -> RawData:
        """按数据类型下载模型元数据文件。

        - POLICY_MODEL: 拉取 model_info.json/config.json 元数据后，经 HF tree API
          （/models/{id}/tree/main）定位权重文件：≤ max_fetch_bytes 真实下载落盘，
          超限返回 RawReference 引用
        - 其他类型（默认）: 拉取 ``config.json``

        Args:
            item_id: 模型 ID（如 "bert-base-uncased"）
            req_type: 数据需求类型字符串或 DataReqType（如 POLICY_MODEL），可空

        Returns:
            RawData 包含对应 JSON 元数据
        """
        # C1: 走可配置的下载镜像（默认 hf-mirror.com），避免硬编码 huggingface.co
        download_base = settings.huggingface_download_base_url.rstrip("/")
        # retrieve_data 传 DataReqType 枚举（StrEnum，值小写），统一按值比较
        is_policy = str(req_type).lower() == "policy_model"
        if is_policy:
            return await self._fetch_policy_meta(download_base, item_id)
        config_url = f"{download_base}/{item_id}/resolve/main/config.json"
        content = await self._download_bytes(config_url)
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=config_url,
            size_bytes=len(content),
        )

    async def _fetch_policy_meta(self, download_base: str, item_id: str) -> RawData:
        """POLICY_MODEL 拉取链路：meta JSON + HF tree API 定位权重。

        - meta：model_info.json 优先，404 降级 config.json，均不可用兜底引用 payload
        - 权重：HF tree API（/models/{id}/tree/main）→ select_target_file 定位候选，
          HEAD 预检 ≤ max_fetch_bytes 则真实下载落盘（metadata["downloaded"]=True）；
          超限返回 RawReference（resolve url + wget 提示），data 保留 meta 结构并
          注明未下载；无候选/树 API 失败维持原 metadata 引用行为（PASS_WITH_FALLBACK）。
        """
        # 1) 元数据 JSON（结构与既有行为一致）
        candidates = ["model_info.json", "config.json"]
        last_error = ""
        meta_payload: dict[str, Any] = {}
        meta_url = f"https://huggingface.co/{item_id}"
        for filename in candidates:
            url = f"{download_base}/{item_id}/resolve/main/{filename}"
            try:
                content = await self._download_bytes(url)
            except Exception as exc:  # noqa: BLE001 — 单文件失败继续尝试下一候选
                last_error = str(exc)
                continue
            validated = self._validate_model_info(item_id, content, filename)
            if validated is not None:
                meta_payload = json.loads(validated.decode("utf-8"))
                meta_url = url
                break
        if not meta_payload:
            meta_payload = {
                "model_id": item_id,
                "metadata_only": True,
                "note": f"model_info.json/config.json 均不可用，返回元数据引用: {last_error}",
            }
        # 2) HF tree API 定位权重候选（树失败不阻断 metadata 返回）
        candidate = await self._select_policy_candidate(item_id)
        if candidate is None:
            return self._policy_meta_raw(item_id, meta_payload, meta_url)
        path = str(candidate.get("path") or candidate.get("name") or "")
        ref_url = f"https://huggingface.co/{item_id}/resolve/main/{path.lstrip('/')}"
        # 3) HEAD 预检：超限 → RawReference；未知/未超限 → 真实下载落盘
        size = await self._head_content_length(ref_url)
        if size is not None and size > settings.max_fetch_bytes:
            return self._policy_reference(item_id, meta_payload, candidate, ref_url, size)
        cache_id = f"{item_id}/{path}"
        data_bytes = self.load_from_cache(cache_id) if self.is_cached(cache_id) else None
        if data_bytes is None:
            data_bytes = await self._download_bytes(ref_url)
            self.save_to_cache(cache_id, data_bytes)
        # 与超限分支（_policy_reference）同构：data 返回 meta JSON 并注明已下载 +
        # download_guide（含 resolve url/wget 命令，供手动复现），避免裸权重字节
        # 传入下游 PolicyInterfaceSkill 时 json.loads 失败而降级为空壳文档、
        # 权重本身被丢弃（审查问题 1）。
        guide = build_download_guide(
            {**candidate, "url": ref_url},
            "权重已自动下载（≤ max_fetch_bytes），指引供手动复现",
            DataReqType.POLICY_MODEL,
        )
        payload = {
            **meta_payload,
            "downloaded": True,
            "file_path": path,
            "file_size": size or len(data_bytes),
            "download_guide": guide,
        }
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://huggingface.co/{item_id}",
            size_bytes=len(content),
            metadata={"downloaded": True},
        )

    async def _select_policy_candidate(self, item_id: str) -> dict[str, Any] | None:
        """HF tree API 取文件树，经 select_target_file 返回首个权重候选（无则 None）。

        树请求失败或仓库无权重文件均返回 None（调用方维持 metadata 引用语义，
        不抛错）；tree 条目补 name（由 path 派生），与 select_target_file 的
        输入约定一致（HF tree API 只返回 path/type/size）。
        """
        # 分支回退 main → master（默认分支非 main 的仓库定位失败不算降级，
        # 参照 github._find_urdf_file 的 main→master 回退，审查问题 4）；
        # 两分支均失败返回 None（调用方维持 metadata 引用语义，不抛错）。
        raw_tree: list[dict[str, Any]] | None = None
        for ref in ("main", "master"):
            try:
                raw_tree = await self._request(
                    "GET",
                    f"/models/{item_id}/tree/{ref}",
                    params={"recursive": "true"},
                )
            except Exception:  # noqa: BLE001 — 分支失败继续尝试下一分支
                raw_tree = None
            if raw_tree:
                break
        if not raw_tree:
            return None
        tree = [
            {**entry, "name": str(entry.get("path", "")).rsplit("/", 1)[-1]}
            for entry in raw_tree
            if isinstance(entry, dict)
        ]
        candidates = select_target_file(tree, DataReqType.POLICY_MODEL)
        return candidates[0] if candidates else None

    def _policy_meta_raw(
        self, item_id: str, meta_payload: dict[str, Any], meta_url: str
    ) -> RawData:
        """无权重候选：返回 meta JSON RawData（维持既有 metadata 引用行为）。"""
        content = json.dumps(meta_payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=meta_url,
            size_bytes=len(content),
        )

    def _policy_reference(
        self,
        item_id: str,
        meta_payload: dict[str, Any],
        candidate: dict[str, Any],
        ref_url: str,
        size: int,
    ) -> RawData:
        """权重超 max_fetch_bytes：构造 RawReference（resolve url + wget 提示）。

        data 保留 meta 结构并注明未下载（downloaded=false + download_guide），
        reference 由 registry 无条件透传到 ParsedItem 供手动获取。
        """
        reason = "超过 max_fetch_bytes 自动下载上限"
        guide = build_download_guide(
            {**candidate, "url": ref_url}, reason, DataReqType.POLICY_MODEL
        )
        path = str(candidate.get("path") or candidate.get("name") or "")
        payload = {
            **meta_payload,
            "downloaded": False,
            "file_path": path,
            "file_size": size,
            "download_guide": guide,
        }
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.HUGGINGFACE,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://huggingface.co/{item_id}",
            size_bytes=len(content),
            metadata={"downloaded": False},
            reference=RawReference(
                url=ref_url,
                download_hint=guide["method_hint"],
                file_size=size,
                reason=reason,
            ),
        )

    @staticmethod
    def _validate_model_info(item_id: str, content: bytes, filename: str) -> bytes | None:
        """校验模型元数据内容为合法 JSON dict；非法时返回 None（由调用方继续降级）。"""
        try:
            decoded = json.loads(content.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return None
        if not isinstance(decoded, dict):
            return None
        # config.json 缺少 modelId/tags 等模型标识时补充 item_id，保证下游可识别
        if "modelId" not in decoded and "id" not in decoded and "model_id" not in decoded:
            decoded["model_id"] = item_id
            return json.dumps(decoded, ensure_ascii=False).encode("utf-8")
        return content
