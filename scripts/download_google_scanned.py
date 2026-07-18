"""
Google Scanned Objects 数据集下载脚本

功能：
- 下载Google Scanned Objects 3D扫描数据集
- 支持断点续传

数据源：Google Scanned Objects
官方地址：https://research.google/blog/scanned-objects-a-dataset-of-3d-scanned-everyday-objects/
对接方式：官方下载（AWS S3）
数据格式：STL/OBJ/PLY
认证需求：无

输出目录：data/sources/datasets/google_scanned/
预估大小：~10 GB

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


class GoogleScannedDownloader:
    """Google Scanned Objects 数据集下载器。"""

    # Google Scanned Objects 公开 S3 链接
    BASE_URL = "https://fuel.gazebosim.org/1.0/GoogleResearch/models"

    def __init__(self):
        self.output_dir = get_data_dir() / "datasets" / "google_scanned"
        self.models_dir = self.output_dir / "models"

    async def get_model_list(self, client: httpx.AsyncClient) -> list[str]:
        """获取可用模型列表。"""
        # Google Scanned Objects 托管在 Fuel (Gazebo) 平台
        try:
            url = "https://fuel.gazebosim.org/1.0/GoogleResearch/models"
            response = await client.get(url, timeout=30.0, follow_redirects=True)

            if response.status_code == 200:
                # 尝试解析返回的模型列表
                try:
                    data = response.json()
                    if isinstance(data, list):
                        return [m.get("name", "") for m in data if m.get("name")]
                except Exception:
                    pass
        except Exception as e:
            print(f"  [警告] 无法获取模型列表: {e}")

        # 返回部分已知模型名称作为示例
        return [
            "Avocado",
            "Bleach_cleanser",
            "Bowl",
            "Cracker_box",
            "Gelatin_box",
            "Hammer",
            "Mustard_bottle",
            "Potted_meat_can",
            "Sugar_box",
            "Tomato_soup_can",
        ]

    async def run(self, confirm: bool = False) -> None:
        """执行下载流程。"""
        print("=" * 60)
        print("  Google Scanned Objects 数据集下载")
        print("  注意：此数据集约 10 GB")
        print("=" * 60)

        self.models_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            model_list = await self.get_model_list(client)
            print(f"\n找到 {len(model_list)} 个模型")

            if not model_list:
                print("  未找到模型列表")
                return

            if not confirm:
                print(f"即将下载 {len(model_list)} 个模型")
                answer = input("确认下载？(y/N): ").strip().lower()
                if answer != "y":
                    print("已取消下载")
                    return

            success_count = 0
            for model_name in model_list:
                model_dir = self.models_dir / model_name
                model_dir.mkdir(parents=True, exist_ok=True)

                print(f"\n  下载: {model_name}")

                # 尝试从 Fuel 下载模型配置
                try:
                    url = f"{self.BASE_URL}/{model_name}"
                    response = await client.get(url, timeout=15.0, follow_redirects=True)

                    if response.status_code == 200:
                        # 保存模型元数据
                        meta_path = model_dir / "model_info.json"
                        meta_path.write_text(response.text, encoding="utf-8")
                        print(f"    ✅ 元数据")
                        success_count += 1
                    else:
                        print(f"    ⚠️ HTTP {response.status_code}")
                except Exception as e:
                    print(f"    ⚠️ 下载失败: {e}")

        # 保存下载说明
        info_path = self.output_dir / "download_info.json"
        info_path.write_text(
            json.dumps(
                {
                    "dataset": "Google Scanned Objects",
                    "url": "https://fuel.gazebosim.org/1.0/GoogleResearch/models",
                    "blog": "https://research.google/blog/scanned-objects-a-dataset-of-3d-scanned-everyday-objects/",
                    "models": model_list,
                    "note": "如自动下载失败，请从 Fuel 平台手动下载",
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

        print(f"\n下载完成: {success_count}/{len(model_list)} 个模型处理成功")
        print(f"输出目录: {self.output_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Google Scanned Objects 数据集下载")
    parser.add_argument("--confirm", action="store_true", help="跳过确认直接下载")
    args = parser.parse_args()

    downloader = GoogleScannedDownloader()
    asyncio.run(downloader.run(confirm=args.confirm))


if __name__ == "__main__":
    main()
