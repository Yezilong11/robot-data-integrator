"""Google Scanned Objects 数据集下载脚本。

Google Scanned Objects 是 Google Research 发布的 1000+ 3D 扫描家用物品数据集，
托管在 Gazebo Fuel（https://app.gazebosim.org）上，owner 为 GoogleResearch。

原始 GSO 数据集于 2020-09-03 上传，本脚本通过 Gazebo Fuel REST API 列出并下载。

用法：
    python scripts/download_google_scanned.py
    python scripts/download_google_scanned.py --output-dir data/sources/datasets/google_scanned/models/
    python scripts/download_google_scanned.py --max-download 100
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
FUEL_API = "https://fuel.gazebosim.org/1.0"
FUEL_OWNER = "GoogleResearch"
# GSO 模型上传日期（原始数据集）
GSO_DATE_PREFIX = "2020-09-03"
TIMEOUT = 60.0
PAGE_SIZE = 20  # Fuel API 每页最多返回 20 条

DEFAULT_OUTPUT = Path("data/sources/datasets/google_scanned/models/")


# ─── 工具函数 ──────────────────────────────────────────────────────────
def flatten_file_tree(tree: list) -> list[str]:
    """递归展开 Gazebo Fuel 文件树，返回所有文件路径。"""
    files: list[str] = []
    for node in tree:
        path = node.get("path", "")
        if path:
            files.append(path)
        children = node.get("children", [])
        if children:
            files.extend(flatten_file_tree(children))
    return files


# ─── API 调用 ──────────────────────────────────────────────────────────
async def list_gso_models(client: httpx.AsyncClient, max_download: int = 0) -> list[dict]:
    """列出 GoogleResearch 下 2020-09-03 上传的 GSO 模型。

    Fuel API 按时间排序，GSO 模型在 page ~47-101 之间。
    我们按 order=asc 分页扫描，只保留 2020-09-03 上传的模型。
    """
    all_models: list[dict] = []
    page = 1

    while True:
        params = {
            "owner": FUEL_OWNER,
            "limit": PAGE_SIZE,
            "order": "asc",
            "page": page,
        }
        resp = await client.get(f"{FUEL_API}/models", params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  [警告] API 返回 HTTP {resp.status_code}")
            break

        batch = resp.json()
        if not batch:
            break

        # 按日期过滤 GSO 模型
        gso_batch = [
            m for m in batch
            if m.get("createdAt", "").startswith(GSO_DATE_PREFIX)
        ]

        if gso_batch:
            all_models.extend(gso_batch)
            if max_download and len(all_models) >= max_download:
                all_models = all_models[:max_download]
                break

        # 如果当前页已经跳过 GSO 日期，且已有数据，可以停止
        first_date = batch[0].get("createdAt", "")[:10]
        last_date = batch[-1].get("createdAt", "")[:10]

        # GSO 模型在 2020-09-03，如果当前页已经超过这个日期且有数据了就继续
        # 如果最后一页都还没到 GSO 日期，继续翻页
        # 如果第一页已经超过 GSO 日期且有数据了，停止
        if all_models and first_date > GSO_DATE_PREFIX:
            break

        # 总共 3353 个模型，~168 页，避免无限循环
        if page > 200:
            break

        page += 1

    return all_models


async def get_file_tree(client: httpx.AsyncClient, model_name: str) -> list[str]:
    """获取单个模型的文件列表。"""
    url = f"{FUEL_API}/{FUEL_OWNER}/models/{model_name}/tip/files"
    resp = await client.get(url, timeout=30)
    if resp.status_code != 200:
        return []
    data = resp.json()
    tree = data.get("file_tree", [])
    return flatten_file_tree(tree)


async def download_file(
    client: httpx.AsyncClient,
    model_name: str,
    file_path: str,
    dest: Path,
) -> bool:
    """下载单个文件。"""
    if dest.exists() and dest.stat().st_size > 0:
        return True

    url = f"{FUEL_API}/{FUEL_OWNER}/models/{model_name}/tip/files/{file_path}"
    try:
        resp = await client.get(url, timeout=30, follow_redirects=True)
        if resp.status_code != 200:
            return False
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(resp.content)
        return True
    except httpx.HTTPError:
        return False


# ─── 主流程 ────────────────────────────────────────────────────────────
async def run(output_dir: Path, max_download: int) -> None:
    print("=" * 70)
    print("Google Scanned Objects 数据集下载")
    print("=" * 70)
    print(f"  数据源: Gazebo Fuel ({FUEL_API})")
    print(f"  Owner: {FUEL_OWNER}")
    print(f"  GSO 日期: {GSO_DATE_PREFIX}")
    print(f"  输出目录: {output_dir}")
    print(f"  最大下载数: {max_download if max_download > 0 else '无限制'}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        # 1. 列出 GSO 模型
        print("步骤 1: 列出 GSO 模型 (2020-09-03 上传)...")
        models = await list_gso_models(client, max_download)
        print(f"  [完成] 发现 {len(models)} 个 GSO 模型\n")

        if not models:
            print("  [错误] 未找到 GSO 模型，退出")
            return

        success = 0
        failed = 0

        for i, model in enumerate(models, 1):
            name = model["name"]
            model_dir = output_dir / name

            # 跳过已下载的模型
            if model_dir.exists() and any(model_dir.rglob("model.config")):
                print(f"  [{i}/{len(models)}] 跳过 {name} (已下载)")
                success += 1
                continue

            print(f"  [{i}/{len(models)}] 下载 {name}...")

            # 2. 获取文件列表
            file_paths = await get_file_tree(client, name)
            if not file_paths:
                print(f"    [警告] 无文件")
                failed += 1
                continue

            # 3. 下载每个文件
            model_ok = False
            for fp in file_paths:
                dest = model_dir / fp.lstrip("/")
                ok = await download_file(client, name, fp, dest)
                if ok:
                    model_ok = True

            if model_ok:
                size_mb = sum(f.stat().st_size for f in model_dir.rglob("*") if f.is_file()) / 1e6
                print(f"    [完成] {len(file_paths)} 个文件 ({size_mb:.1f} MB)")
                success += 1
            else:
                print(f"    [失败]")
                failed += 1

    print()
    print("=" * 70)
    print(f"下载完成: 成功 {success}，失败 {failed}，共 {len(models)}")
    print("=" * 70)


# ─── 入口 ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Google Scanned Objects 数据集下载脚本")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出目录（默认: {DEFAULT_OUTPUT}）",
    )
    parser.add_argument(
        "--max-download",
        type=int,
        default=0,
        help="最多下载的模型数量（0 表示无限制）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(run(args.output_dir, args.max_download))


if __name__ == "__main__":
    main()