"""
YCB Objects 数据集下载脚本

功能：
- 从官网下载物体3D模型
- 格式：STL/OBJ/PLY
- 支持断点续传

数据源：YCB Dataset
官方地址：https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/
对接方式：官方下载
数据格式：STL/OBJ/PLY
认证需求：无

输出目录：data/sources/datasets/ycb/
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


class YCBDownloader:
    """YCB Objects 数据集下载器。"""

    # YCB 物体列表（标准20个物体）
    YCB_OBJECTS = [
        "002_master_chef_can",
        "003_cracker_box",
        "004_sugar_box",
        "005_tomato_soup_can",
        "006_mustard_bottle",
        "007_tuna_fish_can",
        "008_pudding_box",
        "009_gelatin_box",
        "010_potted_meat_can",
        "011_banana",
        "019_strawberry",
        "021_bleach_cleanser",
        "024_bowl",
        "025_mug",
        "035_power_drill",
        "036_wood_block",
        "037_scissors",
        "040_large_marker",
        "051_extra_large_clamp",
        "052_extra_large_clamp",
    ]

    # 下载基础URL（YCB数据集托管在多个位置）
    BASE_URL = "https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/data"

    def __init__(self):
        self.output_dir = get_data_dir() / "datasets" / "ycb"
        self.models_dir = self.output_dir / "models"

    async def get_available_links(self, client: httpx.AsyncClient) -> list[dict]:
        """从官网解析可用的下载链接。"""
        try:
            response = await client.get(
                "https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/",
                timeout=30.0,
                follow_redirects=True,
            )
            # 简单返回已知URL模板
            return [
                {
                    "name": obj,
                    "url": f"{self.BASE_URL}/{obj}.zip",
                }
                for obj in self.YCB_OBJECTS
            ]
        except Exception:
            return [
                {
                    "name": obj,
                    "url": f"{self.BASE_URL}/{obj}.zip",
                }
                for obj in self.YCB_OBJECTS
            ]

    async def run(self, confirm: bool = False) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  YCB Objects 数据集下载")
        print("  注意：此数据集约 5 GB")
        print("=" * 60)

        self.models_dir.mkdir(parents=True, exist_ok=True)

        if not confirm:
            print(f"\n即将下载 {len(self.YCB_OBJECTS)} 个物体模型")
            answer = input("确认下载？(y/N): ").strip().lower()
            if answer != "y":
                print("已取消下载")
                return

        async with httpx.AsyncClient() as client:
            links = await self.get_available_links(client)

            print(f"\n开始下载 {len(links)} 个物体模型...")
            success_count = 0

            for item in links:
                obj_name = item["name"]
                obj_dir = self.models_dir / obj_name
                obj_dir.mkdir(parents=True, exist_ok=True)

                print(f"\n  下载: {obj_name}")

                # 尝试下载不同格式
                for fmt in ["zip", "tar.gz"]:
                    url = f"{self.BASE_URL}/{obj_name}.{fmt}"
                    output_path = obj_dir / f"{obj_name}.{fmt}"

                    ok = await download_file(url, output_path, client)
                    if ok:
                        success_count += 1
                        print(f"    ✅ {fmt}")
                        break
                else:
                    print(f"    ⚠️ 自动下载失败，请手动下载")
                    print(f"    官网: https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/")

        # 保存下载说明
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "dataset": "YCB-Video",
                    "url": "https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/",
                    "objects": self.YCB_OBJECTS,
                    "note": "如自动下载失败，请手动从官网下载并解压到 models/ 目录",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {success_count}/{len(links)} 个物体成功")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="YCB Objects 数据集下载")
    parser.add_argument("--confirm", action="store_true", help="跳过确认直接下载")
    args = parser.parse_args()

    downloader = YCBDownloader()
    asyncio.run(downloader.run(confirm=args.confirm))


if __name__ == "__main__":
    main()
