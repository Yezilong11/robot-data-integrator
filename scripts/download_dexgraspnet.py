"""
DexGraspNet 数据集下载脚本

功能：
- 从 HuggingFace 下载 DexGraspNet 灵巧手抓取数据集
- 支持断点续传

数据源：DexGraspNet
官方地址：https://huggingface.co/datasets/dexgraspnet
对接方式：HuggingFace 镜像
数据格式：numpy 数组 (.npy/.npz)
认证需求：无

输出目录：data/sources/datasets/dexgraspnet/
预估大小：~5 GB

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
from utils import download_file, format_size, get_data_dir


class DexGraspNetDownloader:
    """DexGraspNet 数据集下载器。"""

    def __init__(self):
        self.output_dir = get_data_dir() / "datasets" / "dexgraspnet"
        self.data_dir = self.output_dir / "data"

    async def get_dataset_info(self, client: httpx.AsyncClient) -> dict:
        """获取数据集信息。"""
        try:
            url = "https://huggingface.co/api/datasets/dexgraspnet/GraspNet"
            response = await client.get(url, timeout=30.0)

            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        # 尝试另一个可能的ID
        try:
            url = "https://huggingface.co/api/datasets/dexgraspnet"
            response = await client.get(url, timeout=30.0)

            if response.status_code == 200:
                return response.json()
        except Exception:
            pass

        return {}

    async def run(self, confirm: bool = False) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  DexGraspNet 数据集下载")
        print("  注意：此数据集约 5 GB")
        print("=" * 60)

        self.data_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            # 获取数据集信息
            print("\n获取数据集信息...")
            info = await self.get_dataset_info(client)

            if info:
                print(f"  数据集: {info.get('id', 'N/A')}")
                print(f"  描述: {info.get('description', 'N/A')[:100]}...")

                # 保存数据集元数据
                meta_path = self.output_dir / "dataset_info.json"
                meta_path.write_text(
                    json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            else:
                print("  [警告] 无法获取数据集信息，可能数据集ID已变更")

            if not confirm:
                print("\n即将下载 DexGraspNet 数据集 (~5 GB)")
                answer = input("确认下载？(y/N): ").strip().lower()
                if answer != "y":
                    print("已取消下载")
                    return

            # 尝试使用 huggingface_hub 下载
            try:
                from huggingface_hub import snapshot_download

                print("\n使用 huggingface_hub 下载...")
                # 尝试已知的数据集ID
                dataset_ids = [
                    "dexgraspnet/GraspNet",
                    "dexgraspnet",
                ]

                for dataset_id in dataset_ids:
                    try:
                        print(f"  尝试: {dataset_id}")
                        local_dir = snapshot_download(
                            repo_id=dataset_id,
                            repo_type="dataset",
                            local_dir=str(self.data_dir),
                        )
                        print(f"  ✅ 下载成功: {local_dir}")
                        return
                    except Exception as e:
                        print(f"  ⚠️ {dataset_id} 失败: {e}")
                        continue

                print("\n  [提示] 自动下载失败，请手动下载：")
                print("  pip install huggingface_hub")
                print("  huggingface-cli download dexgraspnet/GraspNet --repo-type dataset --local-dir data/sources/datasets/dexgraspnet/data")

            except ImportError:
                print("\n  [提示] huggingface_hub 未安装，请手动安装：")
                print("  pip install huggingface_hub")
                print("  然后运行：")
                print("  huggingface-cli download dexgraspnet/GraspNet --repo-type dataset --local-dir data/sources/datasets/dexgraspnet/data")

        # 保存下载说明
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "dataset": "DexGraspNet",
                    "huggingface_url": "https://huggingface.co/datasets/dexgraspnet",
                    "manual_download": "huggingface-cli download dexgraspnet/GraspNet --repo-type dataset --local-dir <output_dir>",
                    "estimated_size": "~5 GB",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n输出目录: {self.output_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="DexGraspNet 数据集下载")
    parser.add_argument("--confirm", action="store_true", help="跳过确认直接下载")
    args = parser.parse_args()

    downloader = DexGraspNetDownloader()
    asyncio.run(downloader.run(confirm=args.confirm))


if __name__ == "__main__":
    main()
