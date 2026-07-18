"""
arXiv 数据下载脚本

功能：
- 搜索抓取领域代表性论文（50篇）
- 下载论文元数据（JSON）和PDF
- 支持多个关键词搜索

数据源：arXiv
官方地址：http://export.arxiv.org/api/query
对接方式：REST API（Atom XML）
数据格式：Atom XML（元数据）、PDF（论文）
认证需求：无

输出目录：data/sources/api/arxiv/
预估大小：~200 MB（50篇PDF）

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import ProgressTracker, download_file, get_data_dir

# ─── 搜索关键词 ───
SEARCH_KEYWORDS = [
    "robot grasping",
    "6-DOF grasp",
    "dexterous manipulation",
    "dexterous hand grasping",
]

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}


class ArxivDownloader:
    """arXiv 论文下载器。"""

    BASE_URL = "https://export.arxiv.org/api/query"

    def __init__(self, max_papers: int = 50):
        self.max_papers = max_papers
        self.output_dir = get_data_dir() / "api" / "arxiv"
        self.metadata_dir = self.output_dir / "metadata"
        self.pdfs_dir = self.output_dir / "pdfs"

    def _parse_entries(self, xml_text: str) -> list[dict]:
        """解析 arXiv Atom XML，提取论文信息。"""
        entries = []
        try:
            root = ET.fromstring(xml_text)
            for entry in root.findall("atom:entry", ATOM_NS):
                arxiv_id = entry.find("atom:id", ATOM_NS).text.split("/")[-1]
                title = entry.find("atom:title", ATOM_NS).text.strip().replace("\n", " ")
                summary = entry.find("atom:summary", ATOM_NS).text.strip().replace("\n", " ")
                published = entry.find("atom:published", ATOM_NS).text.strip()

                authors = [
                    a.find("atom:name", ATOM_NS).text
                    for a in entry.findall("atom:author", ATOM_NS)
                ]

                categories = [
                    c.get("term")
                    for c in entry.findall("atom:category", ATOM_NS)
                ]

                pdf_link = ""
                for link in entry.findall("atom:link", ATOM_NS):
                    if link.get("title") == "pdf":
                        pdf_link = link.get("href")
                        break

                entries.append({
                    "arxiv_id": arxiv_id,
                    "title": title,
                    "authors": authors,
                    "summary": summary,
                    "published": published,
                    "categories": categories,
                    "pdf_url": pdf_link or f"https://arxiv.org/pdf/{arxiv_id}.pdf",
                })
        except ET.ParseError as e:
            print(f"  [警告] XML解析失败: {e}")

        return entries

    async def search(self, client: httpx.AsyncClient, query: str, max_results: int = 50) -> list[dict]:
        """搜索 arXiv 论文。"""
        params = {
            "search_query": f"all:{query}",
            "max_results": max_results,
            "sortBy": "relevance",
            "sortOrder": "descending",
        }

        try:
            response = await client.get(self.BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            return self._parse_entries(response.text)
        except Exception as e:
            print(f"  [错误] 搜索失败 ({query}): {e}")
            return []

    async def download_paper(self, client: httpx.AsyncClient, paper: dict) -> bool:
        """下载单篇论文的元数据和PDF。"""
        arxiv_id = paper["arxiv_id"]
        safe_id = arxiv_id.replace("/", "_")

        # 保存元数据
        meta_path = self.metadata_dir / f"{safe_id}.json"
        if not meta_path.exists():
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")

        # 下载PDF
        pdf_url = paper["pdf_url"]
        pdf_path = self.pdfs_dir / f"{safe_id}.pdf"
        return await download_file(pdf_url, pdf_path, client)

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        max_papers = 3 if test_mode else self.max_papers
        per_keyword = max(max_papers // len(SEARCH_KEYWORDS), 5)

        print("=" * 60)
        print(f"  arXiv 数据下载 {'[测试模式]' if test_mode else ''}")
        print(f"  目标: {max_papers} 篇论文")
        print("=" * 60)

        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.pdfs_dir.mkdir(parents=True, exist_ok=True)

        all_papers: dict[str, dict] = {}

        async with httpx.AsyncClient() as client:
            # 搜索
            for kw in SEARCH_KEYWORDS:
                print(f"\n搜索关键词: {kw}")
                papers = await self.search(client, kw, per_keyword)
                for p in papers:
                    if p["arxiv_id"] not in all_papers:
                        all_papers[p["arxiv_id"]] = p
                print(f"  找到 {len(papers)} 篇，去重后共 {len(all_papers)} 篇")

                if len(all_papers) >= max_papers:
                    break

            # 截取目标数量
            papers_to_download = list(all_papers.values())[:max_papers]
            print(f"\n开始下载 {len(papers_to_download)} 篇论文...")

            tracker = ProgressTracker(len(papers_to_download), "下载论文")
            success_count = 0

            for paper in papers_to_download:
                ok = await self.download_paper(client, paper)
                if ok:
                    success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(papers_to_download)} 篇成功")
        print(f"元数据目录: {self.metadata_dir}")
        print(f"PDF目录: {self.pdfs_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="arXiv 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式，只下载3篇")
    parser.add_argument("--count", type=int, default=None, help="下载数量（覆盖默认50）")
    args = parser.parse_args()

    count = args.count or config.ARXIV_PAPER_COUNT
    downloader = ArxivDownloader(max_papers=count)
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
