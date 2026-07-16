"""DexGraspNet 数据集下载脚本。

DexGraspNet 数据集约 5GB，从 HuggingFace 下载。
利用 HuggingFace API 获取文件列表，下载元数据和部分示例数据到
data/sources/datasets/dexgraspnet/data/。

用法：
    python scripts/download_dexgraspnet.py
    python scripts/download_dexgraspnet.py --output-dir data/sources/datasets/dexgraspnet/data/
    python scripts/download_dexgraspnet.py --max-size-mb 100
"""

from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path
from urllib.parse import quote

import httpx

# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── 常量 ──────────────────────────────────────────────────────────────
# 支持 HF_ENDPOINT 环境变量切换镜像站（如 https://hf-mirror.com）
_HF_BASE = os.getenv("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
DATASET_REPO = "lhrlhr/DexGraspNet2.0"
REPO_INFO_URL = f"{_HF_BASE}/api/datasets/{DATASET_REPO}"
TREE_API_URL = f"{_HF_BASE}/api/datasets/{DATASET_REPO}/tree/main"
FILE_BASE_URL = f"{_HF_BASE}/datasets/{DATASET_REPO}/resolve/main/"
TIMEOUT = 60.0
CHUNK_SIZE = 1 << 20  # 1 MiB


# ─── 工具函数 ──────────────────────────────────────────────────────────
def human_readable_size(num_bytes: float) -> str:
    """将字节数转为人类可读字符串。"""
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f}PB"


# ─── HuggingFace API ─────────────────────────────────────────────────
async def fetch_repo_info(client: httpx.AsyncClient) -> dict:
    """获取 HuggingFace 数据集仓库信息。"""
    print("正在获取仓库信息...")
    print(f"  API: {REPO_INFO_URL}")
    try:
        resp = await client.get(REPO_INFO_URL)
        if resp.status_code != 200:
            print(f"  [警告] API 返回 HTTP {resp.status_code}")
            return {}
        data = resp.json()
        print(f"  [完成] 仓库: {data.get('id', DATASET_REPO)}")
        print(f"         私有: {data.get('private', False)}")
        print(f"         下载次数: {data.get('downloads', 0)}")
        return data
    except (httpx.HTTPError, ValueError) as e:
        print(f"  [错误] 获取仓库信息失败: {e}")
        return {}


async def fetch_file_tree(client: httpx.AsyncClient, path: str = "") -> list[dict]:
    """递归获取仓库文件树。返回 [{path, type, size, oid}] 列表。"""
    url = TREE_API_URL if not path else f"{TREE_API_URL}/{quote(path, safe='')}"
    print(f"  [列表] {url}")
    try:
        resp = await client.get(url)
        if resp.status_code != 200:
            print(f"  [警告] 列表 API 返回 HTTP {resp.status_code}")
            return []
        entries = resp.json()
    except (httpx.HTTPError, ValueError) as e:
        print(f"  [错误] 列表 API 请求失败: {e}")
        return []

    files: list[dict] = []
    for entry in entries:
        entry_type = entry.get("type", "")
        entry_path = entry.get("path", "")
        if entry_type == "directory":
            sub_files = await fetch_file_tree(client, entry_path)
            files.extend(sub_files)
        elif entry_type == "file":
            files.append(
                {
                    "path": entry_path,
                    "size": entry.get("size", 0),
                    "oid": entry.get("oid", ""),
                    "lfs": bool(entry.get("lfs")),
                }
            )
    return files


# ─── 下载 ──────────────────────────────────────────────────────────────
async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    display_name: str,
) -> bool:
    """异步下载文件，打印进度到 stdout。"""
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [跳过] 文件已存在: {dest.name}")
        return True

    print(f"  [下载] {display_name}")
    print(f"         URL: {url}")
    try:
        async with client.stream("GET", url, follow_redirects=True) as resp:
            if resp.status_code != 200:
                print(f"  [错误] HTTP {resp.status_code} —— {display_name}")
                return False
            total = int(resp.headers.get("content-length", 0))
            downloaded = 0
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open("wb") as f:
                async for chunk in resp.aiter_bytes(chunk_size=CHUNK_SIZE):
                    f.write(chunk)
                    downloaded += len(chunk)
                    if total > 0:
                        pct = downloaded * 100 // total
                        if downloaded == len(chunk) or pct % 10 == 0:
                            print(
                                f"         进度: {downloaded}/{total} bytes ({pct}%)",
                                end="\r",
                                flush=True,
                            )
            print()
            print(f"  [完成] {dest.name} ({downloaded} bytes)")
            return True
    except httpx.HTTPError as e:
        print(f"  [错误] 下载失败 {display_name}: {e}")
        return False


# ─── 主流程 ────────────────────────────────────────────────────────────
async def run(output_dir: Path, max_size_mb: float) -> None:
    print("=" * 70)
    print("DexGraspNet 数据集下载")
    print("=" * 70)
    print(f"  数据集仓库: {DATASET_REPO}")
    print(f"  输出目录: {output_dir}")
    print(f"  单文件最大大小: {max_size_mb}MB")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)
    max_size_bytes = int(max_size_mb * 1024 * 1024)

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        # 1. 获取仓库信息
        info = await fetch_repo_info(client)
        if not info:
            print("  [警告] 无法获取仓库信息，仍尝试列出文件树。")

        # 2. 获取文件树
        print()
        print("正在获取文件列表...")
        files = await fetch_file_tree(client)
        print(f"  [完成] 共发现 {len(files)} 个文件")

        if not files:
            print()
            print("=" * 70)
            print("未发现可下载文件，请手动访问：")
            print(f"  https://huggingface.co/datasets/{DATASET_REPO}")
            print(f"  https://huggingface.co/datasets/{DATASET_REPO}/tree/main")
            print()
            print("可使用 huggingface-hub 工具下载：")
            print(f"  huggingface-cli download {DATASET_REPO} --repo-type dataset "
                  f"--local-dir {output_dir}")
            return

        # 3. 按大小过滤并下载
        print()
        print("步骤 3: 按大小过滤并下载文件...")
        skipped_size = 0
        skipped_count = 0
        download_targets: list[dict] = []
        for f in files:
            size = f.get("size", 0) or 0
            if max_size_bytes > 0 and size > max_size_bytes:
                skipped_size += size
                skipped_count += 1
                print(
                    f"  [过滤] 跳过过大文件: {f['path']} "
                    f"({human_readable_size(size)} > {max_size_mb}MB)"
                )
            else:
                download_targets.append(f)

        print(f"  [统计] 待下载 {len(download_targets)} 个文件，跳过 {skipped_count} 个过大文件")

        # 优先下载元数据 README / .json / .csv 等小文件
        download_targets.sort(key=lambda x: x.get("size", 0) or 0)

        success = 0
        failed = 0
        for f in download_targets:
            rel_path = f["path"]
            url = f"{FILE_BASE_URL}{quote(rel_path, safe='/')}"
            dest = output_dir / rel_path
            print(f"\n>>> 处理文件 [{rel_path}]")
            ok = await download_file(client, url, dest, display_name=rel_path)
            if ok:
                success += 1
            else:
                failed += 1

    print()
    print("=" * 70)
    print(
        f"下载完成: 成功 {success}，失败 {failed}，"
        f"跳过过大 {skipped_count} 个（共 {human_readable_size(skipped_size)}）"
    )
    print("=" * 70)


# ─── 入口 ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="DexGraspNet 数据集下载脚本")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/sources/datasets/dexgraspnet/data/"),
        help="输出目录（默认: data/sources/datasets/dexgraspnet/data/）",
    )
    parser.add_argument(
        "--max-size-mb",
        type=float,
        default=500.0,
        help="单文件最大大小（MB），超过则跳过（默认: 500MB，0 表示无限制）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args.output_dir, args.max_size_mb))


if __name__ == "__main__":
    main()