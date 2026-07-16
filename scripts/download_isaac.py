"""下载 NVIDIA Isaac Sim 示例配置文件。

NVIDIA Isaac Sim 的 USD 资源通常无法从公开仓库直接下载，本脚本作为替代方案，
从 Isaac Sim 相关 GitHub 仓库下载示例 URDF/yaml/配置文件到本地。

优先尝试：
  1. NVIDIA-Omniverse/Isaac-Sim 工具：示例配置文档与脚本
  2. NVIDIA-ISAAC/IsaacLab 仓库：示例 URDF/yaml 配置

用法：
    python scripts/download_isaac.py
    python scripts/download_isaac.py --output-dir /path/to/output
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from _github_utils import (  # noqa: E402
    download_file,
    download_repo_tree,
    github_headers,
)

DEFAULT_OUTPUT = Path("data/sources/web/isaac/examples")
TIMEOUT = 30.0


async def _download_doc_examples(client: httpx.AsyncClient, output_dir: Path) -> int:
    """下载 Isaac Sim 文档站点的示例页面（作为元数据备份）。"""
    urls = [
        ("https://docs.isaacsim.omniverse.nvidia.com/latest/", "docs_index.html"),
        (
            "https://docs.isaacsim.omniverse.nvidia.com/latest/"
            "features/environment_setup/assets/usd_assets_robots.html",
            "usd_assets_robots.html",
        ),
    ]
    downloaded = 0
    for url, name in urls:
        try:
            ok = await download_file(client, url, output_dir / name, label=name)
            if ok:
                downloaded += 1
        except httpx.HTTPStatusError as e:
            print(f"  [警告] 跳过 {url}: HTTP {e.response.status_code}")
        except Exception as e:  # noqa: BLE001
            print(f"  [警告] 跳过 {url}: {e}")
    return downloaded


async def run(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    print("=== 下载 NVIDIA Isaac Sim 示例配置 ===")
    print(f"目标: {output_dir.resolve()}\n")

    # 候选仓库列表: (owner, repo, branch, tree_path, 本地子目录)
    candidates: list[tuple[str, str, str, str, Path]] = [
        (
            "isaac-sim",
            "IsaacLab",
            "main",
            "source/isaaclab_assets",
            output_dir / "isaaclab",
        ),
    ]

    total_down = 0
    total_skip = 0
    async with httpx.AsyncClient(timeout=TIMEOUT, headers=github_headers()) as client:
        # 先尝试从文档站点下载示例元数据页
        print("--- Isaac Sim 文档站点 ---")
        doc_down = await _download_doc_examples(client, output_dir)
        total_down += doc_down

        # 再尝试从 GitHub 仓库下载示例配置
        for owner, repo, branch, tree_path, sub_dir in candidates:
            print(f"\n--- github://{owner}/{repo}@{branch}/{tree_path} ---")
            down, skip = await download_repo_tree(
                client,
                owner=owner,
                repo=repo,
                path=tree_path,
                ref=branch,
                output_dir=sub_dir,
            )
            total_down += down
            total_skip += skip

    print(f"\n汇总: 下载 {total_down} 个文件, 跳过 {total_skip} 个已存在文件")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="下载 NVIDIA Isaac Sim 示例配置文件"
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