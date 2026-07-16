"""GitHub 仓库内容遍历与下载辅助函数。

被 scripts/download_*.py 复用以避免重复实现。

用法：
    from _github_utils import download_repo_tree
"""

from __future__ import annotations

import asyncio
import os
import re
from pathlib import Path
from typing import Any

import httpx

# 加载 .env 文件中的环境变量
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

GITHUB_API = "https://api.github.com/repos/{owner}/{repo}/contents/{path}"
RAW_BASE = "https://raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}"
DOWNLOAD_TIMEOUT = 60.0  # 单个文件下载超时
MAX_RETRIES = 3  # 下载失败最大重试次数


def github_headers() -> dict[str, str]:
    """返回 GitHub API 请求头，若设置了 GITHUB_TOKEN 则附加认证。"""
    headers = {"Accept": "application/vnd.github+json"}
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.is_file() and path.stat().st_size > 0


async def list_contents(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    ref: str,
) -> list[dict[str, Any]]:
    """调用 GitHub API 列出仓库某目录内容。"""
    url = GITHUB_API.format(owner=owner, repo=repo, path=path)
    resp = await client.get(url, params={"ref": ref}, headers=github_headers())
    resp.raise_for_status()
    data = resp.json()
    if isinstance(data, dict):
        # 单文件返回单个对象
        return [data]
    return data


async def download_file(
    client: httpx.AsyncClient,
    url: str,
    dest: Path,
    *,
    label: str = "",
) -> bool:
    """下载单个文件到 dest，支持跳过、超时重试与进度打印。返回是否实际下载。"""
    if await _should_skip(dest):
        print(f"  [跳过] {label or dest.name} (已存在, {dest.stat().st_size} bytes)")
        return False

    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"  [下载中] {label or dest.name} <- {url}")

    last_err = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = await client.get(
                url, headers=github_headers(), timeout=DOWNLOAD_TIMEOUT
            )
            resp.raise_for_status()
            data = resp.content
            dest.write_bytes(data)
            print(f"  [完成]   {label or dest.name} ({len(data)} bytes)")
            return True
        except httpx.TransportError as e:
            last_err = e
            print(f"  [重试 {attempt}/{MAX_RETRIES}] {label or dest.name} 网络错误: {type(e).__name__}: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(2 * attempt)  # 递增退避
        except httpx.HTTPStatusError as e:
            # 404 等状态码错误不重试
            print(f"  [失败]   {label or dest.name} HTTP {e.response.status_code}")
            return False

    print(f"  [失败]   {label or dest.name} 重试 {MAX_RETRIES} 次后仍超时: {last_err}")
    return False


async def download_repo_tree(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    path: str,
    ref: str,
    output_dir: Path,
    *,
    label_prefix: str = "",
) -> tuple[int, int]:
    """递归下载仓库某目录下所有文件到 output_dir。

    返回 (已下载数, 跳过数)。
    """
    downloaded = 0
    skipped = 0
    try:
        items = await list_contents(client, owner, repo, path, ref)
    except httpx.HTTPStatusError as e:
        print(f"  [警告] 无法列出 {path}: HTTP {e.response.status_code}")
        print(f"         尝试直接下载 raw 文件")
        return 0, 0
    except Exception as e:  # noqa: BLE001
        print(f"  [警告] 无法列出 {path}: {e}")
        return 0, 0

    for item in items:
        name = item.get("name", "")
        item_type = item.get("type", "")
        item_path = item.get("path", "")
        label = f"{label_prefix}{name}" if label_prefix else name

        if item_type == "file":
            download_url = item.get("download_url") or RAW_BASE.format(
                owner=owner, repo=repo, ref=ref, path=item_path
            )
            dest = output_dir / name
            ok = await download_file(client, download_url, dest, label=label)
            if ok:
                downloaded += 1
            else:
                skipped += 1
        elif item_type == "dir":
            sub_downloaded, sub_skipped = await download_repo_tree(
                client,
                owner,
                repo,
                item_path,
                ref,
                output_dir / name,
                label_prefix=f"{label}/",
            )
            downloaded += sub_downloaded
            skipped += sub_skipped
    return downloaded, skipped


# ─── URDF mesh 引用解析（可选，用于精准递归下载引用的 mesh）──────────────

MESH_RE = re.compile(
    r'filename\s*=\s*"([^"]+\.(?:stl|STL|obj|OBJ|dae|DAE))"'
)


def parse_mesh_refs(urdf_path: Path) -> set[str]:
    """从 URDF/XACRO 文件中解析 mesh filename 引用（相对路径）。"""
    if not urdf_path.is_file():
        return set()
    try:
        text = urdf_path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return set()
    return {m for m in MESH_RE.findall(text)}


async def download_mesh_refs(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    ref: str,
    urdf_path: Path,
    urdf_repo_path: str,
    output_dir: Path,
) -> int:
    """下载 URDF 中引用的 mesh 文件（默认从包目录解析相对路径）。"""
    refs = parse_mesh_refs(urdf_path)
    downloaded = 0
    for ref_path in refs:
        # 规范化: 去掉 package:// 前缀和其他特殊前缀
        clean = ref_path
        for pfx in ("package://", "model://", "file://"):
            if clean.startswith(pfx):
                clean = clean[len(pfx):]
        # 取第一个非空 component 之后的部分（处理包名前缀）
        parts = [p for p in clean.split("/") if p]
        # 尝试多种 repo 内路径
        candidate_paths = [
            "/".join(parts),
            "/".join(parts[1:]) if len(parts) > 1 else "",
        ]
        ok = False
        for cand in candidate_paths:
            if not cand:
                continue
            raw_url = RAW_BASE.format(
                owner=owner, repo=repo, ref=ref, path=cand
            )
            # 保留目录结构
            dest = output_dir / Path(*parts)
            try:
                ok = await download_file(client, raw_url, dest, label=ref_path)
                if ok:
                    downloaded += 1
                    break
            except httpx.HTTPStatusError:
                continue
            except Exception:  # noqa: BLE001
                continue
        if not ok:
            print(f"  [跳过 mesh] {ref_path} (无法找到)")
    return downloaded