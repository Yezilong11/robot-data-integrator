# src/rdi/adapters/zenodo.py
"""Zenodo 科研数据存储源 Adapter。

文档：https://developers.zenodo.org/
速率限制：匿名用户较宽松，建议配置 ZENODO_TOKEN。
"""

import json
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.adapters.selectors import build_download_guide, select_target_file
from rdi.config.settings import settings
from rdi.models.common import DataReqType, DataSource
from rdi.models.retrieval import RawData, RawReference, SearchResult


class ZenodoAdapter(BaseAdapter):
    """Zenodo API Adapter，搜索和获取科研数据记录。"""

    source = DataSource.ZENODO

    # P1-A: search 接受可选 req_type（按需求类型追加 filetype 过滤）。调用方以
    # `is True` 探测该能力（Mock 自动属性恒非 True，测试 fixture 不误触发）。
    accepts_req_type_search = True

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.zenodo_api_url,
            rate_limit=10,
        )

    async def search(
        self, query: str, req_type: str | DataReqType | None = None
    ) -> list[SearchResult]:
        """搜索 Zenodo 记录。

        2026-08-24 P1-A：Zenodo 仅服务 DATASET/SENSOR_DATA（registry 注册表），
        bestmatch 首命中常为 PDF 论文记录（无 csv/json 候选 → 占位）。按需求
        类型在 query 追加 filetype 过滤把真实数据文件记录浮出：sensor → csv 单
        格式（zip 命中会因 select_target_file 无候选再次占位，故只用 csv）；
        dataset → csv OR zip（Zenodo 结构化数据以 csv 为主，json 几乎无命中）。

        Args:
            query: 搜索词（如 "robot grasp dataset"）
            req_type: 需求类型（DataReqType 或小写字符串），None 不加过滤

        Returns:
            SearchResult 列表，metadata 含 doi、size、created
        """
        req = self._coerce_req_type(req_type)
        q = query
        if req is DataReqType.SENSOR_DATA:
            q = f'{query} AND filetype:"csv"'
        elif req is DataReqType.DATASET:
            q = f'{query} AND (filetype:"csv" OR filetype:"zip")'
        data = await self._request(
            "GET",
            "/records",
            params={"q": q, "sort": "bestmatch"},
        )
        results: list[SearchResult] = []
        for item in data.get("hits", {}).get("hits", []):
            item_id = str(item.get("id", ""))
            md = item.get("metadata") or {}
            title = str(md.get("title") or item.get("title") or "")
            keywords = " ".join(str(k) for k in (md.get("keywords") or []))
            summary = str(md.get("description") or "")[:200]
            # fix4: description = 标题 + 关键词 + 描述摘要，供检索期语义预筛
            # （retrieve_data._pick_semantic_candidate 读 metadata.description）
            # 在 title 不含需求词但关键词/描述含词时（如 IMU 记录标题缺 'IMU'）
            # 仍能按语义打分选对候选。
            search_desc = " ".join(x for x in (title, keywords, summary) if x)
            results.append(
                SearchResult(
                    item_id=item_id,
                    title=title,
                    source=DataSource.ZENODO,
                    url=item.get("links", {}).get("self_html", ""),
                    metadata={
                        "doi": item.get("doi", ""),
                        "size": item.get("files", [{}])[0].get("size", 0)
                        if item.get("files")
                        else 0,
                        "created": item.get("created", ""),
                        "description": search_desc,
                    },
                )
            )
        return results

    async def fetch(self, item_id: str, req_type: str | DataReqType | None = None) -> RawData:
        """获取记录元数据 JSON，并按需求类型定位可下载文件。

        ``record["files"]``（key/link/size/checksum）构造文件树 → ``select_target_file``
        定位目标候选；HEAD 预检体积：≤ ``max_fetch_bytes`` 真实下载并落盘
        （metadata downloaded=True），超限返回 ``RawReference``（link + wget 提示），
        data 保留 record JSON 并注明未下载；无 files/无候选维持原 metadata 返回。

        Args:
            item_id: Zenodo 记录 ID
            req_type: 数据需求类型（DataReqType 枚举或小写字符串），None 走兜底规则

        Returns:
            RawData：小文件返回文件二进制（format=扩展名）；
            超阈值/无文件候选返回 record metadata JSON（format=json）
        """
        record = await self._request("GET", f"/records/{item_id}")
        req = self._coerce_req_type(req_type)
        candidate = self._select_file_candidate(record, req)
        if candidate is None:
            return self._metadata_raw(item_id, record)
        path = str(candidate.get("path") or candidate.get("name") or "")
        ref_url = self._file_url(item_id, candidate, path)
        # HEAD 预检：超限 → RawReference；未知/未超限 → 真实下载落盘
        size = await self._head_content_length(ref_url)
        if size is not None and size > settings.max_fetch_bytes:
            return self._file_reference(item_id, record, candidate, ref_url, size, req)
        cache_id = f"{item_id}/{path}"
        data_bytes = self.load_from_cache(cache_id) if self.is_cached(cache_id) else None
        if data_bytes is None:
            data_bytes = await self._download_bytes(ref_url)
            self.save_to_cache(cache_id, data_bytes)
        fmt = path.rsplit(".", 1)[-1].lower()
        return RawData(
            source=DataSource.ZENODO,
            item_id=item_id,
            format=fmt,
            data=data_bytes,
            url=ref_url,
            size_bytes=len(data_bytes),
            # fix4: title 供装配期语义校验匹配来源标题（registry 透传 source_title）
            # fix4b: description 供装配期语义校验匹配来源描述（registry 透传 source_description）
            metadata={
                "downloaded": True,
                "title": self._record_title(record),
                "description": self._record_description(record),
            },
        )

    @staticmethod
    def _record_description(record: dict[str, Any]) -> str:
        """提取 record 描述摘要（metadata.description，最长 200 字符）。"""
        md = record.get("metadata") or {}
        return str(md.get("description") or "")[:200]

    def _select_file_candidate(
        self, record: dict[str, Any], req: DataReqType | None
    ) -> dict[str, Any] | None:
        """``record["files"]`` 构造文件树经 ``select_target_file`` 定位首个候选。

        files 项映射为 tree 条目：name=key 的 basename、type="file"、path=key、
        url=link（缺失时留空由 ``_file_url`` 兜底）、size=size。树为空或无命中
        候选返回 None（调用方维持 metadata 返回，不抛错）。
        """
        tree = [
            {
                "name": str(f.get("key", "")).rsplit("/", 1)[-1],
                "type": "file",
                "path": str(f.get("key", "")),
                "url": str(f.get("link") or f.get("links", {}).get("self") or ""),
                "size": f.get("size", 0),
            }
            for f in (record.get("files") or [])
            if isinstance(f, dict) and f.get("key")
        ]
        if not tree:
            return None
        candidates = select_target_file(tree, req if req is not None else DataReqType.UNKNOWN)
        return candidates[0] if candidates else None

    @staticmethod
    def _coerce_req_type(req_type: str | DataReqType | None) -> DataReqType | None:
        """把 str/DataReqType/None 归一为 DataReqType；非法字符串返回 None（走兜底规则）。"""
        if isinstance(req_type, DataReqType) or req_type is None:
            return req_type
        try:
            return DataReqType(str(req_type))
        except ValueError:
            return None

    @staticmethod
    def _record_title(record: dict[str, Any]) -> str:
        """提取 record 标题（metadata.title 优先，回退顶层 title）。"""
        md = record.get("metadata") or {}
        return str(md.get("title") or record.get("title") or "")

    @staticmethod
    def _file_url(item_id: str, candidate: dict[str, Any], path: str) -> str:
        """候选下载 URL：优先 files 的 link，缺失时兜底官方下载 URL。"""
        url = str(candidate.get("url") or "")
        return url or f"https://zenodo.org/records/{item_id}/files/{path}?download=1"

    def _metadata_raw(self, item_id: str, record: dict[str, Any]) -> RawData:
        """无 files/无候选：返回 record metadata JSON，并标记 degraded。

        ``metadata.degraded`` 供 retrieve_data 识别"仅元数据/README 降级"交付
        （P1-A）：传感器/数据集需求下此类交付必然被 SensorDataSkill/DatasetSkill
        消费成 <200B 占位，视为本源失败、继续下一候选源更有价值。带真实文件
        引用的 ``_file_reference``（downloaded=False + reference）不在此列。
        """
        content = json.dumps(record, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.ZENODO,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://zenodo.org/records/{item_id}",
            size_bytes=len(content),
            metadata={
                "degraded": "no_file_candidate",
                "title": self._record_title(record),
                "description": self._record_description(record),
            },
        )

    def _file_reference(
        self,
        item_id: str,
        record: dict[str, Any],
        candidate: dict[str, Any],
        ref_url: str,
        size: int,
        req_type: DataReqType | None,
    ) -> RawData:
        """文件超 ``max_fetch_bytes``：构造 RawReference（link + wget 提示）。

        data 保留 record JSON 并注明未下载（downloaded=false + download_guide），
        reference 由 registry 无条件透传到 ParsedItem 供手动获取。
        """
        reason = "超过 max_fetch_bytes 自动下载上限"
        guide = build_download_guide({**candidate, "url": ref_url}, reason, req_type)
        path = str(candidate.get("path") or candidate.get("name") or "")
        file_size = int(candidate.get("size") or size or 0)  # 优先记录声明的 files size
        payload = {
            **record,
            "downloaded": False,
            "file_path": path,
            "file_size": file_size,
            "download_guide": guide,
        }
        content = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.ZENODO,
            item_id=item_id,
            format="json",
            data=content,
            url=f"https://zenodo.org/records/{item_id}",
            size_bytes=len(content),
            metadata={
                "downloaded": False,
                "title": self._record_title(record),
                "description": self._record_description(record),
            },
            reference=RawReference(
                url=ref_url,
                download_hint=guide["method_hint"],
                file_size=file_size,
                reason=reason,
            ),
        )
