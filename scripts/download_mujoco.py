"""下载 MuJoCo 示例 MJCF XML 文件。

从 google-deepmind/mujoco 仓库下载 model/ 目录下的示例 MJCF XML 到本地。
至少包含 humanoid.xml、scene.xml 等基本示例。

用法：
    python scripts/download_mujoco.py
    python scripts/download_mujoco.py --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _github_utils import download_repo_tree, github_headers  # noqa: E402

OWNER = "google-deepmind"
REPO = "mujoco"
BRANCH = "main"

# model/ 目录包含 humanoid.xml、scene.xml 等示例
TREE_PATH = "model"

DEFAULT_OUTPUT = Path("data/sources/web/mujoco/examples")
TIMEOUT = 30.0


async def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("=== 下载 MuJoCo 示例 MJCF XML ===")
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
        description="下载 MuJoCo 示例 MJCF XML 文件"
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