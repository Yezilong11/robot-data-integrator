"""
公共工具模块

功能：
- 异步文件下载
- 项目路径管理
- 进度跟踪
- 重试机制

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import time
from pathlib import Path
from typing import Optional

import httpx


async def download_file(
    url: str,
    output_path: Path,
    client: httpx.AsyncClient,
    max_retries: int = 3,
    retry_delay: float = 2.0,
) -> bool:
    """异步下载文件，支持重试和断点续传检测。

    Args:
        url: 下载地址
        output_path: 本地保存路径
        client: httpx 异步客户端
        max_retries: 最大重试次数
        retry_delay: 重试间隔（秒）

    Returns:
        下载是否成功
    """
    # 断点续传：如果文件已存在且大小 > 0，跳过
    if output_path.exists() and output_path.stat().st_size > 0:
        print(f"  [跳过] 已存在: {output_path.name}")
        return True

    for attempt in range(1, max_retries + 1):
        try:
            response = await client.get(url, follow_redirects=True, timeout=60.0)
            response.raise_for_status()

            output_path.parent.mkdir(parents=True, exist_ok=True)
            with open(output_path, "wb") as f:
                for chunk in response.iter_bytes(chunk_size=8192):
                    f.write(chunk)
            return True

        except (httpx.HTTPStatusError, httpx.RequestError) as e:
            print(f"  [重试 {attempt}/{max_retries}] {url} -> {e}")
            if attempt < max_retries:
                await asyncio.sleep(retry_delay * attempt)
        except Exception as e:
            print(f"  [错误] {url} -> {e}")
            return False

    print(f"  [失败] 超过最大重试次数: {url}")
    return False


def get_project_root() -> Path:
    """获取项目根目录（robot-data-integrator/）。"""
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """获取数据目录（data/sources/）。"""
    return get_project_root() / "data" / "sources"


def get_scripts_dir() -> Path:
    """获取脚本目录（scripts/）。"""
    return get_project_root() / "scripts"


class ProgressTracker:
    """简单的进度跟踪器。"""

    def __init__(self, total: int, desc: str = "Progress"):
        self.total = total
        self.current = 0
        self.desc = desc
        self.start_time = time.time()

    def update(self, n: int = 1) -> None:
        self.current += n
        elapsed = time.time() - self.start_time
        percent = (self.current / self.total) * 100 if self.total > 0 else 0
        print(
            f"\r  {self.desc}: {self.current}/{self.total} "
            f"({percent:.1f}%) [{elapsed:.1f}s]",
            end="",
            flush=True,
        )
        if self.current >= self.total:
            print()  # 换行

    def done(self) -> None:
        if self.current < self.total:
            print()


def format_size(size_bytes: int) -> str:
    """格式化文件大小。"""
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(size_bytes) < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0  # type: ignore[assignment]
    return f"{size_bytes:.1f} PB"
