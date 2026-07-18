"""
IEEE Xplore 数据下载脚本

功能：
- 使用 IEEE API 搜索抓取领域论文（20篇）
- 下载论文元数据（JSON）
- PDF 下载需要订阅权限，脚本提供下载链接

数据源：IEEE Xplore
官方地址：https://ieeexplore.ieee.org/
对接方式：REST API
数据格式：JSON（元数据）、PDF（论文）
认证需求：API Key（必需）

输出目录：data/sources/api/ieee/
预估大小：~100 MB

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import ProgressTracker, download_file, get_data_dir


class IEEEDownloader:
    """IEEE Xplore 论文下载器。"""

    BASE_URL = "https://ieeexploreapi.restfulmicroservices.com/api/search"

    def __init__(self, api_key: str = "", max_papers: int = 20):
        self.api_key = api_key or config.IEEE_API_KEY
        self.max_papers = max_papers
        self.output_dir = get_data_dir() / "api" / "ieee"
        self.metadata_dir = self.output_dir / "metadata"
        self.pdfs_dir = self.output_dir / "pdfs"

    async def search(self, client: httpx.AsyncClient, query: str, max_results: int = 20) -> list[dict]:
        """搜索 IEEE 论文。"""
        if not self.api_key:
            print("  [跳过] 未配置 IEEE_API_KEY，无法搜索")
            return []

        params = {
            "apikey": self.api_key,
            "querytext": query,
            "max_records": max_results,
            "start_record": 1,
            "sort_order": "relevance",
        }

        try:
            response = await client.get(self.BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            papers = []
            for article in data.get("articles", []):
                papers.append({
                    "ieee_id": article.get("articleNumber", ""),
                    "title": article.get("title", ""),
                    "authors": article.get("authors", {}).get("authors", []),
                    "abstract": article.get("abstract", ""),
                    "publication_year": article.get("publicationYear", ""),
                    "doi": article.get("doi", ""),
                    "pdf_url": article.get("pdfUrl", ""),
                    "html_url": article.get("htmlUrl", ""),
                })
            return papers

        except Exception as e:
            print(f"  [错误] IEEE搜索失败: {e}")
            return []

    async def download_paper_metadata(self, client: httpx.AsyncClient, paper: dict) -> bool:
        """下载单篇论文元数据。"""
        ieee_id = paper.get("ieee_id", "unknown")
        meta_path = self.metadata_dir / f"{ieee_id}.json"

        if meta_path.exists():
            print(f"  [跳过] 已存在: {ieee_id}")
            return True

        meta_path.parent.mkdir(parents=True, exist_ok=True)
        meta_path.write_text(json.dumps(paper, ensure_ascii=False, indent=2), encoding="utf-8")

        # PDF 需要订阅权限，仅记录链接
        if paper.get("pdf_url"):
            link_file = self.pdfs_dir / f"{ieee_id}_pdf_url.txt"
            link_file.parent.mkdir(parents=True, exist_ok=True)
            link_file.write_text(paper["pdf_url"], encoding="utf-8")

        return True

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        max_papers = 3 if test_mode else self.max_papers

        print("=" * 60)
        print(f"  IEEE Xplore 数据下载 {'[测试模式]' if test_mode else ''}")
        print("=" * 60)

        if not self.api_key:
            print("\n  [警告] 未配置 IEEE_API_KEY")
            print("  请在 .env 文件中设置 IEEE_API_KEY")
            print("  获取地址: https://developer.ieee.org/")
            return

        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.pdfs_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n搜索关键词: robot grasping")
            papers = await self.search(client, "robot grasping", max_papers)
            print(f"  找到 {len(papers)} 篇论文")

            if not papers:
                print("  未找到论文，请检查 API Key 是否有效")
                return

            tracker = ProgressTracker(len(papers), "下载元数据")
            success_count = 0

            for paper in papers:
                ok = await self.download_paper_metadata(client, paper)
                if ok:
                    success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(papers)} 篇元数据成功")
        print(f"元数据目录: {self.metadata_dir}")
        print(f"PDF链接目录: {self.pdfs_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="IEEE Xplore 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式，只下载3篇")
    args = parser.parse_args()

    downloader = IEEEDownloader(max_papers=config.IEEE_PAPER_COUNT)
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
