"""
Franka Panda URDF 下载脚本

功能：
- 下载 Panda 机械臂 URDF 模型
- 下载 mesh 文件
- 存储到本地目录

数据源：Franka
官方地址：https://franka.de/
对接方式：GitHub 仓库（frankaemika/franka_ros）
数据格式：URDF (XML)
认证需求：无

输出目录：data/sources/web/franka/panda/
预估大小：~50 MB

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


class FrankaDownloader:
    """Franka Panda URDF 下载器。"""

    # 使用 franka_ros 官方仓库中的 URDF 文件
    GITHUB_API = "https://api.github.com"
    REPO = "frankaemika/franka_ros"
    URDF_PATH = "franka_description/robots"

    def __init__(self):
        self.output_dir = get_data_dir() / "web" / "franka" / "panda"

    async def get_repo_tree(self, client: httpx.AsyncClient) -> list[dict]:
        """获取仓库文件树。"""
        headers = config.github_headers
        try:
            url = f"{self.GITHUB_API}/repos/{self.REPO}/git/trees/main"
            params = {"recursive": "1"}
            response = await client.get(url, headers=headers, params=params, timeout=30.0)
            response.raise_for_status()
            return response.json().get("tree", [])
        except Exception:
            # 尝试 master 分支
            try:
                url = f"{self.GITHUB_API}/repos/{self.REPO}/git/trees/master"
                params = {"recursive": "1"}
                response = await client.get(url, headers=headers, params=params, timeout=30.0)
                response.raise_for_status()
                return response.json().get("tree", [])
            except Exception as e:
                print(f"  [错误] 获取仓库文件树失败: {e}")
                return []

    async def download_file_from_github(
        self, client: httpx.AsyncClient, path: str, output_path: Path
    ) -> bool:
        """从 GitHub 下载单个文件。"""
        headers = config.github_headers
        url = f"{self.GITHUB_API}/repos/{self.REPO}/contents/{path}"

        try:
            response = await client.get(url, headers=headers, timeout=15.0)
            if response.status_code != 200:
                return False

            data = response.json()
            if data.get("encoding") == "base64":
                content = base64.b64decode(data["content"])
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(content)
                return True
        except Exception:
            pass

        # 回退：使用 raw URL
        try:
            raw_url = f"https://raw.githubusercontent.com/{self.REPO}/main/{path}"
            response = await client.get(raw_url, timeout=15.0, follow_redirects=True)
            if response.status_code == 200:
                output_path.parent.mkdir(parents=True, exist_ok=True)
                output_path.write_bytes(response.content)
                return True
        except Exception:
            pass

        return False

    async def run(self) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  Franka Panda URDF 下载")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n获取 Franka 仓库文件列表...")
            tree = await self.get_repo_tree(client)

            # 过滤 URDF 相关文件
            urdf_files = []
            for item in tree:
                path = item.get("path", "")
                if self.URDF_PATH in path and item.get("type") == "blob":
                    # 包含 URDF、mesh、配置文件
                    if any(path.endswith(ext) for ext in [".urdf", ".xacro", ".xml", ".stl", ".dae", ".yaml"]):
                        urdf_files.append(path)

            # 也检查 franka_description 下的其他路径
            for item in tree:
                path = item.get("path", "")
                if "franka_description" in path and item.get("type") == "blob":
                    if path not in urdf_files and any(
                        path.endswith(ext) for ext in [".urdf", ".xacro", ".xml", ".stl", ".dae", ".yaml", ".rviz"]
                    ):
                        urdf_files.append(path)

            if not urdf_files:
                print("  [警告] 未在仓库中找到 URDF 文件，尝试直接下载已知文件...")
                # 直接下载已知的 Panda URDF 文件
                known_files = [
                    "franka_description/robots/panda.urdf",
                    "franka_description/robots/panda_arm.urdf.xacro",
                    "franka_description/robots/hand.urdf.xacro",
                ]
                urdf_files = known_files

            print(f"  找到 {len(urdf_files)} 个相关文件\n")

            success_count = 0
            for path in urdf_files:
                # 保持目录结构
                rel_path = path.replace("franka_description/robots/", "")
                output_path = self.output_dir / rel_path

                print(f"  下载: {rel_path}...", end=" ", flush=True)
                ok = await self.download_file_from_github(client, path, output_path)
                print("✅" if ok else "❌")
                if ok:
                    success_count += 1

        # 保存下载信息
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "source": "frankaemika/franka_ros",
                    "url": "https://github.com/frankaemika/franka_ros",
                    "official": "https://franka.de/",
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
    downloader = FrankaDownloader()
    asyncio.run(downloader.run())


if __name__ == "__main__":
    main()
