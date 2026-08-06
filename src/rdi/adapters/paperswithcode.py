# src/rdi/adapters/paperswithcode.py
"""Papers with Code 论文-代码关联源 Adapter。

文档原始对接方式：网页解析（BeautifulSoup 解析 paperswithcode.com 搜索页）
降级回退方式：REST API（/search/ 和 /papers/ 端点，返回 JSON）
无需 API Key。

E5 修复：paperswithcode.com 在国内受 Cloudflare 反爬 + 访问慢，主源失败时
自动 fallback 到 OpenAlex（免费、无需 key、国内可达，~1.2s 响应）。
OpenAlex 不提供 paper-code 关联，fallback 结果的 code_url 为空。
"""

import asyncio
import json
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# C12 + E5 修复：paperswithcode.com 受 Cloudflare 反爬 + 国内访问慢，
# 基类 _request 用 adapter_timeout（默认 120s），探活 25s 外部超时会先杀掉进程，
# 表现为 search hang 满 25s。这里给 paperswithcode 一个独立的短超时（10s），
# 超时即转 AdapterError，让上层显式失败而非看起来卡死。
_PWC_REQUEST_TIMEOUT_S = 10.0


class PapersWithCodeAdapter(BaseAdapter):
    """Papers with Code Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：网页解析 — BeautifulSoup 解析 paperswithcode.com 搜索结果页
    - 路径 B（降级）：REST API — 调用 Papers with Code REST API
    - 路径 C（E5 fallback）：OpenAlex API — PwC 主源失败时兜底（免费、无 key、国内可达）
    """

    source = DataSource.PAPERSWITHCODE

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.paperswithcode_base_url,
            rate_limit=5,
        )
        self._web_url = settings.paperswithcode_web_url
        # E5 修复：OpenAlex fallback 源（PwC 受 Cloudflare 限制时兜底）
        self._openalex_base_url = settings.openalex_base_url

    async def _pwc_request(self, method: str, path: str, **kwargs: Any) -> Any:
        """带独立短超时的 _request 包装。

        C12 + E5：paperswithcode.com 端点受 Cloudflare 影响，基类 _request 的
        adapter_timeout（默认 120s）过长，探活 25s 外部超时会先杀进程表现为 hang。
        这里用 ``asyncio.wait_for`` 包一层 10s 独立超时，超时即转 AdapterError，
        让 search/fetch 快速失败，避免拖满探活外部超时。

        Args:
            method: HTTP 方法
            path: API 路径
            **kwargs: 传递给 _request 的额外参数

        Returns:
            JSON 响应体

        Raises:
            AdapterError: 10s 内未完成（含原 _request 的重试耗尽）
        """
        try:
            return await asyncio.wait_for(
                self._request(method, path, **kwargs),
                timeout=_PWC_REQUEST_TIMEOUT_S,
            )
        except TimeoutError as e:
            raise AdapterError(
                message=(
                    f"PapersWithCode {method} {path} timed out after "
                    f"{_PWC_REQUEST_TIMEOUT_S}s (Cloudflare/网络慢, E5)"
                ),
                source=self.source.value,
            ) from e

    async def _openalex_request(self, path: str, **kwargs: Any) -> Any:
        """OpenAlex API 请求（PwC fallback 源，E5 修复）。

        临时切换 self.base_url 到 OpenAlex，复用基类 _request 的重试/SSL/缓存逻辑。
        OpenAlex 国内可达且响应快（~1.2s），不受 Cloudflare 限制。

        Args:
            path: OpenAlex API 路径（如 ``/works``、``/works/W123``）
            **kwargs: 传递给 _request 的额外参数

        Returns:
            JSON 响应体

        Raises:
            AdapterError: 请求失败
        """
        saved_base = self.base_url
        self.base_url = self._openalex_base_url
        try:
            return await self._request("GET", path, **kwargs)
        finally:
            self.base_url = saved_base

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Papers with Code 论文。

        C12 修复：跳过网页抓取主源（paperswithcode.com 受 Cloudflare 反爬 +
        国内访问极慢，主源 hang 满超时才走 fallback），直接走 REST API。
        C12 + E5 修复：用 _pwc_request 包 10s 独立超时，避免 search hang 满 25s。
        E5 修复：PwC 主源失败时 fallback 到 OpenAlex（免费、无 key、国内可达）。
        """
        try:
            data = await self._pwc_request("GET", "/search/", params={"q": query})
            return self._parse_search_results(data)
        except AdapterError as pwc_err:
            # E5：PwC 受 Cloudflare 限制，fallback 到 OpenAlex
            if not self._openalex_base_url:
                raise
            try:
                data = await self._openalex_request(
                    "/works", params={"search": query, "per-page": "10"}
                )
                return self._parse_openalex_search_results(data)
            except AdapterError:
                # 双路径均失败，抛 PwC 原异常（符合项目约束）
                raise pwc_err from None

    async def fetch(self, paper_id: str) -> RawData:
        """获取论文详情及代码关联。

        C12 修复：跳过网页抓取主源，直接走 REST API。
        C12 + E5 修复：用 _pwc_request 包 10s 独立超时。
        E5 修复：PwC 主源失败时 fallback 到 OpenAlex（无 code 关联，仅论文详情）。
        """
        try:
            paper_data = await self._pwc_request("GET", f"/papers/{paper_id}")
        except AdapterError as pwc_err:
            # E5：PwC 受 Cloudflare 限制，fallback 到 OpenAlex
            if not self._openalex_base_url:
                raise
            try:
                data = await self._openalex_request(f"/works/{paper_id}")
                return self._build_openalex_rawdata(data, paper_id)
            except AdapterError:
                # 双路径均失败，抛 PwC 原异常
                raise pwc_err from None

        implementations: list[Any] = []
        implementations_fetch_failed = False
        try:
            implementations_data = await self._pwc_request(
                "GET", f"/papers/{paper_id}/implementations/"
            )
            implementations = implementations_data.get("results", [])
        except AdapterError:
            # implementations 接口失败不阻塞 fetch 主流程，但在 metadata 标记
            implementations_fetch_failed = True
        combined = {
            "paper": paper_data,
            "implementations": implementations,
            "metadata": {
                "implementations_fetch_failed": implementations_fetch_failed,
            },
        }
        raw_bytes = json.dumps(combined, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.PAPERSWITHCODE,
            item_id=paper_id,
            format="json",
            data=raw_bytes,
            url=f"{self.base_url}/papers/{paper_id}",
            size_bytes=len(raw_bytes),
        )

    @staticmethod
    def _parse_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析 Papers with Code REST API 搜索返回的 JSON 数据。"""
        results: list[SearchResult] = []
        for item in data.get("results", []):
            paper = item.get("paper", item)
            paper_id = paper.get("id", "")
            title = paper.get("title", "")
            code_url = ""
            framework = ""
            repo = paper.get("repository", {})
            if repo:
                code_url = repo.get("url", "")
                framework = repo.get("framework", "")
            results.append(
                SearchResult(
                    item_id=paper_id,
                    title=title,
                    source=DataSource.PAPERSWITHCODE,
                    url=paper.get("url", f"https://paperswithcode.com/paper/{paper_id}"),
                    metadata={
                        "paper_id": paper_id,
                        "code_url": code_url,
                        "framework": framework,
                    },
                )
            )
        return results

    @staticmethod
    def _extract_openalex_work_id(id_url: str) -> str:
        """从 OpenAlex 完整 ID URL 提取 work ID。

        OpenAlex 返回的 id 格式为 ``https://openalex.org/W1820657498``，
        fetch 需用 ``W1820657498`` 部分作为路径参数。

        Args:
            id_url: OpenAlex work 的完整 ID URL

        Returns:
            work ID 字符串（如 ``W1820657498``），解析失败返回原字符串
        """
        if not id_url:
            return ""
        # 取 URL 最后一段（/ 后部分）
        return id_url.rsplit("/", 1)[-1]

    @staticmethod
    def _parse_openalex_search_results(data: dict[str, Any]) -> list[SearchResult]:
        """解析 OpenAlex search 返回的 JSON 数据。

        OpenAlex 不提供 paper-code 关联，code_url/framework 为空。
        metadata 标记 ``source: "openalex"`` 以区分来源。
        """
        results: list[SearchResult] = []
        for w in data.get("results", []):
            work_id = PapersWithCodeAdapter._extract_openalex_work_id(
                w.get("id", "")
            )
            title = w.get("title", "")
            doi = w.get("doi", "") or ""
            results.append(
                SearchResult(
                    item_id=work_id,
                    title=title,
                    source=DataSource.PAPERSWITHCODE,
                    url=w.get("id", ""),
                    pdf_url=None,
                    metadata={
                        "paper_id": work_id,
                        "code_url": "",  # OpenAlex 不提供 code 关联
                        "framework": "",
                        "source": "openalex",  # 标记来源
                        "doi": doi,
                        "cited_by_count": w.get("cited_by_count", 0),
                        "publication_year": w.get("publication_year"),
                    },
                )
            )
        return results

    def _build_openalex_rawdata(
        self, data: dict[str, Any], paper_id: str
    ) -> RawData:
        """从 OpenAlex work 数据构建 RawData（fetch fallback）。

        OpenAlex 仅提供论文详情，无 code 关联，implementations 为空。
        """
        combined = {
            "paper": {
                "id": paper_id,
                "title": data.get("title", ""),
                "doi": data.get("doi", "") or "",
                "openalex_id": data.get("id", ""),
                "cited_by_count": data.get("cited_by_count", 0),
                "publication_year": data.get("publication_year"),
                "type": data.get("type", ""),
                "open_access": data.get("open_access", {}),
            },
            "implementations": [],  # OpenAlex 不提供 code 关联
            "metadata": {
                "source": "openalex",
                "note": "PwC unavailable (Cloudflare/网络), fallback to OpenAlex",
            },
        }
        raw_bytes = json.dumps(combined, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.PAPERSWITHCODE,
            item_id=paper_id,
            format="json",
            data=raw_bytes,
            url=f"{self._openalex_base_url}/works/{paper_id}",
            size_bytes=len(raw_bytes),
        )

