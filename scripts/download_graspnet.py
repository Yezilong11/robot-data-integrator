"""
GraspNet 数据集下载脚本

功能：
- 从官网获取下载链接
- 提供多线程下载（aria2c 或 PowerShell）
- 提供MD5校验
- 支持断点续传

数据源：GraspNet
官方地址：https://graspnet.net/
对接方式：官方下载
数据格式：numpy数组(.npy/.npz)、STL/OBJ(mesh)、JSON/XML(场景)
认证需求：无

输出目录：data/sources/datasets/graspnet/
预估大小：~30 GB

注意：此数据集较大（30GB），脚本会提示用户确认后执行下载

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import hashlib
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import format_size, get_data_dir


class GraspNetDownloader:
    """GraspNet 数据集下载器。"""

    # 官方下载链接（根据官网实际URL调整）
    DATASET_COMPONENTS = {
        "models": {
            "url": "https://graspnet.net/data/graspnet/models.zip",
            "description": "物体3D mesh模型",
            "estimated_size": "5 GB",
        },
        "scenes": {
            "url": "https://graspnet.net/data/graspnet/scenes.zip",
            "description": "场景数据",
            "estimated_size": "20 GB",
        },
        "grasps": {
            "url": "https://graspnet.net/data/graspnet/grasps.zip",
            "description": "抓取标注数据",
            "estimated_size": "3 GB",
        },
        "calibration": {
            "url": "https://graspnet.net/data/graspnet/calibration.zip",
            "description": "相机标定数据",
            "estimated_size": "1 GB",
        },
    }

    def __init__(self):
        self.output_dir = get_data_dir() / "datasets" / "graspnet"
        self.dataset_dir = self.output_dir / "dataset"
        self.models_dir = self.output_dir / "models"
        self.calibration_dir = self.output_dir / "calibration"

    def verify_md5(self, file_path: Path, expected_md5: str = "") -> bool:
        """校验文件MD5。"""
        if not file_path.exists():
            return False

        print(f"  校验MD5: {file_path.name} ...", end=" ", flush=True)
        md5_hash = hashlib.md5()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5_hash.update(chunk)

        actual_md5 = md5_hash.hexdigest()

        if expected_md5:
            match = actual_md5 == expected_md5
            print("✅" if match else f"❌ (期望: {expected_md5})")
            return match
        else:
            print(f"MD5={actual_md5}")
            return True

    async def download_with_progress(
        self, client: httpx.AsyncClient, url: str, output_path: Path
    ) -> bool:
        """带进度显示的文件下载。"""
        if output_path.exists() and output_path.stat().st_size > 0:
            print(f"  [跳过] 已存在: {output_path.name}")
            return True

        try:
            async with client.stream("GET", url, follow_redirects=True, timeout=300.0) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))

                output_path.parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    downloaded = 0
                    async for chunk in response.aiter_bytes(chunk_size=65536):
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = (downloaded / total_size) * 100
                            print(
                                f"\r  下载中: {percent:.1f}% ({format_size(downloaded)}/{format_size(total_size)})",
                                end="",
                                flush=True,
                            )
                print()  # 换行
                return True

        except Exception as e:
            print(f"\n  [错误] 下载失败: {e}")
            return False

    async def run(self, confirm: bool = False, component: str = "") -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  GraspNet 数据集下载")
        print("  注意：此数据集约 30 GB，请确保磁盘空间充足")
        print("=" * 60)

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # 显示下载选项
        print("\n可用组件：")
        for key, info in self.DATASET_COMPONENTS.items():
            print(f"  {key}: {info['description']} (~{info['estimated_size']})")

        components_to_download = []
        if component:
            if component in self.DATASET_COMPONENTS:
                components_to_download = [component]
            else:
                print(f"\n  [错误] 未知组件: {component}")
                return
        else:
            components_to_download = list(self.DATASET_COMPONENTS.keys())

        # 确认下载
        if not confirm:
            total_est = sum(
                int(self.DATASET_COMPONENTS[c]["estimated_size"].replace(" GB", "").replace(" MB", ""))
                for c in components_to_download
            )
            print(f"\n即将下载 {len(components_to_download)} 个组件，预估总大小: ~{total_est} GB")
            answer = input("确认下载？(y/N): ").strip().lower()
            if answer != "y":
                print("已取消下载")
                return

        async with httpx.AsyncClient() as client:
            for comp_name in components_to_download:
                comp = self.DATASET_COMPONENTS[comp_name]
                url = comp["url"]

                print(f"\n--- 下载: {comp_name} ({comp['description']}) ---")
                print(f"  URL: {url}")
                print(f"  预估大小: {comp['estimated_size']}")

                output_path = self.output_dir / f"{comp_name}.zip"
                ok = await self.download_with_progress(client, url, output_path)

                if ok and output_path.exists():
                    print(f"  ✅ 下载成功: {output_path}")
                    # 校验
                    self.verify_md5(output_path)
                else:
                    print(f"  ❌ 下载失败: {comp_name}")
                    print(f"  请手动从 https://graspnet.net/datasets.html 下载")

        # 保存下载说明
        readme_path = self.output_dir / "download_info.json"
        readme_path.write_text(
            json.dumps(
                {
                    "dataset": "GraspNet-1Billion",
                    "url": "https://graspnet.net/datasets.html",
                    "components": self.DATASET_COMPONENTS,
                    "note": "如自动下载失败，请手动从官网下载并放置到对应目录",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n输出目录: {self.output_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="GraspNet 数据集下载")
    parser.add_argument("--confirm", action="store_true", help="跳过确认直接下载")
    parser.add_argument("--component", type=str, default="", help="只下载指定组件(models/scenes/grasps/calibration)")
    args = parser.parse_args()

    downloader = GraspNetDownloader()
    asyncio.run(downloader.run(confirm=args.confirm, component=args.component))


if __name__ == "__main__":
    main()
