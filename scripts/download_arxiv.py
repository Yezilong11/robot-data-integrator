"""从 arXiv API 搜索并下载论文元数据与 PDF。

用法：
    python scripts/download_arxiv.py --max-results 50
    python scripts/download_arxiv.py --keywords "robot grasping" "6-DOF grasp" --max-results 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any
from xml.etree import ElementTree

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
ARXIV_API = "https://export.arxiv.org/api/query"
TIMEOUT = 60.0
MAX_RETRY = 3

METADATA_DIR = Path("data/sources/api/arxiv/metadata")
PDF_DIR = Path("data/sources/api/arxiv/pdfs")

DEFAULT_KEYWORDS = [
    "robot grasping",
    "6-DOF grasp",
    "manipulation",
    "dexterous hand",
]

# Atom XML 命名空间
NS_ATOM = {"atom": "http://www.w3.org/2005/Atom"}

# ─── XML 解析 ──────────────────────────────────────────────────────────


def parse_arxiv_response(xml_text: str) -> list[dict[str, Any]]:
    """解析 arXiv Atom XML 响应，提取论文信息。

    返回 [{"arxiv_id": ..., "title": ..., "pdf_url": ..., "summary": ..., "authors": [...], "published": ...}, ...]
    """
    root = ElementTree.fromstring(xml_text)
    entries: list[dict[str, Any]] = []

    for entry_elem in root.findall("atom:entry", NS_ATOM):
        # 提取 ID，如 http://arxiv.org/abs/2401.12345v1 -> 2401.12345
        id_elem = entry_elem.find("atom:id", NS_ATOM)
        if id_elem is None or id_elem.text is None:
            continue
        arxiv_url = id_elem.text.strip()
        # 从 URL 提取 arxiv_id：去版本号
        match = re.search(r"abs/(.+?)(v\d+)?$", arxiv_url)
        arxiv_id = match.group(1) if match else arxiv_url.rsplit("/", 1)[-1]

        title_elem = entry_elem.find("atom:title", NS_ATOM)
        title = title_elem.text.strip() if title_elem is not None and title_elem.text else ""

        summary_elem = entry_elem.find("atom:summary", NS_ATOM)
        summary = (
            summary_elem.text.strip() if summary_elem is not None and summary_elem.text else ""
        )

        # PDF 链接
        pdf_url: str | None = None
        for link_elem in entry_elem.findall("atom:link", NS_ATOM):
            if link_elem.get("title") == "pdf" or link_elem.get("type") == "application/pdf":
                href = link_elem.get("href")
                if href:
                    # 替换 http 为 https（arxiv 证书有效）
                    pdf_url = href.replace("http://", "https://")
                break
        if not pdf_url:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        # 作者列表
        authors: list[str] = []
        for author_elem in entry_elem.findall("atom:author", NS_ATOM):
            name_elem = author_elem.find("atom:name", NS_ATOM)
            if name_elem is not None and name_elem.text:
                authors.append(name_elem.text.strip())

        published_elem = entry_elem.find("atom:published", NS_ATOM)
        published = (
            published_elem.text.strip() if published_elem is not None and published_elem.text else ""
        )

        entries.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "pdf_url": pdf_url,
                "summary": summary,
                "authors": authors,
                "published": published,
                "primary_source": "arxiv",
            }
        )

    return entries


# ─── 跳过逻辑 ──────────────────────────────────────────────────────────


def should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.exists() and path.stat().st_size > 0


# ─── 下载函数 ──────────────────────────────────────────────────────────


async def download_metadata(
    client: httpx.AsyncClient, entry: dict[str, Any]
) -> Path | None:
    """下载单篇论文的元数据 JSON。"""
    arxiv_id = entry["arxiv_id"]
    out_path = METADATA_DIR / f"{arxiv_id}.json"

    if should_skip(out_path):
        print(f"  ⏭ 跳过元数据 {arxiv_id}（已存在）")
        return out_path

    for attempt in range(1, MAX_RETRY + 1):
        try:
            await asyncio.sleep(3)  # arXiv 要求请求间隔 >=3 秒
            resp = await client.post(
                ARXIV_API,
                params={"id_list": arxiv_id, "max_results": 1},
            )
            resp.raise_for_status()
            records = parse_arxiv_response(resp.text)
            meta_data = records[0] if records else entry
        except Exception as e:
            print(f"  ⚠ 元数据 {arxiv_id} 第 {attempt} 次请求失败: {e}")
            if attempt == MAX_RETRY:
                # fallback：直接写入已解析的 entry
                meta_data = entry
                break
            await asyncio.sleep(5)
            continue
        break

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(meta_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✅ 已下载元数据 {arxiv_id}")
    return out_path


async def download_pdf(client: httpx.AsyncClient, entry: dict[str, Any]) -> Path | None:
    """下载单篇论文的 PDF。"""
    arxiv_id = entry["arxiv_id"]
    pdf_url = entry["pdf_url"]
    out_path = PDF_DIR / f"{arxiv_id}.pdf"

    if should_skip(out_path):
        print(f"  ⏭ 跳过 PDF {arxiv_id}（已存在）")
        return out_path

    for attempt in range(1, MAX_RETRY + 1):
        try:
            await asyncio.sleep(3)  # arXiv 礼貌间隔
            async with client.stream("GET", pdf_url, follow_redirects=True) as resp:
                resp.raise_for_status()
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with out_path.open("wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
        except Exception as e:
            print(f"  ⚠ PDF {arxiv_id} 第 {attempt} 次下载失败: {e}")
            if attempt == MAX_RETRY:
                if out_path.exists() and out_path.stat().st_size == 0:
                    out_path.unlink()
                return None
            await asyncio.sleep(5)
            continue
        break

    print(f"  ✅ 已下载 PDF {arxiv_id} ({out_path.stat().st_size / 1024:.1f} KB)")
    return out_path


async def search_papers(
    client: httpx.AsyncClient, keywords: list[str], max_results: int
) -> list[dict[str, Any]]:
    """按关键词搜索 arXiv，返回所有论文条目。"""
    all_entries: list[dict[str, Any]] = []
    seen_ids: set[str] = set()

    for kw in keywords:
        per_kw = max_results  # 每个关键词最多 max_results 篇
        total_for_kw = 0
        start = 0
        batch_size = 50  # arXiv 单页最多 200，用 50 比较稳

        print(f"\n🔍 搜索关键词: '{kw}' (最多 {per_kw} 篇)")

        while total_for_kw < per_kw:
            remaining = per_kw - total_for_kw
            current_batch = min(batch_size, remaining)

            for attempt in range(1, MAX_RETRY + 1):
                try:
                    await asyncio.sleep(3)  # arXiv 要求间隔 >=3 秒
                    resp = await client.get(
                        ARXIV_API,
                        params={
                            "search_query": f"all:{kw}",
                            "start": start,
                            "max_results": current_batch,
                        },
                    )
                    resp.raise_for_status()
                    entries = parse_arxiv_response(resp.text)
                    break
                except Exception as e:
                    print(f"  ⚠ 关键词 '{kw}' 第 {attempt} 次搜索失败: {e}")
                    if attempt == MAX_RETRY:
                        entries = []
                        break
                    await asyncio.sleep(5)

            if not entries:
                break

            for entry in entries:
                aid = entry["arxiv_id"]
                if aid not in seen_ids:
                    seen_ids.add(aid)
                    all_entries.append(entry)
                    total_for_kw += 1
                    if total_for_kw >= per_kw:
                        break

            start += current_batch

            if len(entries) < current_batch:
                break  # 没有更多结果

        print(f"  关键词 '{kw}' 新增 {total_for_kw} 篇")

    print(f"\n共收集 {len(all_entries)} 篇唯一论文")
    return all_entries


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 arXiv 下载机器人抓取相关论文元数据与 PDF"
    )
    parser.add_argument(
        "--max-results",
        type=int,
        default=50,
        help="每个关键词最多下载的论文数量 (默认: 50)",
    )
    parser.add_argument(
        "--keywords",
        nargs="+",
        default=DEFAULT_KEYWORDS,
        help="搜索关键词列表 (默认: robot grasping, 6-DOF grasp, manipulation, dexterous hand)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("arXiv 论文下载工具")
    print("=" * 60)
    print(f"关键词: {args.keywords}")
    print(f"每关键词最大数量: {args.max_results}")
    print(f"元数据目录: {METADATA_DIR}")
    print(f"PDF 目录: {PDF_DIR}")
    print()

    METADATA_DIR.mkdir(parents=True, exist_ok=True)
    PDF_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        entries = await search_papers(client, args.keywords, args.max_results)
        print(f"\n📦 开始下载 {len(entries)} 篇论文...\n")

        meta_success = 0
        pdf_success = 0

        for i, entry in enumerate(entries, 1):
            aid = entry["arxiv_id"]
            print(f"[{i}/{len(entries)}] {aid}: {entry['title'][:60]}...")

            meta_path = await download_metadata(client, entry)
            if meta_path:
                meta_success += 1

            pdf_path = await download_pdf(client, entry)
            if pdf_path:
                pdf_success += 1

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print(f"⏱ 总耗时: {elapsed:.1f}s")
    print(f"📊 元数据: {meta_success}/{len(entries)} 成功")
    print(f"📊 PDF: {pdf_success}/{len(entries)} 成功")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())