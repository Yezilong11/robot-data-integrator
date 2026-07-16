"""从 HuggingFace API 搜索并下载机器人抓取相关模型的配置文件。

用法：
    python scripts/download_huggingface.py --limit 10
    python scripts/download_huggingface.py --search "robot grasping" --limit 20
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any

import httpx

# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ─── 常量 ──────────────────────────────────────────────────────────────
# 支持 HF_ENDPOINT 环境变量切换镜像站（如 https://hf-mirror.com）
_HF_BASE = os.getenv("HF_ENDPOINT", "https://huggingface.co").rstrip("/")
HF_API = f"{_HF_BASE}/api"
TIMEOUT = 30.0
MAX_RETRY = 5

MODELS_DIR = Path("data/sources/api/huggingface/models")

DEFAULT_SEARCH = "robot grasping"


# ─── 跳过逻辑 ──────────────────────────────────────────────────────────


def should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.exists() and path.stat().st_size > 0


def safe_dir_name(model_id: str) -> str:
    """模型 ID 中的 '/' 替换为 '_' 作为目录名。"""
    return model_id.replace("/", "_")


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    delay: float = 1.0,
) -> httpx.Response | None:
    """带重试的 GET 请求。"""
    for attempt in range(1, MAX_RETRY + 1):
        await asyncio.sleep(delay)
        try:
            resp = await client.get(url, params=params)
            if resp.status_code == 429:
                print(f"  [WAIT] 速率限制，等待 10s 后重试 ({attempt}/{MAX_RETRY})")
                await asyncio.sleep(10)
                continue
            if resp.status_code >= 500:
                print(f"  [WARN] 服务端错误 {resp.status_code}，重试 ({attempt}/{MAX_RETRY})")
                continue
            return resp
        except httpx.HTTPError as e:
            wait = 5 * attempt  # 5s, 10s, 15s, 20s, 25s 递增退避
            print(f"  [WARN] 请求失败 ({attempt}/{MAX_RETRY}): {e}")
            if attempt < MAX_RETRY:
                print(f"     等待 {wait}s 后重试...")
                await asyncio.sleep(wait)
            else:
                return None
    return None


# ─── 下载逻辑 ──────────────────────────────────────────────────────────


async def search_models(
    client: httpx.AsyncClient, search: str, limit: int, delay: float = 1.0
) -> list[dict[str, Any]]:
    """搜索 HuggingFace 模型。"""
    url = f"{HF_API}/models"
    resp = await safe_get(
        client,
        url,
        params={"search": search, "limit": limit, "full": "false"},
        delay=delay,
    )
    if resp is None or resp.status_code != 200:
        print(f"  [FAIL] 搜索失败: {resp.status_code if resp else 'no response'}")
        return []
    return resp.json() if resp.text else []


async def download_config_file(
    client: httpx.AsyncClient,
    model_id: str,
    filename: str,
    out_path: Path,
    delay: float = 1.0,
) -> bool:
    """下载单个 config.json 或 model_index.json。"""
    if should_skip(out_path):
        print(f"    [SKIP] 跳过 {filename}: {out_path.name}（已存在）")
        return True

    # 直接通过 raw resolve 接口拿文件内容
    url = f"{HF_API}/models/{model_id}/resolve/{filename}"
    resp = await safe_get(client, url, delay=delay)

    if resp is None or resp.status_code != 200:
        print(f"    [WARN] {filename} 不可用 (状态码: {resp.status_code if resp else 'N/A'})")
        return False

    # 优先保存为 JSON（如果内容是有效 JSON）
    try:
        data = resp.json()
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except json.JSONDecodeError:
        # 非 JSON 原样写入
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(resp.text, encoding="utf-8")

    size_kb = out_path.stat().st_size / 1024
    print(f"    [OK] 已保存 {filename} ({size_kb:.1f} KB)")
    return True


async def process_model(
    client: httpx.AsyncClient, model_info: dict[str, Any]
) -> int:
    """处理单个模型：下载 config.json 和 model_index.json。返回下载数量。"""
    model_id = model_info.get("id", "")
    if not model_id:
        return 0

    dir_name = safe_dir_name(model_id)
    model_dir = MODELS_DIR / dir_name
    model_dir.mkdir(parents=True, exist_ok=True)

    # 保存模型元信息
    meta_path = model_dir / "_model_meta.json"
    if not should_skip(meta_path):
        meta_path.write_text(
            json.dumps(
                {
                    "id": model_id,
                    "author": model_info.get("author"),
                    "tags": model_info.get("tags", []),
                    "downloads": model_info.get("downloads"),
                    "likes": model_info.get("likes"),
                    "lastModified": model_info.get("lastModified"),
                    "pipeline_tag": model_info.get("pipeline_tag"),
                    "library_name": model_info.get("library_name"),
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    count = 0
    # 下载数据集/模型的 config.json（位于主目录）
    config_path = model_dir / "config.json"
    if await download_config_file(client, model_id, "config.json", config_path):
        count += 1

    # 下载 model_index.json（diffusers 模型）
    index_path = model_dir / "model_index.json"
    if await download_config_file(client, model_id, "model_index.json", index_path):
        count += 1

    return count


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 HuggingFace 下载 robot grasping 相关模型配置"
    )
    parser.add_argument(
        "--search",
        type=str,
        default=DEFAULT_SEARCH,
        help="搜索关键词 (默认: 'robot grasping')",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="最大下载数量 (默认: 10)",
    )
    args = parser.parse_args()

    print("=" * 60)
    print("HuggingFace 模型配置下载工具")
    print("=" * 60)
    print(f"搜索关键词: '{args.search}'")
    print(f"最大数量: {args.limit}")
    print(f"输出目录: {MODELS_DIR}")
    print()

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "RobotDataIntegrator/1.0"}) as client:
        print(f"[SEARCH] 搜索关键词 '{args.search}'...")
        models = await search_models(client, args.search, args.limit)

        if not models:
            print("[FAIL] 未找到模型，退出")
            return

        # 限制数量
        models = models[: args.limit]
        print(f"  找到 {len(models)} 个模型\n")

        print(f"[PKG] 开始下载模型配置...\n")

        total_files = 0
        success_models = 0

        for i, model_info in enumerate(models, 1):
            mid = model_info.get("id", "unknown")
            downloads = model_info.get("downloads", 0)
            likes = model_info.get("likes", 0)
            print(f"[{i}/{len(models)}] {mid} (下载: {downloads}, like: {likes})")

            cnt = await process_model(client, model_info)
            total_files += cnt
            if cnt > 0:
                success_models += 1

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print(f"[TIME] 总耗时: {elapsed:.1f}s")
    print(f"[STAT] 配置文件下载: {total_files} 文件，{success_models}/{len(models)} 个模型成功")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())