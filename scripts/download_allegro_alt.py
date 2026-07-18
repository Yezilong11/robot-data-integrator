"""
Allegro 灵巧手 URDF 备用下载脚本

功能：
- 当官方 Wonik Robotics 官网超时时，尝试多个备选源
- 从 GitHub 镜像下载 Allegro Hand ROS 包
- 自动选择可用的 URDF/XACRO 文件

数据源：Allegro Hand
官网（超时）：https://www.wonikrobotics.com/
GitHub 备选：https://github.com/allegrohand/allegro_hand_ros

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
from utils import format_size, get_data_dir

# 备选仓库列表
REPOS = [
    "allegrohand/allegro_hand_ros",
    "SimLab/Allegro-Hand",
    "CatherinaW/AnynetGrasping",
    "kasmith/allegro_hand_ros",
]

# 关键文件路径
KEY_FILES = [
    "allegro_hand_description/urdf/allegro_hand.urdf.xacro",
    "allegro_hand_description/urdf/allegro_hand.urdf",
    "allegro_hand_description/meshes/",
    "allegro_hand_description/urdf/allegro_hand_right.urdf.xacro",
    "allegro_hand_description/urdf/allegro_hand_left.urdf.xacro",
]


async def try_repo(
    client: httpx.AsyncClient, repo: str, output_dir: Path, headers: dict
) -> tuple[bool, list[str]]:
    """尝试从指定仓库下载。"""
    downloaded_files = []

    for branch in ["main", "master", "kinetic-devel", "noetic-devel"]:
        print(f"    尝试分支: {branch}")

        for file_path in KEY_FILES:
            # 跳过目录
            if file_path.endswith("/"):
                continue

            raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{file_path}"
            file_name = file_path.split("/")[-1]
            output_path = output_dir / file_name

            try:
                response = await client.get(raw_url, timeout=15.0, follow_redirects=True)
                if response.status_code == 200 and len(response.content) > 100:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    output_path.write_bytes(response.content)
                    downloaded_files.append(file_name)
                    print(f"      ✅ {file_name} ({format_size(len(response.content))})")
            except Exception:
                continue

    # 尝试从 GitHub API 获取整个仓库结构
    if not downloaded_files:
        try:
            for branch in ["main", "master"]:
                url = f"https://api.github.com/repos/{repo}/git/trees/{branch}"
                response = await client.get(url, headers=headers, params={"recursive": "1"}, timeout=15.0)
                if response.status_code == 200:
                    tree = response.json().get("tree", [])
                    # 过滤 URDF/mesh 相关文件
                    urdf_files = [
                        item["path"] for item in tree
                        if item.get("type") == "blob"
                        and any(item["path"].endswith(ext) for ext in [".urdf", ".xacro", ".stl", ".dae", ".yaml"])
                        and ("urdf" in item["path"].lower() or "mesh" in item["path"].lower())
                    ]

                    for f_path in urdf_files[:20]:  # 限制数量
                        raw_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{f_path}"
                        file_name = f_path.split("/")[-1]
                        output_path = output_dir / file_name

                        try:
                            resp = await client.get(raw_url, timeout=15.0, follow_redirects=True)
                            if resp.status_code == 200:
                                output_path.parent.mkdir(parents=True, exist_ok=True)
                                output_path.write_bytes(resp.content)
                                downloaded_files.append(file_name)
                                print(f"      ✅ {file_name}")
                        except Exception:
                            pass

                    if downloaded_files:
                        break
        except Exception:
            pass

    return len(downloaded_files) > 0, downloaded_files


async def run() -> None:
    """执行 Allegro URDF 下载。"""
    print("=" * 60)
    print("  Allegro 灵巧手 URDF 下载（备用方案）")
    print("=" * 60)

    output_dir = get_data_dir() / "web" / "allegro" / "hand"
    output_dir.mkdir(parents=True, exist_ok=True)

    headers = config.github_headers

    print(f"\n输出目录: {output_dir}")
    print(f"尝试 {len(REPOS)} 个备选仓库\n")

    async with httpx.AsyncClient() as client:
        client.headers["User-Agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

        for repo in REPOS:
            print(f"\n尝试仓库: {repo}")
            ok, files = await try_repo(client, repo, output_dir, headers)
            if ok:
                print(f"  ✅ 成功从 {repo} 下载 {len(files)} 个文件")
                # 保存下载信息
                info = {
                    "source": repo,
                    "files": files,
                    "official_website": "https://www.wonikrobotics.com/",
                    "note": "Wonik Robotics 官网访问超时，使用 GitHub 备选源",
                }
                (output_dir / "download_info.json").write_text(
                    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                break
            else:
                print(f"  ❌ {repo} 不可用")

    # 统计
    total_size = sum(f.stat().st_size for f in output_dir.rglob("*") if f.is_file())
    file_count = sum(1 for f in output_dir.rglob("*") if f.is_file())

    print(f"\n" + "=" * 60)
    print(f"  下载完成")
    print(f"  文件数: {file_count}")
    print(f"  总大小: {format_size(total_size)}")
    print(f"  输出目录: {output_dir}")
    print(f"=" * 60)

    if file_count == 0:
        print(f"\n⚠️  所有备选源都不可用，建议：")
        print(f"  1. 手动访问 https://www.wonikrobotics.com/ 下载 Allegro Hand SDK")
        print(f"  2. 或使用 git clone: git clone https://github.com/allegrohand/allegro_hand_ros.git")


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
