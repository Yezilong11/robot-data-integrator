"""YCB 物体数据集下载脚本。

YCB 物体数据集从 S3 镜像下载 berkeley 处理后的 mesh + google 16k 扫描数据。
S3 基址: http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/

用法：
    python scripts/download_ycb.py
    python scripts/download_ycb.py --objects 002_master_chef_can,003_cracker_box
    python scripts/download_ycb.py --skip-existing
    python scripts/download_ycb.py --output-dir data/sources/datasets/ycb/models/
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import tarfile
from pathlib import Path

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
S3_BASE = "http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/"
TIMEOUT = 60.0
CHUNK_SIZE = 1 << 20  # 1 MiB

# YCB 20 个标准物体
# Berkeley meshes: 处理后的纹理 mesh (Poisson + Volumetric)
# Google 16k: Google 扫描 16k 多边形 mesh
YCB_OBJECTS: list[dict[str, str]] = [
    {"name": "002_master_chef_can", "berkeley": f"{S3_BASE}berkeley/002_master_chef_can/002_master_chef_can_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/002_master_chef_can_google_16k.tgz"},
    {"name": "003_cracker_box", "berkeley": f"{S3_BASE}berkeley/003_cracker_box/003_cracker_box_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/003_cracker_box_google_16k.tgz"},
    {"name": "004_sugar_box", "berkeley": f"{S3_BASE}berkeley/004_sugar_box/004_sugar_box_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/004_sugar_box_google_16k.tgz"},
    {"name": "005_tomato_soup_can", "berkeley": f"{S3_BASE}berkeley/005_tomato_soup_can/005_tomato_soup_can_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/005_tomato_soup_can_google_16k.tgz"},
    {"name": "006_mustard_bottle", "berkeley": f"{S3_BASE}berkeley/006_mustard_bottle/006_mustard_bottle_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/006_mustard_bottle_google_16k.tgz"},
    {"name": "007_tuna_fish_can", "berkeley": f"{S3_BASE}berkeley/007_tuna_fish_can/007_tuna_fish_can_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/007_tuna_fish_can_google_16k.tgz"},
    {"name": "008_pudding_box", "berkeley": f"{S3_BASE}berkeley/008_pudding_box/008_pudding_box_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/008_pudding_box_google_16k.tgz"},
    {"name": "009_gelatin_box", "berkeley": f"{S3_BASE}berkeley/009_gelatin_box/009_gelatin_box_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/009_gelatin_box_google_16k.tgz"},
    {"name": "010_potted_meat_can", "berkeley": f"{S3_BASE}berkeley/010_potted_meat_can/010_potted_meat_can_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/010_potted_meat_can_google_16k.tgz"},
    {"name": "011_banana", "berkeley": f"{S3_BASE}berkeley/011_banana/011_banana_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/011_banana_google_16k.tgz"},
    {"name": "019_pitcher_base", "berkeley": f"{S3_BASE}berkeley/019_pitcher_base/019_pitcher_base_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/019_pitcher_base_google_16k.tgz"},
    {"name": "021_bleach_cleanser", "berkeley": f"{S3_BASE}berkeley/021_bleach_cleanser/021_bleach_cleanser_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/021_bleach_cleanser_google_16k.tgz"},
    {"name": "024_bowl", "berkeley": f"{S3_BASE}berkeley/024_bowl/024_bowl_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/024_bowl_google_16k.tgz"},
    {"name": "025_mug", "berkeley": f"{S3_BASE}berkeley/025_mug/025_mug_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/025_mug_google_16k.tgz"},
    {"name": "035_power_drill", "berkeley": f"{S3_BASE}berkeley/035_power_drill/035_power_drill_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/035_power_drill_google_16k.tgz"},
    {"name": "036_wood_block", "berkeley": f"{S3_BASE}berkeley/036_wood_block/036_wood_block_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/036_wood_block_google_16k.tgz"},
    {"name": "037_scissors", "berkeley": f"{S3_BASE}berkeley/037_scissors/037_scissors_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/037_scissors_google_16k.tgz"},
    {"name": "040_large_marker", "berkeley": f"{S3_BASE}berkeley/040_large_marker/040_large_marker_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/040_large_marker_google_16k.tgz"},
    {"name": "051_large_clamp", "berkeley": f"{S3_BASE}berkeley/051_large_clamp/051_large_clamp_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/051_large_clamp_google_16k.tgz"},
    {"name": "052_extra_large_clamp", "berkeley": f"{S3_BASE}berkeley/052_extra_large_clamp/052_extra_large_clamp_berkeley_meshes.tgz", "google_16k": f"{S3_BASE}google/052_extra_large_clamp_google_16k.tgz"},
]


# ─── 工具函数 ──────────────────────────────────────────────────────────
def is_extracted(output_dir: Path, name: str) -> bool:
    target_dir = output_dir / name
    return target_dir.exists() and target_dir.is_dir()


def extract_archive(archive_path: Path, output_dir: Path, name: str) -> bool:
    print(f"  [解压] {archive_path.name} -> {output_dir / name}")
    try:
        if archive_path.suffixes[-2:] == [".tar", ".gz"] or archive_path.suffix == ".tgz":
            with tarfile.open(archive_path, "r:gz") as tf:
                tf.extractall(output_dir / name)
        else:
            print(f"  [警告] 不支持的压缩格式: {archive_path.name}")
            return False
        print(f"  [完成] 解压完成: {name}")
        return True
    except (tarfile.TarError, OSError) as e:
        print(f"  [错误] 解压失败 {name}: {e}")
        return False


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    display_name: str,
) -> bool:
    if dest.exists() and dest.stat().st_size > 0:
        print(f"  [跳过] 文件已存在: {dest.name}")
        return True

    print(f"  [下载] {display_name}")
    print(f"         URL: {url}")
    try:
        async with client.stream("GET", url) as resp:
            if resp.status_code != 200:
                print(f"  [错误] HTTP {resp.status_code} -- {display_name}")
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
async def run(objects: list[dict[str, str]], output_dir: Path, skip_existing: bool) -> None:
    print("=" * 70)
    print("YCB 物体数据集下载")
    print("=" * 70)
    print(f"  S3 基址: {S3_BASE}")
    print(f"  输出目录: {output_dir}")
    print(f"  物体数量: {len(objects)}")
    print(f"  跳过已解压: {'是' if skip_existing else '否'}")
    print()

    output_dir.mkdir(parents=True, exist_ok=True)
    success = 0
    failed = 0

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
        for obj in objects:
            name = obj["name"]

            if skip_existing and is_extracted(output_dir, name):
                print(f"  [跳过] 物体已解压: {name}")
                success += 1
                continue

            print(f"\n>>> 处理物体 [{name}]")
            obj_ok = False

            # 下载 berkeley meshes
            berkeley_url = obj["berkeley"]
            berkeley_archive = output_dir / f"{name}_berkeley_meshes.tgz"
            ok1 = await download_file(client, berkeley_url, berkeley_archive, display_name=f"{name} (berkeley meshes)")
            if ok1:
                extract_archive(berkeley_archive, output_dir, name)
                berkeley_archive.unlink(missing_ok=True)
                obj_ok = True

            # 下载 google 16k
            google_url = obj.get("google_16k", "")
            if google_url:
                google_archive = output_dir / f"{name}_google_16k.tgz"
                ok2 = await download_file(client, google_url, google_archive, display_name=f"{name} (google 16k)")
                if ok2:
                    extract_archive(google_archive, output_dir / name, f"{name}/google_16k")
                    google_archive.unlink(missing_ok=True)
                    obj_ok = True

            if obj_ok:
                success += 1
            else:
                failed += 1

    print()
    print("=" * 70)
    print(f"下载完成: 成功 {success}，失败 {failed}，共 {len(objects)}")
    print("=" * 70)


# ─── 入口 ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="YCB 物体数据集下载脚本")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/sources/datasets/ycb/models/"),
        help="输出目录（默认: data/sources/datasets/ycb/models/）",
    )
    parser.add_argument(
        "--objects",
        type=str,
        default="",
        help="逗号分隔的物体名列表（默认: 全部 20 个物体）",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="跳过已解压的物体",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir

    if args.objects:
        wanted = {n.strip() for n in args.objects.split(",") if n.strip()}
        objects = [o for o in YCB_OBJECTS if o["name"] in wanted]
        if not objects:
            print(f"  [错误] 未匹配到指定物体: {args.objects}")
            print("  可用物体名:")
            for o in YCB_OBJECTS:
                print(f"    - {o['name']}")
            sys.exit(1)
    else:
        objects = YCB_OBJECTS

    asyncio.run(run(objects, output_dir, args.skip_existing))


if __name__ == "__main__":
    main()