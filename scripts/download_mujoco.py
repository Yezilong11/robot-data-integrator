"""
MuJoCo 配置示例下载脚本

功能：
- 从 MuJoCo 官方仓库下载 MJCF 示例文件
- 下载仿真配置 XML

数据源：MuJoCo
官方地址：https://mujoco.org/
对接方式：GitHub 仓库（google-deepmind/mujoco）
数据格式：MJCF (XML)
认证需求：无

输出目录：data/sources/web/mujoco/examples/
预估大小：~5 MB

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


class MuJoCoDownloader:
    """MuJoCo 示例配置下载器。"""

    GITHUB_API = "https://api.github.com"
    REPO = "google-deepmind/mujoco"

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "mujoco" / "examples"

    async def get_example_files(self, client: httpx.AsyncClient) -> list[dict]:
        """获取 MuJoCo 模型示例文件列表。"""
        headers = config.github_headers
        example_dirs = ["model", "model/humanoid", "model/quadrotor", "model/reacher"]

        files = []
        for directory in example_dirs:
            try:
                url = f"{self.GITHUB_API}/repos/{self.REPO}/contents/{directory}"
                response = await client.get(url, headers=headers, timeout=15.0)

                if response.status_code != 200:
                    continue

                items = response.json()
                if isinstance(items, list):
                    for item in items:
                        if item.get("type") == "file" and item.get("name", "").endswith(".xml"):
                            files.append({
                                "name": item["name"],
                                "path": item["path"],
                                "download_url": item.get("download_url", ""),
                            })

            except Exception:
                continue

        return files

    async def run(self) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  MuJoCo 配置示例下载")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n获取 MuJoCo 模型文件列表...")
            files = await self.get_example_files(client)
            print(f"  找到 {len(files)} 个示例文件\n")

            if not files:
                print("  [警告] 未找到文件，尝试直接下载已知示例...")
                # 尝试直接下载一些已知的经典示例
                known_examples = [
                    "humanoid/humanoid.xml",
                    "humanoid/humanoid100.xml",
                    "reacher/reacher.xml",
                    "quadrotor/quadrotor.xml",
                    "cartpole/cartpole.xml",
                    "ant/ant.xml",
                    "swimmer/swimmer.xml",
                    "walker/walker.xml",
                    "half_cheetah/half_cheetah.xml",
                    "hopper/hopper.xml",
                ]

                for example in known_examples:
                    raw_url = f"https://raw.githubusercontent.com/{self.REPO}/main/model/{example}"
                    output_path = self.output_dir / example
                    ok = await download_file(raw_url, output_path, client)
                    if ok:
                        files.append({"name": example, "path": f"model/{example}"})
            else:
                # 下载找到的文件
                success_count = 0
                for file_info in files:
                    name = file_info["name"]
                    download_url = file_info.get("download_url", "")

                    if not download_url:
                        # 使用 raw URL
                        download_url = f"https://raw.githubusercontent.com/{self.REPO}/main/{file_info['path']}"

                    output_path = self.output_dir / name
                    print(f"  下载: {name}...", end=" ", flush=True)
                    ok = await download_file(download_url, output_path, client)
                    print("✅" if ok else "❌")
                    if ok:
                        success_count += 1

        # 保存下载信息
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "source": "google-deepmind/mujoco",
                    "url": "https://github.com/google-deepmind/mujoco",
                    "official": "https://mujoco.org/",
                    "docs": "https://mujoco.readthedocs.io/",
                    "files": [f["name"] for f in files],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {len(files)} 个示例文件")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    downloader = MuJoCoDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
