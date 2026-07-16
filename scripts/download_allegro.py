"""下载 Allegro 灵巧手 URDF 与 mesh 文件。

从 WonikRobotics/allegro 仓库下载 Allegro Hand URDF 描述及关联 mesh 到本地。

用法：
    python scripts/download_allegro.py
    python scripts/download_allegro.py --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _github_utils import download_repo_tree, github_headers  # noqa: E402

OWNER = "simlabrobotics"
REPO = "allegro_hand_model_v4"
BRANCH = "main"

# Allegro Hand description 目录（根目录即包含 URDF/mesh）
TREE_PATHS = [""]

DEFAULT_OUTPUT = Path("data/sources/web/allegro/hand")
TIMEOUT = 30.0


async def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("=== 下载 Allegro 灵巧手 URDF/mesh ===")
    print(f"源:   github://{OWNER}/{REPO}@{BRANCH}")
    print(f"目标: {output_dir.resolve()}\n")

    total_down = 0
    total_skip = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=github_headers()) as client:
        for tree_path in TREE_PATHS:
            print(f"\n--- 处理子目录: {tree_path} ---")
            down, skip = await download_repo_tree(
                client,
                owner=OWNER,
                repo=REPO,
                path=tree_path,
                ref=BRANCH,
                output_dir=output_dir / tree_path,
            )
            total_down += down
            total_skip += skip
    print(f"\n汇总: 下载 {total_down} 个文件, 跳过 {total_skip} 个已存在文件")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载 Allegro 灵巧手 URDF + mesh 文件"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"输出目录 (默认 {DEFAULT_OUTPUT})",
    )
    args = parser.parse_args()
    asyncio.run(run(args.output_dir))


if __name__ == "__main__":
    main()