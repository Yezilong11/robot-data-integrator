"""
Isaac Sim 配置示例下载脚本

功能：
- 从 NVIDIA Isaac Sim 文档/仓库下载配置示例
- 下载 USD 场景配置示例

数据源：Isaac Sim
官方地址：https://developer.nvidia.com/isaac-sim
对接方式：文档解析 / GitHub 仓库
数据格式：USD（Universal Scene Description）
认证需求：无

输出目录：data/sources/web/isaac/examples/
预估大小：~10 MB

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import download_file, get_data_dir


class IsaacSimDownloader:
    """Isaac Sim 配置示例下载器。"""

    # Isaac Sim 相关仓库
    REPOS = [
        "NVIDIA-Omniverse/Isaac-Sim",
        "isaac-sim/IsaacSim",
    ]

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "isaac" / "examples"

    async def get_examples_from_repo(
        self, client: httpx.AsyncClient, repo: str
    ) -> list[dict]:
        """从仓库获取示例文件。"""
        headers = config.github_headers
        example_dirs = [
            "docs/source/examples",
            "standalone_examples",
            "source/examples",
            "exts/isaacsim.examples/data",
        ]

        files = []
        for directory in example_dirs:
            try:
                url = f"https://api.github.com/repos/{repo}/contents/{directory}"
                response = await client.get(url, headers=headers, timeout=15.0)

                if response.status_code != 200:
                    continue

                items = response.json()
                if isinstance(items, list):
                    for item in items:
                        name = item.get("name", "")
                        if item.get("type") == "file" and any(
                            name.endswith(ext) for ext in [".py", ".usd", ".usda", ".xml", ".yaml", ".json"]
                        ):
                            files.append({
                                "name": name,
                                "path": item["path"],
                                "download_url": item.get("download_url", ""),
                            })
                        elif item.get("type") == "dir":
                            # 递归获取子目录内容（一层）
                            try:
                                sub_url = item.get("url", "")
                                if sub_url:
                                    sub_resp = await client.get(sub_url, headers=headers, timeout=15.0)
                                    if sub_resp.status_code == 200:
                                        sub_items = sub_resp.json()
                                        if isinstance(sub_items, list):
                                            for sub_item in sub_items:
                                                sub_name = sub_item.get("name", "")
                                                if sub_item.get("type") == "file" and any(
                                                    sub_name.endswith(ext)
                                                    for ext in [".py", ".usd", ".usda", ".xml", ".yaml"]
                                                ):
                                                    files.append({
                                                        "name": sub_name,
                                                        "path": sub_item["path"],
                                                        "download_url": sub_item.get("download_url", ""),
                                                    })
                            except Exception:
                                pass

            except Exception:
                continue

        return files

    async def run(self) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  Isaac Sim 配置示例下载")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            all_files = []
            success_count = 0

            for repo in self.REPOS:
                print(f"\n尝试仓库: {repo}")
                files = await self.get_examples_from_repo(client, repo)

                if files:
                    print(f"  找到 {len(files)} 个示例文件")

                    for file_info in files:
                        name = file_info["name"]
                        download_url = file_info.get("download_url", "")

                        if not download_url:
                            # 使用 raw URL
                            download_url = f"https://raw.githubusercontent.com/{repo}/main/{file_info['path']}"

                        output_path = self.output_dir / name
                        print(f"  下载: {name}...", end=" ", flush=True)
                        ok = await download_file(download_url, output_path, client)
                        print("✅" if ok else "❌")
                        if ok:
                            all_files.append(file_info)
                            success_count += 1

                    if success_count > 0:
                        break  # 找到可用的仓库即可
                else:
                    print(f"  ⚠️ {repo} 未找到示例文件")

            if success_count == 0:
                print("\n  [提示] 自动下载失败，可手动获取：")
                print("  官方文档: https://docs.isaacsim.omniverse.nvidia.com/")
                print("  示例仓库: https://github.com/NVIDIA-Omniverse/Isaac-Sim")

                # 创建一个示例参考文档
                ref_path = self.output_dir / "reference.json"
                ref_path.write_text(
                    json.dumps(
                        {
                            "official_docs": "https://docs.isaacsim.omniverse.nvidia.com/",
                            "github_repo": "https://github.com/NVIDIA-Omniverse/Isaac-Sim",
                            "note": "Isaac Sim 示例通常随 Omniverse Launcher 安装，建议通过官方途径获取",
                        },
                        ensure_ascii=False,
                        indent=2,
                    ),
                    encoding="utf-8",
                )

        # 保存下载信息
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "source": self.REPOS,
                    "official": "https://developer.nvidia.com/isaac-sim",
                    "docs": "https://docs.isaacsim.omniverse.nvidia.com/",
                    "files": [f["name"] for f in all_files],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {success_count} 个示例文件")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    downloader = IsaacSimDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
