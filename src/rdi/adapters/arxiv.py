# src/rdi/adapters/arxiv.py
"""arXiv 论文源 Adapter。

文档：http://export.arxiv.org/api/query
速率限制：建议每3秒1次请求
无需API Key。
"""

from lxml import etree

from rdi.adapters.base import BaseAdapter
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class ArxivAdapter(BaseAdapter):
    """arXiv API Adapter。"""

    source = DataSource.ARXIV

    def __init__(self) -> None:
        super().__init__(
            base_url="http://export.arxiv.org/api",
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

        Args:
            arxiv_id: arXiv 论文ID（如 "2304.06524"）

        Returns:
            RawData 包含 PDF 二进制数据
        """
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        pdf_bytes = await self._download_bytes(pdf_url)
        return RawData(
            source=DataSource.ARXIV,
            item_id=arxiv_id,
            format="pdf",
            data=pdf_bytes,
            url=pdf_url,
            size_bytes=len(pdf_bytes),
        )

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
