"""从 Semantic Scholar API 搜索并下载论文元数据。

原脚本依赖已停服的 Papers with Code API，现改用 Semantic Scholar Graph API
（https://api.semanticscholar.org/graph/v1/paper/search）获取论文元数据及
关联的 arXiv ID，结果仍写入 data/sources/web/paperswithcode/papers/。

用法：
    python scripts/download_paperswithcode.py --limit 50
    python scripts/download_paperswithcode.py --q "robot grasping" --limit 30
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from pathlib import Path
from typing import Any

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
S2_API = "https://api.semanticscholar.org/graph/v1/paper/search"
TIMEOUT = 30.0
MAX_RETRY = 5
# Semantic Scholar API 限制：请求间隔 >=3 秒
REQUEST_DELAY = 3.0

PAPERS_DIR = Path("data/sources/web/paperswithcode/papers")

DEFAULT_Q = "robot grasping"
DEFAULT_LIMIT = 50

# 请求字段：title, authors, year, abstract, externalIds, url, openAccessPdf
SEARCH_FIELDS = "title,authors,year,abstract,externalIds,url,openAccessPdf"


# ─── 跳过逻辑 ──────────────────────────────────────────────────────────


def should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.exists() and path.stat().st_size > 0


def safe_id(text: str) -> str:
    """生成可作文件名的安全 ID（只保留字母数字与 "-"）。"""
    text = text.strip().lower()
    cleaned = re.sub(r"[^a-z0-9-]+", "-", text)
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    return cleaned or "unknown"


# ─── HTTP 请求 ─────────────────────────────────────────────────────────


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    delay: float = REQUEST_DELAY,
) -> httpx.Response | None:
    """带重试与礼貌间隔的 GET 请求。"""
    for attempt in range(1, MAX_RETRY + 1):
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                wait = 30 * (2 ** (attempt - 1))  # 30s, 60s, 120s, 240s, 480s
                print(f"  [WAIT] 速率限制，等待 {wait}s 后重试 ({attempt}/{MAX_RETRY})")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                print(f"  [WARN] 服务端错误 {resp.status_code}，重试 ({attempt}/{MAX_RETRY})")
                continue
            return resp
        except httpx.HTTPError as e:
            print(f"  [WARN] 请求失败 ({attempt}/{MAX_RETRY}): {e}")
            if attempt == MAX_RETRY:
                return None
    return None


# ─── 搜索 ────────────────────────────────────────────────────────────────


async def search_papers(
    client: httpx.AsyncClient, q: str, limit: int
) -> list[dict[str, Any]]:
    """使用 Semantic Scholar 搜索 API 搜索论文。

    请求参数: query, limit, fields=title,authors,year,abstract,externalIds,url,openAccessPdf
    """
    if not q.strip():
        return []

    all_results: list[dict[str, Any]] = []
    offset = 0
    batch_size = min(100, limit)  # S2 单页最多 100 条

    print(f"[SEARCH] 搜索 '{q}' (最多 {limit} 篇)")

    while len(all_results) < limit:
        remaining = limit - len(all_results)
        current_batch = min(batch_size, remaining)

        resp = await safe_get(
            client,
            S2_API,
            params={
                "query": q,
                "limit": current_batch,
                "offset": offset,
                "fields": SEARCH_FIELDS,
            },
        )
        if resp is None:
            print(f"  [WARN] 搜索 '{q}' 偏移 {offset} 失败")
            break

        if resp.status_code != 200:
            print(f"  [WARN] 搜索 {q!r} 偏移 {offset} 失败 (状态码: {resp.status_code})")
            break

        data = resp.json() if resp.text else {}
        if not data:
            break

        results = data.get("data", [])
        if not results:
            break

        all_results.extend(results)

        # 检查是否还有更多结果
        total = data.get("total", 0)
        offset += len(results)

        if len(results) < current_batch:
            break  # 没有更多结果
        if total and len(all_results) >= total:
            break

    print(f"  找到 {len(all_results)} 条搜索结果")
    return all_results[:limit]


# ─── 元数据处理 ────────────────────────────────────────────────────────


def extract_paper_record(paper: dict[str, Any]) -> dict[str, Any]:
    """从 Semantic Scholar 返回的论文对象中提取并规整元数据。

    - 提取 arXiv ID（位于 externalIds.ArXiv）
    - 规整作者列表、开放获取 PDF 等字段
    """
    external_ids = paper.get("externalIds") or {}
    arxiv_id = external_ids.get("ArXiv") or external_ids.get("arxiv")

    authors_raw = paper.get("authors") or []
    authors = []
    for a in authors_raw:
        if isinstance(a, dict):
            authors.append(
                {
                    "name": a.get("name"),
                    "authorId": a.get("authorId"),
                }
            )
        elif isinstance(a, str):
            authors.append({"name": a})

    open_access_pdf = paper.get("openAccessPdf")
    pdf_url = None
    if isinstance(open_access_pdf, dict):
        pdf_url = open_access_pdf.get("url")
    elif isinstance(open_access_pdf, str):
        pdf_url = open_access_pdf

    return {
        "paperId": paper.get("paperId"),
        "arxiv_id": arxiv_id,
        "title": paper.get("title", ""),
        "abstract": paper.get("abstract"),
        "year": paper.get("year"),
        "authors": authors,
        "externalIds": external_ids,
        "url": paper.get("url"),
        "openAccessPdf": pdf_url,
        "source": "semantic-scholar",
    }


def pick_filename(record: dict[str, Any], idx: int) -> str:
    """根据 paperId 或 arxiv_id 选择文件名。"""
    paper_id = record.get("paperId")
    if paper_id:
        return f"{safe_id(str(paper_id))}.json"
    arxiv_id = record.get("arxiv_id")
    if arxiv_id:
        return f"{safe_id(str(arxiv_id))}.json"
    return f"unknown-{idx}.json"


# ─── 主流程 ──────────────────────────────────────────────────────────────


async def process_paper(
    client: httpx.AsyncClient,
    paper: dict[str, Any],
    idx: int,
    total: int,
) -> Path | None:
    """处理单条搜索结果，写入元数据 JSON。"""
    record = extract_paper_record(paper)
    filename = pick_filename(record, idx)
    out_path = PAPERS_DIR / filename

    title = record.get("title", "") or ""
    if should_skip(out_path):
        print(f"  [SKIP] 跳过 [{idx}/{total}] {title[:60]}（已存在）")
        return out_path

    # 注意：此步骤无需再发请求，搜索结果已包含所需字段。
    # 保留 client 参数以与其他脚本接口保持一致。
    _ = client

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    extra = f" arXiv: {record['arxiv_id']}" if record.get("arxiv_id") else ""
    print(f"  [OK] [{idx}/{total}] {title[:60]}{extra}")
    return out_path


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 Semantic Scholar 下载论文元数据（替代 Papers with Code API）"
    )
    parser.add_argument(
        "--q",
        type=str,
        default=DEFAULT_Q,
        help="搜索查询 (默认: 'robot grasping')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_LIMIT,
        help="最大下载论文数 (默认: 50)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Semantic Scholar 论文元数据下载工具")
    print("=" * 60)
    print(f"查询: '{args.q}'")
    print(f"最大数量: {args.limit}")
    print(f"输出目录: {PAPERS_DIR}")
    print(f"请求间隔: {REQUEST_DELAY}s")
    print()

    PAPERS_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "RobotDataIntegrator/1.0"}) as client:
        results = await search_papers(client, args.q, args.limit)

        if not results:
            print("[FAIL] 未找到论文，退出")
            return

        print(f"\n[PKG] 开始保存 {len(results)} 篇论文元数据...\n")

        success = 0
        for i, paper in enumerate(results, 1):
            out = await process_paper(client, paper, i, len(results))
            if out:
                success += 1

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print(f"[TIME] 总耗时: {elapsed:.1f}s")
    print(f"[STAT] 元数据: {success}/{len(results)} 成功")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())