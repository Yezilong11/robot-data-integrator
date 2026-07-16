"""从 Zenodo API 搜索并下载机器人抓取相关记录及其关联文件。

用法：
    python scripts/download_zenodo.py --size 10
    python scripts/download_zenodo.py --query "robot grasping" --size 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
ZENODO_API = "https://zenodo.org/api/records"
TIMEOUT = 60.0
MAX_RETRY = 3
MAX_FILE_SIZE = 100 * 1024 * 1024  # 100MB

RECORDS_DIR = Path("data/sources/api/zenodo/records")

DEFAULT_QUERY = "robot grasping"


# ─── 跳过逻辑 ──────────────────────────────────────────────────────────


def should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.exists() and path.stat().st_size > 0


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    delay: float = 1.0,
) -> httpx.Response | None:
    """带重试的 GET 请求。"""
    for attempt in range(1, MAX_RETRY + 1):
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                print(f"  ⏸ 速率限制，等待 10s 后重试 ({attempt}/{MAX_RETRY})")
                await asyncio.sleep(10)
                continue
            if resp.status_code >= 500:
                print(f"  ⚠ 服务端错误 {resp.status_code}，重试 ({attempt}/{MAX_RETRY})")
                continue
            return resp
        except httpx.HTTPError as e:
            print(f"  ⚠ 请求失败 ({attempt}/{MAX_RETRY}): {e}")
            if attempt == MAX_RETRY:
                return None
    return None


# ─── 下载逻辑 ──────────────────────────────────────────────────────────


async def search_records(
    client: httpx.AsyncClient, query: str, size: int, delay: float = 1.0
) -> list[dict[str, Any]]:
    """搜索 Zenodo 记录。"""
    resp = await safe_get(
        client,
        ZENODO_API,
        params={"q": query, "size": size, "sort": "mostviewed"},
        delay=delay,
    )
    if resp is None or resp.status_code != 200:
        print(f"  ❌ 搜索失败: {resp.status_code if resp else 'no response'}")
        return []

    data = resp.json()
    hits = data.get("hits", {})
    return hits.get("hits", [])


async def download_record_metadata(
    client: httpx.AsyncClient, record: dict[str, Any], delay: float = 1.0
) -> bool:
    """下载单条记录的元数据 JSON。"""
    rid = str(record.get("id", ""))
    if not rid:
        return False

    out_path = RECORDS_DIR / f"{rid}.json"

    if should_skip(out_path):
        print(f"  ⏭ 跳过元数据 #{rid}（已存在）")
        return True

    # 尝试拉取完整的记录详情
    resp = await safe_get(client, f"{ZENODO_API}/{rid}", delay=delay)
    if resp is not None and resp.status_code == 200:
        data = resp.json()
    else:
        data = record

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"  ✅ 元数据已保存 #{rid}")
    return True


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    out_path: Path,
    expected_size: int | None = None,
    delay: float = 1.0,
) -> bool:
    """下载单个文件，支持流式写入。"""
    if should_skip(out_path):
        print(f"    ⏭ 跳过文件: {out_path.name}（已存在）")
        return True

    # 大小检查
    if expected_size is not None and expected_size > MAX_FILE_SIZE:
        print(
            f"    ⏭ 跳过大文件: {out_path.name} "
            f"({expected_size / 1024 / 1024:.1f} MB > 100MB)"
        )
        return False

    for attempt in range(1, MAX_RETRY + 1):
        try:
            await asyncio.sleep(delay)
            async with client.stream("GET", url, follow_redirects=True) as resp:
                if resp.status_code != 200:
                    print(f"    ⚠ {out_path.name} HTTP {resp.status_code}")
                    return False

                out_path.parent.mkdir(parents=True, exist_ok=True)
                written = 0
                with out_path.open("wb") as f:
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
                        written += len(chunk)
                        # 超大保护（下载过程中超 100MB 则中止）
                        if written > MAX_FILE_SIZE:
                            f.close()
                            out_path.unlink()
                            print(
                                f"    ⏭ {out_path.name} 下载中超过 100MB，已中止"
                            )
                            return False
                print(f"    ✅ 已下载 {out_path.name} ({written / 1024:.1f} KB)")
                return True
        except httpx.HTTPError as e:
            print(f"    ⚠ 文件 {out_path.name} 下载失败 ({attempt}/{MAX_RETRY}): {e}")
            if attempt == MAX_RETRY:
                if out_path.exists() and out_path.stat().st_size == 0:
                    out_path.unlink()
                return False

    return False


async def process_record(
    client: httpx.AsyncClient, record: dict[str, Any], delay: float = 1.0
) -> tuple[bool, int]:
    """处理单条记录：下载元数据 + 关联文件。返回 (元数据成功?, 文件数)。"""
    rid = str(record.get("id", ""))
    files_downloaded = 0

    if await download_record_metadata(client, record, delay=delay):
        pass
    else:
        return False, 0

    # Zenodo v2 record：file metadata 在 record["files"] 或 _files
    files = record.get("files", [])
    if not files:
        # Zenodo v1 legacy 格式 _files 字段
        files = record.get("metadata", {}).get("_files", [])

    if not files:
        print(f"  ℹ #{rid} 无关联文件")
        return True, 0

    files_dir = RECORDS_DIR / rid
    files_dir.mkdir(parents=True, exist_ok=True)

    for file_info in files:
        # Zenodo file API：download via key 直接 URL
        # /api/records/{id}/files/{filename}/content (Zenodo v2)
        key = file_info.get("key") or file_info.get("filename") or ""
        size = file_info.get("size") or file_info.get("filesize")
        download_url = (
            file_info.get("links", {}).get("download")
            or file_info.get("links", {}).get("self")
        )

        # 如果还没有 URL，尝试构造 Zenodo v2 URL
        if not download_url and key:
            download_url = f"{ZENODO_API}/{rid}/files/{key}/content"

        if not download_url or not key:
            continue

        # size 可能是 None（field 名 filesize），小心处理
        size_int = int(size) if size else None
        out_path = files_dir / key

        if await download_file(client, download_url, out_path, size_int, delay=delay):
            files_downloaded += 1

    return True, files_downloaded


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 Zenodo 下载 robot grasping 相关记录"
    )
    parser.add_argument(
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help="搜索查询 (默认: 'robot grasping')",
    )
    parser.add_argument(
        "--size",
        type=int,
        default=10,
        help="最大下载数量 (默认: 10)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("Zenodo 记录下载工具")
    print("=" * 60)
    print(f"查询: '{args.query}'")
    print(f"最大数量: {args.size}")
    print(f"输出目录: {RECORDS_DIR}")
    print()

    RECORDS_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        print(f"🔍 搜索 '{args.query}'...")
        records = await search_records(client, args.query, args.size)

        if not records:
            print("❌ 未找到记录，退出")
            return

        records = records[: args.size]
        print(f"  找到 {len(records)} 条记录\n")

        print(f"📦 开始下载记录...\n")

        meta_ok = 0
        total_files = 0

        for i, record in enumerate(records, 1):
            rid = str(record.get("id", "?"))
            title = record.get("metadata", {}).get("title", "")
            print(
                f"[{i}/{len(records)}] #{rid}: {title[:60]}"
            )

            ok, nfiles = await process_record(client, record)
            if ok:
                meta_ok += 1
            total_files += nfiles

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print(f"⏱ 总耗时: {elapsed:.1f}s")
    print(f"📊 记录元数据: {meta_ok}/{len(records)} 成功")
    print(f"📊 文件下载: {total_files} 个")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())