"""
代表性论文 PDF 下载脚本

功能：
- 下载抓取领域10篇经典论文PDF
- 从 arXiv 搜索并下载

数据源：arXiv
对接方式：REST API
数据格式：PDF
认证需求：无

输出目录：data/sources/papers/
预估大小：~100 MB

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

ATOM_NS = {"atom": "http://www.w3.org/2005/Atom"}

# ─── 10篇经典论文（含已知 arXiv ID） ───
PAPER_LIST = [
    {
        "title": "AnyGrasp: Robust and Efficient Grasping with Point Clouds",
        "arxiv_id": "2212.08333",
        "search_query": "AnyGrasp robust efficient grasping point clouds",
    },
    {
        "title": "ContactGraspNet: Efficient 6-DOF Grasp Synthesis",
        "arxiv_id": "2109.05062",
        "search_query": "ContactGraspNet efficient 6-DOF grasp synthesis",
    },
    {
        "title": "GraspNet-1Billion: A Large-Scale Benchmark",
        "arxiv_id": "2009.06578",
        "search_query": "GraspNet-1Billion large-scale benchmark grasping",
    },
    {
        "title": "DexGraspNet: A Large-Scale Dexterous Grasping Dataset",
        "arxiv_id": "2206.12964",
        "search_query": "DexGraspNet large-scale dexterous grasping dataset",
    },
    {
        "title": "6-DOF Grasping for Target-driven Object Manipulation",
        "arxiv_id": "1910.13491",
        "search_query": "6-DOF grasping target-driven object manipulation",
    },
    {
        "title": "Robot Learning of Grasping with Deep Reinforcement Learning",
        "arxiv_id": "",
        "search_query": "robot grasping deep reinforcement learning",
    },
    {
        "title": "Grasp Planning via Deep Learning",
        "arxiv_id": "",
        "search_query": "grasp planning deep learning",
    },
    {
        "title": "Multi-Fingered Grasping with Tactile Feedback",
        "arxiv_id": "",
        "search_query": "multi-fingered grasping tactile feedback",
    },
    {
        "title": "Sim-to-Real Transfer for Robotic Manipulation",
        "arxiv_id": "",
        "search_query": "sim-to-real transfer robotic manipulation grasping",
    },
    {
        "title": "Learning to Grasp with Visual Servoing",
        "arxiv_id": "",
        "search_query": "learning grasp visual servoing robot",
    },
]


class PapersDownloader:
    """代表性论文下载器。"""

    BASE_URL = "http://export.arxiv.org/api/query"

    def __init__(self):
        self.output_dir = get_data_dir() / "papers"

    async def find_arxiv_id(
        self, client: httpx.AsyncClient, search_query: str
    ) -> str:
        """通过搜索查找论文的 arXiv ID。"""
        params = {
            "search_query": f"all:{search_query}",
            "max_results": 1,
        }

        try:
            response = await client.get(self.BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            entries = root.findall("atom:entry", ATOM_NS)

            if entries:
                entry = entries[0]
                arxiv_id = entry.find("atom:id", ATOM_NS).text.split("/")[-1]
                title = entry.find("atom:title", ATOM_NS).text.strip().replace("\n", " ")
                print(f"    找到: {title[:60]}...")
                return arxiv_id

        except Exception as e:
            print(f"    [错误] 搜索失败: {e}")

        return ""

    async def download_paper(
        self, client: httpx.AsyncClient, paper: dict
    ) -> bool:
        """下载单篇论文 PDF。"""
        title = paper["title"]
        arxiv_id = paper.get("arxiv_id", "")

        # 如果没有已知 arXiv ID，通过搜索查找
        if not arxiv_id:
            print(f"  搜索: {title[:50]}...")
            arxiv_id = await self.find_arxiv_id(client, paper["search_query"])

        if not arxiv_id:
            print(f"  [跳过] 未找到: {title[:50]}")
            return False

        # 生成安全文件名
        safe_name = title.split(":")[0].strip().replace(" ", "_").replace("/", "_")[:40]
        pdf_path = self.output_dir / f"{safe_name}.pdf"

        # 下载 PDF
        pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
        ok = await download_file(pdf_url, pdf_path, client)

        if ok:
            # 保存元数据
            meta = {**paper, "arxiv_id": arxiv_id, "pdf_url": pdf_url}
            meta_path = self.output_dir / f"{safe_name}.json"
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

        return ok

    async def run(self) -> None:
        """执行完整下载流程。"""
        print("=" * 60)
        print("  代表性论文 PDF 下载")
        print(f"  目标: {len(PAPER_LIST)} 篇经典论文")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            tracker = ProgressTracker(len(PAPER_LIST), "下载论文")
            success_count = 0

            for paper in PAPER_LIST:
                print(f"\n  [{PAPER_LIST.index(paper) + 1}/{len(PAPER_LIST)}] {paper['title'][:50]}...")
                ok = await self.download_paper(client, paper)
                if ok:
                    success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(PAPER_LIST)} 篇论文成功")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    downloader = PapersDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
