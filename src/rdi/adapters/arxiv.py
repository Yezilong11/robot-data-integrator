# src/rdi/adapters/arxiv.py
"""arXiv 论文源 Adapter。

文档：https://export.arxiv.org/api/query
速率限制：建议每3秒1次请求
无需API Key。
注意：必须用 https，国内网络下 http 明文会被阻断/超时。
"""

import io
import json

import fitz  # PyMuPDF（项目依赖，parse_goal 已使用）
from lxml import etree

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, RawReference, SearchResult


class ArxivAdapter(BaseAdapter):
    """arXiv API Adapter。"""

    source = DataSource.ARXIV

    def __init__(self) -> None:
        super().__init__(
            base_url="https://export.arxiv.org/api",
            rate_limit=3,  # arXiv建议每3秒1次
        )

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 arXiv 论文。

        Args:
            query: 搜索词（如 "robot grasping 6-DOF"）

        Returns:
            SearchResult 列表
        """
        params = {
            "search_query": f"all:{query}",
            "max_results": "10",
            "sortBy": "relevance",
        }
        xml_data = await self._request_text("GET", "/query", params=params)
        return self._parse_atom_xml(xml_data)

    async def fetch(self, arxiv_id: str) -> RawData:
        """下载指定论文的 PDF。

        E1 修复：arXiv PDF 常为多 MB，国内 30s 下载超时。
        下载前先 HEAD 预检 Content-Length，超过 ``max_fetch_bytes`` 阈值时
        改返回 metadata JSON（含 url/size/title/abstract），避免下载全量 PDF。
        HEAD 不可得（None）或文件较小时走原下载流程。

        Args:
            arxiv_id: arXiv 论文ID（如 "2304.06524"）

        Returns:
            RawData：小文件返回 PDF 二进制（format=pdf）；
            超阈值返回 metadata JSON（format=json，含 url/size/title/abstract）
        """
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        # E1: HEAD 预检体积，超阈值改返回 metadata
        # arXiv.org 国内下载慢（5MB PDF 常 >30s），用独立的 arxiv_max_fetch_bytes
        # （默认 2MB）而非全局 max_fetch_bytes（50MB），使典型 arXiv PDF 返回 metadata。
        size = await self._head_content_length(pdf_url)
        if size is not None and size > settings.arxiv_max_fetch_bytes:
            return await self._metadata_fallback(arxiv_id, pdf_url, size)
        pdf_bytes = await self._download_bytes(pdf_url)
        if not self._is_valid_pdf(pdf_bytes):
            # Day2：下载到无法打开的 PDF（魔数正确但损坏/截断，前端 "Failed to open
            # stream" 的现场），重试一次；仍无效则显式降级返回 metadata JSON。
            pdf_bytes = await self._download_bytes(pdf_url)
        if not self._is_valid_pdf(pdf_bytes):
            return await self._metadata_fallback(arxiv_id, pdf_url, len(pdf_bytes))
        return RawData(
            source=DataSource.ARXIV,
            item_id=arxiv_id,
            format="pdf",
            data=pdf_bytes,
            url=pdf_url,
            size_bytes=len(pdf_bytes),
        )

    async def _metadata_fallback(self, arxiv_id: str, pdf_url: str, size: int) -> RawData:
        """PDF 不可用（超阈值或下载内容非有效 PDF）时，显式降级返回 metadata JSON。

        包内记录 url/size/title/abstract 与 ``download_hint``（供用户手动获取），
        符合"降级必须显式"的判定口径。
        """
        metadata = await self._fetch_paper_metadata(arxiv_id)
        payload = {
            "url": pdf_url,
            "size_bytes": size,
            "title": metadata.get("title", ""),
            "abstract": metadata.get("abstract", ""),
            "arxiv_id": arxiv_id,
            "note": "PDF unavailable or exceeds max_fetch_bytes; returning metadata only",
        }
        data_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return RawData(
            source=DataSource.ARXIV,
            item_id=arxiv_id,
            format="json",
            data=data_bytes,
            url=pdf_url,
            size_bytes=size,
            # PDF 不可用，记录引用供用户手动获取
            reference=RawReference(
                url=pdf_url,
                file_size=size,
                download_hint=pdf_url,
                reason="PDF unavailable or exceeds max_fetch_bytes; returning metadata only",
            ),
        )

    @staticmethod
    def _is_valid_pdf(data: bytes) -> bool:
        """校验字节是能实际打开的 PDF（PyMuPDF 打开成功且有页）。

        先查 %PDF 魔数（fitz 对无魔数内容可能宽容解析），再真正 open 一次；
        国内网络下可能拿到魔数正确但结构损坏的字节（前端 "Failed to open stream"
        即此场景），仅魔数不足，需实际打开验证。
        """
        if not data.startswith(b"%PDF"):
            return False
        try:
            with fitz.open(stream=io.BytesIO(data), filetype="pdf") as doc:
                return len(doc) > 0
        except Exception:
            return False

    async def _fetch_paper_metadata(self, arxiv_id: str) -> dict[str, str]:
        """通过 arXiv API 获取单篇论文的 title/abstract。

        用于超阈值 fetch 时的 metadata 返回。失败时返回空 dict，
        不阻塞主流程（metadata 字段降级为空字符串）。
        """
        try:
            xml_data = await self._request_text(
                "GET", "/query", params={"id_list": arxiv_id, "max_results": "1"}
            )
        except AdapterError:
            return {}
        results = self._parse_atom_xml(xml_data)
        if not results:
            return {}
        first = results[0]
        return {
            "title": first.title,
            "abstract": first.metadata.get("abstract", ""),
        }

    @staticmethod
    def _parse_atom_xml(xml_str: str) -> list[SearchResult]:
        """解析 arXiv API 返回的 Atom XML。"""
        root = etree.fromstring(xml_str.encode())
        ns = {"atom": "http://www.w3.org/2005/Atom"}

        results: list[SearchResult] = []
        for entry in root.findall("atom:entry", ns):
            arxiv_id_elem = entry.find("atom:id", ns)
            arxiv_id = (
                arxiv_id_elem.text.strip().split("/")[-1]
                if arxiv_id_elem is not None and arxiv_id_elem.text
                else ""
            )

            title_elem = entry.find("atom:title", ns)
            title = (
                " ".join(title_elem.text.split())
                if title_elem is not None and title_elem.text
                else ""
            )

            summary_elem = entry.find("atom:summary", ns)
            abstract = (
                " ".join(summary_elem.text.split())
                if summary_elem is not None and summary_elem.text
                else ""
            )

            published_elem = entry.find("atom:published", ns)
            published = (
                published_elem.text if published_elem is not None and published_elem.text else ""
            )

            authors = [
                name_elem.text
                for author in entry.findall("atom:author", ns)
                if (name_elem := author.find("atom:name", ns)) is not None
                and name_elem.text is not None
            ]

            pdf_url = None
            for link in entry.findall("atom:link", ns):
                if link.get("title") == "pdf":
                    pdf_url = link.get("href")
                    break

            results.append(
                SearchResult(
                    item_id=arxiv_id,
                    title=title,
                    source=DataSource.ARXIV,
                    url=f"https://arxiv.org/abs/{arxiv_id}",
                    pdf_url=pdf_url,
                    metadata={
                        "authors": authors,
                        "abstract": abstract,
                        "published": published,
                    },
                )
            )
        return results
