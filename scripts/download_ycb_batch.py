"""
YCB 物体批量下载脚本（增强版）

功能：
- 批量下载 YCB 标准 20 个物体
- 支持断点续传
- 自动解压并清理
- 显示下载进度

数据源：YCB Dataset
官方地址：https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/

作者：挑战杯团队
创建日期：2026-07-14
"""

import argparse
import asyncio
import sys
import zipfile
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import format_size, get_data_dir

# YCB 标准 20 个物体及其下载链接
YCB_OBJECTS = {
    "002_master_chef_can": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/002_master_chef_can.zip",
    "003_cracker_box": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/003_cracker_box.zip",
    "004_sugar_box": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/004_sugar_box.zip",
    "005_tomato_soup_can": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/005_tomato_soup_can.zip",
    "006_mustard_bottle": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/006_mustard_bottle.zip",
    "007_tuna_fish_can": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/007_tuna_fish_can.zip",
    "008_pudding_box": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/008_pudding_box.zip",
    "009_gelatin_box": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/009_gelatin_box.zip",
    "010_potted_meat_can": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/010_potted_meat_can.zip",
    "011_banana": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/011_banana.zip",
    "019_strawberry": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/019_strawberry.zip",
    "021_bleach_cleanser": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/021_bleach_cleanser.zip",
    "024_bowl": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/024_bowl.zip",
    "025_mug": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/025_mug.zip",
    "035_power_drill": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/035_power_drill.zip",
    "036_wood_block": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/036_wood_block.zip",
    "037_scissors": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/037_scissors.zip",
    "040_large_marker": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/040_large_marker.zip",
    "051_extra_large_clamp": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/051_extra_large_clamp.zip",
    "052_extra_large_clamp": "https://rse-lab.cs.washington.edu/wp-content/uploads/2015/02/052_extra_large_clamp.zip",
}


async def download_object(
    client: httpx.AsyncClient, name: str, url: str, output_dir: Path
) -> tuple[bool, str]:
    """下载单个 YCB 物体。"""
    obj_dir = output_dir / name

    # 检查是否已经解压完成
    if obj_dir.exists() and any(obj_dir.iterdir()):
        return True, f"已存在: {name}"

    zip_path = output_dir / f"{name}.zip"

    # 下载 zip
    try:
        if zip_path.exists() and zip_path.stat().st_size > 1000:
            pass  # 已有 zip，跳过下载
        else:
            response = await client.get(url, timeout=120.0, follow_redirects=True)
            response.raise_for_status()

            zip_path.parent.mkdir(parents=True, exist_ok=True)
            with open(zip_path, "wb") as f:
                f.write(response.content)

    except Exception as e:
        return False, f"下载失败: {name} - {e}"

    # 解压
    try:
        obj_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(obj_dir)
        # 删除 zip 节省空间
        zip_path.unlink()
        return True, f"完成: {name}"
    except Exception as e:
        return False, f"解压失败: {name} - {e}"


async def run(objects: list[str] | None = None, max_concurrent: int = 3) -> None:
    """执行批量下载。"""
    print("=" * 60)
    print("  YCB 物体批量下载")
    print("=" * 60)

    output_dir = get_data_dir() / "datasets" / "ycb" / "models"
    output_dir.mkdir(parents=True, exist_ok=True)

    # 选择要下载的物体
    if objects is None:
        target_objects = YCB_OBJECTS
    else:
        target_objects = {k: v for k, v in YCB_OBJECTS.items() if k in objects}

    print(f"\n目标物体数: {len(target_objects)}")
    print(f"输出目录: {output_dir}")
    print(f"并发数: {max_concurrent}\n")

    semaphore = asyncio.Semaphore(max_concurrent)

    async def download_with_semaphore(client, name, url):
        async with semaphore:
            return await download_object(client, name, url, output_dir)

    success_count = 0
    fail_count = 0

    async with httpx.AsyncClient() as client:
        # 添加 User-Agent 避免被拒绝
        client.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        tasks = [download_with_semaphore(client, name, url) for name, url in target_objects.items()]

        results = []
        for i, coro in enumerate(asyncio.as_completed(tasks), 1):
            ok, msg = await coro
            results.append((ok, msg))
            status = "✅" if ok else "❌"
            print(f"  [{i}/{len(target_objects)}] {status} {msg}")
            if ok:
                success_count += 1
            else:
                fail_count += 1

    # 统计
    total_size = sum(
        f.stat().st_size for f in output_dir.rglob("*") if f.is_file()
    )

    print(f"\n" + "=" * 60)
    print(f"  下载完成")
    print(f"  成功: {success_count}/{len(target_objects)}")
    print(f"  失败: {fail_count}")
    print(f"  总大小: {format_size(total_size)}")
    print(f"  输出目录: {output_dir}")
    print(f"=" * 60)


def main():
    parser = argparse.ArgumentParser(description="YCB 物体批量下载")
    parser.add_argument("--objects", nargs="*", help="指定要下载的物体（默认全部）")
    parser.add_argument("--concurrent", type=int, default=3, help="并发下载数（默认3）")
    args = parser.parse_args()

    asyncio.run(run(objects=args.objects, max_concurrent=args.concurrent))


if __name__ == "__main__":
    main()
