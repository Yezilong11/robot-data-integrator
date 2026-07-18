"""
Papers with Code 数据下载脚本

功能：
- 搜索抓取领域论文-代码关联
- 提取论文链接、代码仓库链接、模型权重链接
- 保存为JSON元数据

数据源：Papers with Code
官方地址：https://paperswithcode.com/
对接方式：网页解析 / API
数据格式：HTML/JSON
认证需求：无

输出目录：data/sources/web/paperswithcode/
预估大小：~10 MB

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
from utils import get_data_dir


class PapersWithCodeDownloader:
    """Papers with Code 数据下载器。"""

    API_BASE = "https://paperswithcode.com/api/v1"

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "paperswithcode" / "papers"

    async def search_papers(
        self, client: httpx.AsyncClient, query: str, limit: int = 50
    ) -> list[dict]:
        """搜索论文。"""
        papers = []
        page = 1

        while len(papers) < limit:
            params = {"q": query, "page": page, "items_per_page": min(50, limit - len(papers))}

            try:
                response = await client.get(
                    f"{self.API_BASE}/search/",
                    params=params,
                    timeout=30.0,
                    follow_redirects=True,
                )

                if response.status_code != 200:
                    print(f"  [警告] API返回 {response.status_code}")
                    break

                data = response.json()
                results = data.get("results", [])

                if not results:
                    break

                for item in results:
                    paper = item.get("paper", {})
                    papers.append({
                        "title": paper.get("title", ""),
                        "abstract": paper.get("abstract", ""),
                        "url_pdf": paper.get("url_pdf", ""),
                        "url_abs": paper.get("url_abs", ""),
                        "conference": paper.get("conference", ""),
                        "published": paper.get("published", ""),
                        "repos": [
                            {
                                "url": repo.get("url", ""),
                                "is_official": repo.get("is_official", False),
                                "framework": repo.get("framework", ""),
                            }
                            for repo in item.get("repositories", [])
                        ],
                    })

                if len(results) < 50:
                    break
                page += 1

            except Exception as e:
                print(f"  [错误] Papers with Code搜索失败: {e}")
                break

        return papers[:limit]

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        limit = 5 if test_mode else 50

        print("=" * 60)
        print(f"  Papers with Code 数据下载 {'[测试模式]' if test_mode else ''}")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n搜索关键词: robot grasping")
            papers = await self.search_papers(client, "robot grasping", limit)
            print(f"  找到 {len(papers)} 篇论文-代码关联\n")

            if not papers:
                print("  尝试更宽泛的关键词...")
                papers = await self.search_papers(client, "grasping", limit)
                print(f"  找到 {len(papers)} 篇\n")

            # 保存所有论文元数据
            output_path = self.output_dir / "metadata.json"
            output_path.write_text(
                json.dumps(papers, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # 统计
            papers_with_code = sum(1 for p in papers if p["repos"])
            total_repos = sum(len(p["repos"]) for p in papers)

            print(f"保存完成: {len(papers)} 篇论文")
            print(f"其中有代码关联: {papers_with_code} 篇")
            print(f"代码仓库总数: {total_repos} 个")
            print(f"输出文件: {output_path}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Papers with Code 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式")
    args = parser.parse_args()

    downloader = PapersWithCodeDownloader()
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
