"""从 GitHub API 搜索并下载机器人抓取相关仓库信息。

用法：
    python scripts/download_github.py --max-repos 30
    python scripts/download_github.py --query "robot grasping" --max-repos 15
"""

from __future__ import annotations

import argparse
import asyncio
import base64
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
GITHUB_API = "https://api.github.com"
TIMEOUT = 30.0
MAX_RETRY = 3

REPOS_DIR = Path("data/sources/api/github/repos")
RELEASES_DIR = Path("data/sources/api/github/releases")

DEFAULT_QUERY = "robot grasping"


# ─── 跳过逻辑 ──────────────────────────────────────────────────────────


def should_skip(path: Path) -> bool:
    """已存在文件且大小>0则跳过。"""
    return path.exists() and path.stat().st_size > 0


# ─── API 封装 ──────────────────────────────────────────────────────────


def make_headers() -> dict[str, str]:
    """构建请求头，包含可选的 GITHUB_TOKEN。"""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.getenv("GITHUB_TOKEN", "")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    delay: float = 2.0,
) -> httpx.Response | None:
    """带重试和速率控制的 GET 请求。"""
    for attempt in range(1, MAX_RETRY + 1):
        await asyncio.sleep(delay)
        try:
            resp = await client.get(
                url,
                params=params,
                headers=headers,
            )
            # 检查速率限制
            remaining = resp.headers.get("X-RateLimit-Remaining")
            if resp.status_code == 403 and remaining == "0":
                reset_ts = int(resp.headers.get("X-RateLimit-Reset", "0"))
                wait = max(reset_ts - int(time.time()), 1)
                print(f"  ⏸ 速率限制触发，等待 {wait}s...")
                await asyncio.sleep(wait)
                continue
            if resp.status_code >= 500:
                print(f"  ⚠ 服务端错误 {resp.status_code}，重试 {attempt}/{MAX_RETRY}")
                continue
            return resp
        except httpx.HTTPError as e:
            print(f"  ⚠ 请求失败 ({attempt}/{MAX_RETRY}): {e}")
            if attempt == MAX_RETRY:
                return None
    return None


# ─── 下载逻辑 ──────────────────────────────────────────────────────────


async def search_repos(
    client: httpx.AsyncClient,
    query: str,
    max_repos: int,
    delay: float,
) -> list[dict[str, Any]]:
    """搜索 GitHub 仓库，按 stars 排序。"""
    url = f"{GITHUB_API}/search/repositories"
    headers = make_headers()

    per_page = min(max_repos, 100)
    resp = await safe_get(
        client,
        url,
        params={"q": query, "sort": "stars", "order": "desc", "per_page": per_page},
        headers=headers,
        delay=delay,
    )
    if resp is None or resp.status_code != 200:
        print(f"  ❌ 搜索失败: {resp.status_code if resp else 'no response'}")
        return []

    items = resp.json().get("items", [])
    repos = items[:max_repos]
    print(f"  🔍 找到 {len(items)} 个仓库，取前 {len(repos)} 个")
    return repos


async def download_readme(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    delay: float,
) -> bool:
    """下载仓库 README。"""
    name = f"{owner}_{repo}_readme.md"
    readme_path = REPOS_DIR / name

    if should_skip(readme_path):
        print(f"    ⏭ 跳过 README: {name}（已存在）")
        return True

    headers = make_headers()
    headers["Accept"] = "application/vnd.github.raw+json"

    resp = await safe_get(
        client,
        f"{GITHUB_API}/repos/{owner}/{repo}/readme",
        headers=headers,
        delay=delay,
    )
    if resp is None or resp.status_code != 200:
        # 尝试 README.md / README.rst 退化路径
        for branch in ["main", "master"]:
            for filename in ["README.md", "README.rst", "README"]:
                url = (
                    f"https://raw.githubusercontent.com/{owner}/{repo}/{branch}/{filename}"
                )
                resp2 = await safe_get(
                    client,
                    url,
                    headers={"Accept": "text/plain"},
                    delay=delay,
                )
                if resp2 is not None and resp2.status_code == 200:
                    text = resp2.text
                    break
            else:
                continue
            break
        else:
            print(f"    ❌ 未找到 README: {owner}/{repo}")
            return False
    else:
        text = resp.text

    readme_path.parent.mkdir(parents=True, exist_ok=True)
    readme_path.write_text(text, encoding="utf-8")
    print(f"    ✅ README 已保存: {name} ({len(text)} 字符)")
    return True


async def download_releases(
    client: httpx.AsyncClient,
    owner: str,
    repo: str,
    delay: float,
) -> bool:
    """下载仓库的 Release 资产列表 JSON。"""
    name = f"{owner}_{repo}_releases.json"
    releases_path = RELEASES_DIR / name

    if should_skip(releases_path):
        print(f"    ⏭ 跳过 Release 列表: {name}（已存在）")
        return True

    headers = make_headers()
    # GitHub 默认返回 30 条 release，分页取前 100
    all_releases: list[dict[str, Any]] = []
    page = 1

    while page <= 3:  # 最多 3 页 = 90 条
        resp = await safe_get(
            client,
            f"{GITHUB_API}/repos/{owner}/{repo}/releases",
            params={"per_page": 30, "page": page},
            headers=headers,
            delay=delay,
        )
        if resp is None or resp.status_code != 200:
            break
        data = resp.json() if resp.text else []
        if not data:
            break
        all_releases.extend(data)
        if len(data) < 30:
            break
        page += 1

    # 提取资产摘录
    summary = []
    for rel in all_releases:
        summary.append(
            {
                "tag_name": rel.get("tag_name"),
                "name": rel.get("name"),
                "id": rel.get("id"),
                "created_at": rel.get("created_at"),
                "html_url": rel.get("html_url"),
                "assets": [
                    {
                        "name": asset.get("name"),
                        "size": asset.get("size"),
                        "download_count": asset.get("download_count"),
                        "browser_download_url": asset.get("browser_download_url"),
                        "content_type": asset.get("content_type"),
                    }
                    for asset in rel.get("assets", [])
                ],
            }
        )

    releases_path.parent.mkdir(parents=True, exist_ok=True)
    releases_path.write_text(
        json.dumps(
            {
                "owner": owner,
                "repo": repo,
                "count": len(summary),
                "releases": summary,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"    ✅ Release 列表已保存: {name} ({len(summary)} 条)")
    return True


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="从 GitHub 下载 robot grasping 相关仓库信息"
    )
    parser.add_argument(
        "--max-repos",
        type=int,
        default=30,
        help="最大下载仓库数 (默认: 30)",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=DEFAULT_QUERY,
        help="搜索查询 (默认: 'robot grasping')",
    )
    args = parser.parse_args()

    token = os.getenv("GITHUB_TOKEN", "")
    delay = 0.5 if token else 2.0

    print("=" * 60)
    print("GitHub 仓库下载工具")
    print("=" * 60)
    print(f"查询: '{args.query}'")
    print(f"最大仓库数: {args.max_repos}")
    print(f"Token: {'已配置' if token else '未配置（间隔 2s）'}")
    print(f"仓库目录: {REPOS_DIR}")
    print(f"Release 目录: {RELEASES_DIR}")
    print()

    REPOS_DIR.mkdir(parents=True, exist_ok=True)
    RELEASES_DIR.mkdir(parents=True, exist_ok=True)

    start_time = time.monotonic()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        repos = await search_repos(client, args.query, args.max_repos, delay)
        if not repos:
            print("❌ 未找到仓库，退出")
            return

        print(f"\n📦 开始下载 {len(repos)} 个仓库信息...\n")

        readme_ok = 0
        release_ok = 0

        for i, repo_info in enumerate(repos, 1):
            owner = repo_info["owner"]["login"]
            name = repo_info["name"]
            stars = repo_info.get("stargazers_count", 0)
            print(f"[{i}/{len(repos)}] {owner}/{name} (⭐ {stars})")

            if await download_readme(client, owner, name, delay):
                readme_ok += 1
            if await download_releases(client, owner, name, delay):
                release_ok += 1

    elapsed = time.monotonic() - start_time
    print("\n" + "=" * 60)
    print(f"⏱ 总耗时: {elapsed:.1f}s")
    print(f"📊 README: {readme_ok}/{len(repos)} 成功")
    print(f"📊 Release 列表: {release_ok}/{len(repos)} 成功")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())