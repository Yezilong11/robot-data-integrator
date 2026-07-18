"""
Allegro 灵巧手 URDF 下载脚本

功能：
- 下载 Allegro 灵巧手 URDF 模型
- 存储描述文件和 mesh

数据源：Allegro
官方地址：https://www.wonikrobotics.com/
对接方式：GitHub 仓库
数据格式：URDF (XML)
认证需求：无

输出目录：data/sources/web/allegro/hand/
预估大小：~30 MB

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
from utils import get_data_dir


class AllegroDownloader:
    """Allegro 灵巧手 URDF 下载器。"""

    # 多个可能的仓库源
    REPOS = [
        "allegrohand/allegro_hand_ros",
        "SimLab/Allegro-Hand",
        "wonikrobotics/allegro_hand",
    ]

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "allegro" / "hand"

    async def download_from_repo(
        self, client: httpx.AsyncClient, repo: str
    ) -> tuple[list[str], int]:
        """从指定仓库下载 URDF 文件。"""
        headers = config.github_headers
        success_count = 0
        downloaded_files = []

        # 获取仓库文件树
        for branch in ["main", "master", "melodic-devel"]:
            try:
                url = f"https://api.github.com/repos/{repo}/git/trees/{branch}"
                params = {"recursive": "1"}
                response = await client.get(url, headers=headers, params=params, timeout=30.0)

                if response.status_code != 200:
                    continue

                tree = response.json().get("tree", [])
                urdf_files = [
                    item["path"]
                    for item in tree
                    if item.get("type") == "blob"
                    and any(item["path"].endswith(ext) for ext in [".urdf", ".xacro", ".stl", ".dae", ".yaml"])
                ]

                for path in urdf_files:
                    raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{path}"
                    output_path = self.output_dir / path.replace("urdf/", "").replace("meshes/", "")

                    try:
                        resp = await client.get(raw_url, timeout=15.0, follow_redirects=True)
                        if resp.status_code == 200:
                            output_path.parent.mkdir(parents=True, exist_ok=True)
                            output_path.write_bytes(resp.content)
                            success_count += 1
                            downloaded_files.append(path)
                    except Exception:
                        pass

                return downloaded_files, success_count

            except Exception:
                continue

        return [], 0

    async def run(self) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  Allegro 灵巧手 URDF 下载")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            all_files = []
            total_success = 0

            for repo in self.REPOS:
                print(f"\n尝试仓库: {repo}")
                files, count = await self.download_from_repo(client, repo)

                if count > 0:
                    print(f"  ✅ 从 {repo} 下载 {count} 个文件")
                    all_files.extend(files)
                    total_success += count
                    break  # 找到一个可用的仓库即可
                else:
                    print(f"  ⚠️ {repo} 不可用")

            if total_success == 0:
                print("\n  [提示] 自动下载失败，可手动下载：")
                print("  git clone https://github.com/allegrohand/allegro_hand_ros.git")
                print(f"  将 URDF 文件复制到: {self.output_dir}")

        # 保存下载信息
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "source": self.REPOS,
                    "official": "https://www.wonikrobotics.com/",
                    "files": all_files,
                    "manual_clone": "git clone https://github.com/allegrohand/allegro_hand_ros.git",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {total_success} 个文件成功")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    downloader = AllegroDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
