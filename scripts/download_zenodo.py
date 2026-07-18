"""
Zenodo 数据下载脚本

功能：
- 搜索抓取领域相关科研数据集（10个）
- 下载记录元数据
- 下载数据文件（小型文件）

数据源：Zenodo
官方地址：https://zenodo.org/
对接方式：REST API
数据格式：多种（CSV/JSON/二进制等）
认证需求：无

输出目录：data/sources/api/zenodo/
预估大小：~500 MB

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


class ZenodoDownloader:
    """Zenodo 科研数据集下载器。"""

    BASE_URL = "https://zenodo.org/api/records"

    def __init__(self, max_records: int = 10):
        self.max_records = max_records
        self.output_dir = get_data_dir() / "api" / "zenodo"
        self.records_dir = self.output_dir / "records"

    async def search(
        self, client: httpx.AsyncClient, query: str, size: int = 10
    ) -> list[dict]:
        """搜索 Zenodo 记录。"""
        params = {
            "q": query,
            "size": size,
            "sort": "mostviewed",
        }

        try:
            response = await client.get(self.BASE_URL, params=params, timeout=30.0)
            response.raise_for_status()
            data = response.json()

            records = []
            for hit in data.get("hits", {}).get("hits", []):
                files = []
                for f in hit.get("files", []):
                    files.append({
                        "key": f.get("key", ""),
                        "size": f.get("size", 0),
                        "type": f.get("type", ""),
                        "download_url": f.get("links", {}).get("self", ""),
                    })

                records.append({
                    "id": hit.get("id", ""),
                    "doi": hit.get("doi", ""),
                    "title": hit.get("title", ""),
                    "description": (hit.get("description", "") or "")[:500],
                    "creators": [c.get("name", "") for c in hit.get("creators", [])],
                    "publication_date": hit.get("publication_date", ""),
                    "files": files,
                    "url": hit.get("links", {}).get("self", ""),
                })

            return records

        except Exception as e:
            print(f"  [错误] Zenodo搜索失败: {e}")
            return []

    async def download_record(
        self, client: httpx.AsyncClient, record: dict
    ) -> bool:
        """下载单条记录的元数据和文件。"""
        record_id = record.get("id", "unknown")
        record_dir = self.records_dir / str(record_id)
        record_dir.mkdir(parents=True, exist_ok=True)

        # 保存元数据
        meta_path = record_dir / "metadata.json"
        meta_path.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        # 下载小型文件（< 100MB）
        downloaded = 0
        for file_info in record.get("files", []):
            file_size = file_info.get("size", 0)
            # 只下载小于100MB的文件
            if file_size > 100 * 1024 * 1024:
                # 保存URL但不下载
                url_path = record_dir / f"{file_info['key']}.url.txt"
                url_path.write_text(file_info["download_url"], encoding="utf-8")
                continue

            download_url = file_info.get("download_url", "")
            if download_url:
                file_path = record_dir / file_info["key"]
                ok = await download_file(download_url, file_path, client)
                if ok:
                    downloaded += 1

        return True

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        max_records = 3 if test_mode else self.max_records

        print("=" * 60)
        print(f"  Zenodo 数据下载 {'[测试模式]' if test_mode else ''}")
        print(f"  目标: {max_records} 条记录")
        print("=" * 60)

        self.records_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n搜索关键词: robot grasping")
            records = await self.search(client, "robot grasping", max_records)
            print(f"  找到 {len(records)} 条记录\n")

            if not records:
                print("  尝试更宽泛的关键词...")
                records = await self.search(client, "grasping robot manipulation", max_records)
                print(f"  找到 {len(records)} 条记录\n")

            tracker = ProgressTracker(len(records), "下载记录")
            success_count = 0

            for record in records:
                print(f"  处理: {record['title'][:60]}...")
                ok = await self.download_record(client, record)
                if ok:
                    success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(records)} 条记录处理成功")
        print(f"输出目录: {self.records_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Zenodo 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式，只下载3条记录")
    args = parser.parse_args()

    downloader = ZenodoDownloader(max_records=config.ZENODO_RECORD_COUNT)
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
