"""下载 Franka Panda 机器人 URDF 描述文件。

从 frankarobotics/franka_ros 仓库（develop 分支）下载 franka_description/robots/
panda 目录下的 URDF + mesh 文件到本地。

用法：
    python scripts/download_franka.py
    python scripts/download_franka.py --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

# 允许 import 同目录下 _github_utils
sys.path.insert(0, str(Path(__file__).parent))
from _github_utils import download_repo_tree, github_headers  # noqa: E402

OWNER = "frankarobotics"
REPO = "franka_ros"
BRANCH = "develop"
TREE_PATH = "franka_description/robots/panda"

DEFAULT_OUTPUT = Path("data/sources/web/franka/panda")
TIMEOUT = 30.0


async def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"=== 下载 Franka Panda URDF/mesh ===")
    print(f"源:   github://{OWNER}/{REPO}@{BRANCH}/{TREE_PATH}")
    print(f"目标: {output_dir.resolve()}\n")

    async with httpx.AsyncClient(timeout=TIMEOUT, headers=github_headers()) as client:
        downloaded, skipped = await download_repo_tree(
            client,
            owner=OWNER,
            repo=REPO,
            path=TREE_PATH,
            ref=BRANCH,
            output_dir=output_dir,
        )
    print(f"\n汇总: 下载 {downloaded} 个文件, 跳过 {skipped} 个已存在文件")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载 Franka Panda URDF + mesh 文件"
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