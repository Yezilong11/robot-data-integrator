"""Adapter 冒烟测试脚本。

验证各数据源 Adapter 的 search + fetch 端到端流程。

环境变量说明（国内用户可能需要，需在运行脚本前设置）：
  set HUGGINGFACE_API_URL=https://hf-mirror.com/api     (PowerShell)
  export HUGGINGFACE_API_URL=https://hf-mirror.com/api  (bash)

已知限制：
  - arxiv：本地 SSL 证书验证失败时需设置 SSL_CERT_FILE 环境变量
  - paperswithcode：原 API 已重定向至 huggingface.co（HTML），路径 B 暂不可用
"""

# ── 环境变量必须在 import rdi 之前设置（settings 是模块级单例） ──
import os
import socket

# 国内用户：如 huggingface.co 不可达，自动切换 hf-mirror.com 镜像
if not os.environ.get("HUGGINGFACE_API_URL"):
    try:
        socket.create_connection(("huggingface.co", 443), timeout=3)
    except OSError:
        os.environ["HUGGINGFACE_API_URL"] = "https://hf-mirror.com/api"
        print("[INFO] huggingface.co 不可达，自动切换 hf-mirror.com 镜像")

import asyncio

from rdi.adapters import get_adapter
from rdi.models.common import DataSource

SMOKE_CASES = [
    (DataSource.ARXIV, "robot grasping"),
    (DataSource.GITHUB, "franka robot"),
    (DataSource.SEMANTIC_SCHOLAR, "robot grasping"),
    (DataSource.ZENODO, "robot grasp dataset"),
    (DataSource.HUGGINGFACE, "robot dataset"),
]


async def smoke_one(source: DataSource, query: str) -> None:
    adapter = get_adapter(source)
    try:
        results = await adapter.search(query)
        if results:
            top = results[0]
            raw = await adapter.fetch(top.item_id)
            print(f"[OK] {source.value}: {len(results)} results, raw_type={type(raw).__name__}")
        else:
            print(f"[WARN] {source.value}: no results for query={query!r}")
    except Exception as exc:
        print(f"[FAIL] {source.value}: {exc}")


async def main() -> None:
    for source, query in SMOKE_CASES:
        await smoke_one(source, query)


if __name__ == "__main__":
    asyncio.run(main())
