"""GraspNet 数据集下载辅助脚本。

GraspNet 数据集约 30GB，无法完全自动下载。脚本功能：
1. 打开 https://graspnet.net/datasets.html，提示用户手动下载具体数据
2. 提供 MD5 校验功能：读取 MD5 校验和文件并验证下载的数据
3. 创建 data/sources/datasets/graspnet/dataset/ 下需要的子目录结构

用法：
    python scripts/download_graspnet.py                 # 打印下载说明并创建目录
    python scripts/download_graspnet.py --verify        # 校验模式
    python scripts/download_graspnet.py --output-dir data/sources/datasets/graspnet/
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
from pathlib import Path

import httpx

# ─── 常量 ──────────────────────────────────────────────────────────────
DATASET_PAGE = "https://graspnet.net/datasets.html"
TIMEOUT = 30.0

# GraspNet 数据集各分量的下载入口（用户需在浏览器手动下载）
# 来源：https://graspnet.net/datasets.html
DOWNLOAD_ITEMS: list[dict[str, str]] = [
    {
        "name": "graspnet-baseline",
        "url": "https://graspnet.net/",
        "description": "GraspNet-Baseline 完整数据集（点云 + 抓取标注，约 30GB）",
    },
    {
        "name": "collision-data",
        "url": "https://graspnet.net/",
        "description": "碰撞检测数据（collision-data）",
    },
    {
        "name": "graspnet-1billion",
        "url": "https://graspnet.net/",
        "description": "GraspNet-1Billion 抓取数据集",
    },
    {
        "name": "models",
        "url": "https://graspnet.net/",
        "description": "物体 CAD 模型（models）",
    },
    {
        "name": "calibration",
        "url": "https://graspnet.net/",
        "description": "相机标定参数（calibration）",
    },
]

# dataset/ 下需创建的子目录结构
DATASET_SUBDIRS = [
    "scene_0000",
    "scene_0001",
    "scene_0002",
    "models",
    "collision_data",
    "grasp_labels",
    "registration",
]


# ─── 工具函数 ──────────────────────────────────────────────────────────
def compute_md5(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """计算文件的 MD5 哈希值。"""
    md5 = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def parse_md5_file(md5_path: Path) -> dict[str, str]:
    """解析 MD5 校验和文件，返回 {filename: md5sum} 映射。

    支持两种格式：
        1. "<md5>  <filename>"  （md5sum 标准输出）
        2. "<filename>: <md5>"  （冒号分隔）
    """
    mapping: dict[str, str] = {}
    if not md5_path.exists():
        print(f"  [警告] MD5 校验和文件不存在: {md5_path}")
        return mapping
    for line in md5_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and "  " not in line:
            # filename: md5
            name, _, value = line.partition(":")
            mapping[name.strip()] = value.strip().lower()
        else:
            parts = line.split()
            if len(parts) >= 2:
                value, name = parts[0], parts[-1]
                mapping[Path(name).name] = value.lower()
    return mapping


def create_directory_structure(output_dir: Path) -> None:
    """创建 graspnet/dataset/ 下的子目录结构。"""
    dataset_root = output_dir / "dataset"
    for sub in DATASET_SUBDIRS:
        (dataset_root / sub).mkdir(parents=True, exist_ok=True)
    # 也创建 models / calibration 顶层目录
    (output_dir / "models").mkdir(parents=True, exist_ok=True)
    (output_dir / "calibration").mkdir(parents=True, exist_ok=True)
    print(f"  [目录] 已创建目录结构: {dataset_root}")


# ─── 下载说明 ──────────────────────────────────────────────────────────
async def print_download_instructions(output_dir: Path) -> None:
    """抓取数据集页面并打印下载说明与 URL 列表。"""
    print("=" * 70)
    print("GraspNet 数据集下载说明")
    print("=" * 70)
    print()
    print("GraspNet 数据集约 30GB，无法通过脚本完全自动下载。")
    print("请在浏览器中访问以下页面手动下载数据：")
    print()
    print(f"  数据集首页: {DATASET_PAGE}")
    print()
    print("可用数据分量：")
    for item in DOWNLOAD_ITEMS:
        print(f"  - {item['name']}")
        print(f"    说明: {item['description']}")
        print(f"    入口: {item['url']}")
    print()
    print(f"请将下载的数据放置到以下目录（或其子目录）：")
    print(f"  {output_dir / 'dataset'}")
    print()
    print("建议的目录布局：")
    print("  dataset/scene_XXXX/      每个场景的点云与标注")
    print("  dataset/models/          物体 CAD 模型")
    print("  dataset/collision_data/ 碰撞检测数据")
    print("  dataset/grasp_labels/   抓取标签")
    print()
    print("下载完成后可使用以下命令做 MD5 校验：")
    print(f"  python scripts/download_graspnet.py --verify --output-dir {output_dir}")
    print()

    # 尝试访问数据集页面确认可达性
    print("正在检测数据集页面连通性...")
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(DATASET_PAGE)
            if resp.status_code == 200:
                print(f"  [连通] {DATASET_PAGE} (HTTP {resp.status_code})")
            else:
                print(f"  [警告] {DATASET_PAGE} 返回 HTTP {resp.status_code}")
    except httpx.HTTPError as e:
        print(f"  [错误] 无法访问 {DATASET_PAGE}: {e}")


# ─── 校验模式 ──────────────────────────────────────────────────────────
def verify_directory(output_dir: Path) -> int:
    """遍历 output_dir 下所有文件，与 MD5 校验和文件比对。

    返回校验失败的文件数量（0 表示全部通过）。
    """
    print("=" * 70)
    print("GraspNet 数据集 MD5 校验")
    print("=" * 70)
    print(f"  目标目录: {output_dir}")
    print()

    # 查找 MD5 校验和文件（md5sum.txt / MD5SUMS / *.md5）
    md5_files: list[Path] = []
    for pattern in ("md5sum.txt", "MD5SUMS", "MD5SUM.txt", "md5.txt"):
        found = list(output_dir.rglob(pattern))
        md5_files.extend(found)
    md5_files.extend(output_dir.rglob("*.md5"))

    if not md5_files:
        print("  [警告] 未找到 MD5 校验和文件（md5sum.txt / *.md5），跳过 MD5 校验。")
        print("  将仅检查文件大小是否大于 0。")
        return _check_nonempty(output_dir)

    total_failed = 0
    for md5_path in md5_files:
        print(f"  [校验] 使用校验文件: {md5_path}")
        mapping = parse_md5_file(md5_path)
        base_dir = md5_path.parent
        for filename, expected_md5 in mapping.items():
            target = base_dir / filename
            if not target.exists():
                print(f"    [缺失] {filename} —— 文件不存在")
                total_failed += 1
                continue
            actual = compute_md5(target)
            if actual == expected_md5:
                print(f"    [通过] {filename} ({actual})")
            else:
                print(f"    [失败] {filename}")
                print(f"           期望: {expected_md5}")
                print(f"           实际: {actual}")
                total_failed += 1

    print()
    if total_failed == 0:
        print("  [完成] 所有 MD5 校验通过。")
    else:
        print(f"  [完成] 校验结束，{total_failed} 个文件校验失败。")
    return total_failed


def _check_nonempty(output_dir: Path) -> int:
    """无 MD5 文件时，仅检查文件大小 > 0。返回空文件数量。"""
    empty_count = 0
    file_count = 0
    for path in output_dir.rglob("*"):
        if path.is_file():
            file_count += 1
            size = path.stat().st_size
            if size == 0:
                print(f"    [空文件] {path}")
                empty_count += 1
    print(f"  [统计] 共 {file_count} 个文件，{empty_count} 个空文件。")
    return empty_count


# ─── 入口 ──────────────────────────────────────────────────────────────
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GraspNet 数据集下载辅助脚本（手动下载 + MD5 校验）"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="校验模式：验证已下载数据的 MD5 校验和",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/sources/datasets/graspnet/"),
        help="数据集根目录（默认: data/sources/datasets/graspnet/）",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.verify:
        failed = verify_directory(output_dir)
        sys.exit(1 if failed > 0 else 0)
    else:
        create_directory_structure(output_dir)
        asyncio.run(print_download_instructions(output_dir))


if __name__ == "__main__":
    main()