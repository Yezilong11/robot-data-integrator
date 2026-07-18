"""
Robotiq 夹爪 URDF 下载脚本

功能：
- 下载 Robotiq 夹爪 URDF 模型
- 存储 gripper 描述文件和 mesh

数据源：Robotiq
官方地址：https://robotiq.com/
对接方式：GitHub 仓库（ros-industrial/robotiq）
数据格式：URDF (XML)
认证需求：无

输出目录：data/sources/web/robotiq/grippers/
预估大小：~20 MB

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import download_file, get_data_dir


class RobotiqDownloader:
    """Robotiq 夹爪 URDF 下载器。"""

    GITHUB_API = "https://api.github.com"
    REPO = "ros-industrial/robotiq"

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "robotiq" / "grippers"

    async def get_repo_tree(self, client: httpx.AsyncClient) -> list[dict]:
        """获取仓库文件树。"""
        headers = config.github_headers
        for branch in ["main", "master", "melodic-devel", "noetic-devel"]:
            try:
                url = f"{self.GITHUB_API}/repos/{self.REPO}/git/trees/{branch}"
                params = {"recursive": "1"}
                response = await client.get(url, headers=headers, params=params, timeout=30.0)
                if response.status_code == 200:
                    return response.json().get("tree", [])
            except Exception:
                continue
        return []

    async def download_file_from_github(
        self, client: httpx.AsyncClient, path: str, output_path: Path, branch: str = "main"
    ) -> bool:
        """从 GitHub 下载单个文件。"""
        # 尝试多个分支
        for b in [branch, "main", "master", "melodic-devel", "noetic-devel"]:
            try:
                raw_url = f"https://raw.githubusercontent.com/{self.REPO}/{b}/{path}"
                response = await client.get(raw_url, timeout=15.0, follow_redirects=True)
                if response.status_code == 200:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.content)
                    return True
            except Exception:
                continue
        return False

    async def run(self) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  Robotiq 夹爪 URDF 下载")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n获取 Robotiq 仓库文件列表...")
            tree = await self.get_repo_tree(client)

            # 过滤 URDF 相关文件
            urdf_files = []
            for item in tree:
                path = item.get("path", "")
                if item.get("type") == "blob" and any(
                    path.endswith(ext) for ext in [".urdf", ".xacro", ".xml", ".stl", ".dae", ".yaml"]
                ):
                    urdf_files.append(path)

            if not urdf_files:
                print("  [警告] 未在仓库中找到文件，尝试已知文件路径...")
                known_files = [
                    "robotiq_2f_85_gripper_visualization/urdf/robotiq_2f_85.urdf",
                    "robotiq_2f_140_gripper_visualization/urdf/robotiq_2f_140.urdf",
                    "robotiq_3f_gripper_visualization/urdf/robotiq_3f.urdf",
                ]
                urdf_files = known_files

            print(f"  找到 {len(urdf_files)} 个相关文件\n")

            success_count = 0
            for path in urdf_files:
                output_path = self.output_dir / path
                rel_name = path.split("/")[-1]

                print(f"  下载: {rel_name}...", end=" ", flush=True)
                ok = await self.download_file_from_github(client, path, output_path)
                print("✅" if ok else "❌")
                if ok:
                    success_count += 1

        # 保存下载信息
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "source": "ros-industrial/robotiq",
                    "url": "https://github.com/ros-industrial/robotiq",
                    "official": "https://robotiq.com/",
                    "files": urdf_files,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {success_count}/{len(urdf_files)} 个文件成功")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    downloader = RobotiqDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
