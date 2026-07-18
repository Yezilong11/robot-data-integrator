"""
HuggingFace 数据下载脚本

功能：
- 搜索抓取领域相关模型（10个）
- 下载模型权重和配置文件
- 支持模型元数据提取

数据源：HuggingFace
官方地址：https://huggingface.co/
对接方式：HuggingFace API
数据格式：二进制权重（.pt/.pth/.safetensors）、JSON配置
认证需求：无

输出目录：data/sources/api/huggingface/
预估大小：~1 GB

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
from utils import ProgressTracker, download_file, get_data_dir


class HuggingFaceDownloader:
    """HuggingFace 模型下载器。"""

    API_BASE = "https://huggingface.co/api"

    def __init__(self, max_models: int = 10):
        self.max_models = max_models
        self.output_dir = get_data_dir() / "api" / "huggingface"
        self.models_dir = self.output_dir / "models"

    async def search_models(
        self, client: httpx.AsyncClient, query: str, limit: int = 10
    ) -> list[dict]:
        """搜索 HuggingFace 模型。"""
        params = {"search": query, "limit": limit, "sort": "downloads", "direction": "-1"}

        try:
            response = await client.get(
                f"{self.API_BASE}/models", params=params, timeout=30.0
            )
            response.raise_for_status()
            models = response.json()

            results = []
            for m in models:
                model_id = m.get("modelId", m.get("id", ""))
                results.append({
                    "model_id": model_id,
                    "author": model_id.split("/")[0] if "/" in model_id else "",
                    "pipeline_tag": m.get("pipeline_tag", ""),
                    "downloads": m.get("downloads", 0),
                    "tags": m.get("tags", []),
                    "last_modified": m.get("lastModified", ""),
                })

            return results

        except Exception as e:
            print(f"  [错误] HuggingFace搜索失败: {e}")
            return []

    async def download_model_files(
        self, client: httpx.AsyncClient, model_id: str, output_dir: Path
    ) -> bool:
        """下载模型的关键文件（config.json, tokenizer等），不下载大权重文件。"""
        try:
            # 获取模型文件列表
            url = f"{self.API_BASE}/models/{model_id}"
            response = await client.get(url, timeout=30.0)

            if response.status_code != 200:
                print(f"    [跳过] 无法获取模型信息: {model_id}")
                return False

            model_info = response.json()
            siblings = model_info.get("siblings", [])

            # 保存模型完整元数据
            meta_path = output_dir / "model_info.json"
            meta_path.parent.mkdir(parents=True, exist_ok=True)
            meta_path.write_text(
                json.dumps(model_info, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            # 下载关键小文件（config, tokenizer等），跳过大权重文件
            downloaded = 0
            for sibling in siblings:
                filename = sibling.get("rfilename", "")
                # 只下载配置文件和小文件（<100MB）
                if any(
                    filename.endswith(ext)
                    for ext in [".json", ".txt", ".cfg", ".py", "README.md"]
                ):
                    file_url = f"https://huggingface.co/{model_id}/resolve/main/{filename}"
                    file_path = output_dir / filename
                    ok = await download_file(file_url, file_path, client)
                    if ok:
                        downloaded += 1

            # 记录权重文件信息（不下载，仅记录URL）
            weight_files = []
            for sibling in siblings:
                filename = sibling.get("rfilename", "")
                if any(
                    filename.endswith(ext)
                    for ext in [".bin", ".pt", ".pth", ".safetensors", ".onnx", ".ckpt"]
                ):
                    weight_files.append({
                        "filename": filename,
                        "download_url": f"https://huggingface.co/{model_id}/resolve/main/{filename}",
                    })

            if weight_files:
                weights_path = output_dir / "weight_files.json"
                weights_path.write_text(
                    json.dumps(weight_files, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            print(f"    ✅ 配置文件: {downloaded}, 权重文件(仅链接): {len(weight_files)}")
            return True

        except Exception as e:
            print(f"    [错误] 模型下载失败 ({model_id}): {e}")
            return False

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        max_models = 3 if test_mode else self.max_models

        print("=" * 60)
        print(f"  HuggingFace 数据下载 {'[测试模式]' if test_mode else ''}")
        print(f"  目标: {max_models} 个模型")
        print("=" * 60)

        self.models_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n搜索关键词: robot grasping")
            models = await self.search_models(client, "robot grasping", max_models)
            print(f"  找到 {len(models)} 个模型\n")

            if not models:
                print("  尝试更宽泛的关键词...")
                models = await self.search_models(client, "grasping", max_models)
                print(f"  找到 {len(models)} 个模型\n")

            # 保存搜索结果
            summary_path = self.models_dir / "models_summary.json"
            summary_path.write_text(
                json.dumps(models, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            tracker = ProgressTracker(len(models), "下载模型")
            success_count = 0

            for model in models:
                model_id = model["model_id"]
                safe_name = model_id.replace("/", "_")
                model_dir = self.models_dir / safe_name

                print(f"  处理: {model_id} (下载量: {model['downloads']})")
                ok = await self.download_model_files(client, model_id, model_dir)
                if ok:
                    success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(models)} 个模型处理成功")
        print(f"模型目录: {self.models_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="HuggingFace 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式，只下载3个模型")
    args = parser.parse_args()

    downloader = HuggingFaceDownloader(max_models=config.HUGGINGFACE_MODEL_COUNT)
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
