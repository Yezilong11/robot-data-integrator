"""
Google Scanned Objects 批量下载脚本（增强版）

功能：
- 从 Gazebo Fuel 平台批量下载 Google Scanned Objects
- 支持断点续传
- 显示下载进度
- 同时下载 mesh 和纹理文件

数据源：Google Scanned Objects
官方地址：https://fuel.gazebosim.org/1.0/GoogleResearch/models

作者：挑战杯团队
创建日期：2026-07-14
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import format_size, get_data_dir

# 关键物体列表（重点关注抓取相关）
KEY_MODELS = [
    "Avocado", "Banana", "Bleach_cleanser", "Bowl", "Cracker_box",
    "Fork", "Gelatin_box", "Hammer", "Knife", "Lemon",
    "Mug", "Mustard_bottle", "Orange", "Pear", "Potted_meat_can",
    "Power_drill", "Screwdriver", "Spatula", "Strawberry", "Sugar_box",
    "Tomato_soup_can", "Tuna_fish_can", "Wood_block", "Master_chef_can",
    "Pudding_box", "Large_clamp", "Extra_large_clamp",
]


async def get_model_info(client: httpx.AsyncClient, model_name: str) -> dict | None:
    """从 Fuel 平台获取模型信息。"""
    url = f"https://fuel.gazebosim.org/1.0/GoogleResearch/models/{model_name}"
    try:
        response = await client.get(url, timeout=30.0, follow_redirects=True)
        if response.status_code == 200:
            return response.json()
    except Exception as e:
        print(f"  [错误] {model_name}: {e}")
    return None


async def download_model(
    client: httpx.AsyncClient, model_name: str, output_dir: Path
) -> tuple[bool, str]:
    """下载单个模型。"""
    model_dir = output_dir / model_name
    model_dir.mkdir(parents=True, exist_ok=True)

    # 获取模型信息
    info = await get_model_info(client, model_name)
    if not info:
        return False, f"无法获取模型信息: {model_name}"

    # 保存元数据
    meta_path = model_dir / "model_info.json"
    if not meta_path.exists():
        meta_path.write_text(
            json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    # 下载文件
    files = info.get("files", [])
    if not files:
        return False, f"无文件列表: {model_name}"

    downloaded = 0
    for file_info in files:
        file_name = file_info.get("name", "")
        if not file_name:
            continue

        # 下载文件
        file_url = f"https://fuel.gazebosim.org/1.0/GoogleResearch/models/{model_name}/files/{file_name}"
        file_path = model_dir / file_name

        if file_path.exists() and file_path.stat().st_size > 0:
            downloaded += 1
            continue

        try:
            response = await client.get(file_url, timeout=120.0, follow_redirects=True)
            if response.status_code == 200:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_bytes(response.content)
                downloaded += 1
        except Exception as e:
            print(f"    [警告] 下载文件失败: {file_name} - {e}")

    return downloaded > 0, f"{model_name} ({downloaded}/{len(files)} 文件)"


async def run(models: list[str] | None = None, max_concurrent: int = 3) -> None:
    """执行批量下载。"""
    print("=" * 60)
    print("  Google Scanned Objects 批量下载")
    print("=" * 60)

    output_dir = get_data_dir() / "datasets" / "google_scanned" / "models"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 选择要下载的模型
    if models is None:
        target_models = KEY_MODELS
    else:
        target_models = [m for m in KEY_MODELS if m in models]

    print(f"\n目标模型数: {len(target_models)}")
    print(f"输出目录: {output_dir}")
    print(f"并发数: {max_concurrent}\n")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_semaphore(client, model):
        async with semaphore:
            return await download_model(client, model, output_dir)

    success_count = 0

    async with httpx.AsyncClient() as client:
        client.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        tasks = [download_with_semaphore(client, m) for m in target_models]

        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            ok, msg = await coro
            status = "✅" if ok else "❌"
            print(f"  [{i}/{len(target_models)}] {status} {msg}")
            if ok:
                success_count += 1

    # 统计
    total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())

    print(f"\n" + "=" * 60)
    print(f"  下载完成")
    print(f"  成功: {success_count}/{len(target_models)}")
    print(f"  总大小: {format_size(total_size)}")
    print(f"  输出目录: {output_dir}")
    print(f"=" * 60)


def main():
    parser = argparse.ArgumentParser(description="Google Scanned Objects 批量下载")
    parser.add_argument("--models", nargs="*", help="指定要下载的模型")
    parser.add_argument("--concurrent", type=int, default=3, help="并发下载数（默认3）")
    args = parser.parse_args()

    asyncio.run(run(models=args.models, max_concurrent=args.concurrent))


if __name__ == "__main__":
    main()
