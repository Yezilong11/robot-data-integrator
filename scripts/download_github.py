"""
GitHub 数据下载脚本

功能：
- 搜索抓取领域 Top 30 仓库
- 下载仓库 README
- 下载 Release 资产（模型权重）
- 存储仓库元数据

数据源：GitHub
官方地址：https://docs.github.com/en/rest
对接方式：GitHub REST API
数据格式：Markdown（README）、各代码格式、二进制（权重）
认证需求：Token（建议，认证5000次/小时，未认证60次/小时）

输出目录：data/sources/api/github/
预估大小：~500 MB（主要是模型权重）

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import base64
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config
from utils import ProgressTracker, download_file, get_data_dir


class GitHubDownloader:
    """GitHub 仓库数据下载器。"""

    API_BASE = "https://api.github.com"

    def __init__(self, token: str = "", max_repos: int = 30):
        self.token = token or config.GITHUB_TOKEN
        self.max_repos = max_repos
        self.output_dir = get_data_dir() / "api" / "github"
        self.repos_dir = self.output_dir / "repos"
        self.releases_dir = self.output_dir / "releases"
        self.headers = config.github_headers

    async def search_repos(
        self, client: httpx.AsyncClient, query: str, max_results: int = 30
    ) -> list[dict]:
        """搜索 GitHub 仓库，按 stars 排序。"""
        repos = []
        per_page = min(max_results, 30)
        page = 1

        while len(repos) < max_results:
            params = {
                "q": query,
                "sort": "stars",
                "order": "desc",
                "per_page": per_page,
                "page": page,
            }

            try:
                response = await client.get(
                    f"{self.API_BASE}/search/repositories",
                    params=params,
                    headers=self.headers,
                    timeout=30.0,
                )
                response.raise_for_status()
                data = response.json()

                items = data.get("items", [])
                if not items:
                    break

                for item in items:
                    repos.append({
                        "full_name": item["full_name"],
                        "name": item["name"],
                        "description": item.get("description", ""),
                        "stars": item["stargazers_count"],
                        "language": item.get("language", ""),
                        "url": item["html_url"],
                        "default_branch": item.get("default_branch", "main"),
                    })

                if len(items) < per_page:
                    break
                page += 1

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 403:
                    print("  [警告] GitHub API 速率限制，请配置 GITHUB_TOKEN")
                else:
                    print(f"  [错误] GitHub搜索失败: {e}")
                break
            except Exception as e:
                print(f"  [错误] GitHub搜索失败: {e}")
                break

        return repos[:max_results]

    async def download_readme(
        self, client: httpx.AsyncClient, repo_full_name: str, output_dir: Path
    ) -> bool:
        """下载仓库 README。"""
        # 尝试多个常见 README 文件名
        for readme_name in ["README.md", "README.rst", "README.txt", "README"]:
            try:
                url = f"{self.API_BASE}/repos/{repo_full_name}/contents/{readme_name}"
                response = await client.get(url, headers=self.headers, timeout=15.0)

                if response.status_code == 200:
                    data = response.json()
                    content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
                    readme_path = output_dir / "README.md"
                    readme_path.parent.mkdir(parents=True, exist_ok=True)
                    readme_path.write_text(content, encoding="utf-8")
                    return True

            except Exception:
                continue

        return False

    async def download_releases(
        self, client: httpx.AsyncClient, repo_full_name: str, output_dir: Path
    ) -> list[str]:
        """下载仓库 Release 信息（不自动下载大文件）。"""
        try:
            url = f"{self.API_BASE}/repos/{repo_full_name}/releases"
            response = await client.get(url, headers=self.headers, timeout=15.0)

            if response.status_code != 200:
                return []

            releases = response.json()
            if not releases:
                return []

            # 保存 Release 元数据
            release_info = []
            for release in releases[:3]:  # 只取最近3个 Release
                assets_info = []
                for asset in release.get("assets", []):
                    assets_info.append({
                        "name": asset["name"],
                        "size": asset["size"],
                        "download_url": asset["browser_download_url"],
                    })
                release_info.append({
                    "tag_name": release["tag_name"],
                    "name": release.get("name", ""),
                    "published_at": release.get("published_at", ""),
                    "assets": assets_info,
                })

            if release_info:
                meta_path = output_dir / "releases.json"
                meta_path.parent.mkdir(parents=True, exist_ok=True)
                meta_path.write_text(
                    json.dumps(release_info, ensure_ascii=False, indent=2), encoding="utf-8"
                )

            return [r["tag_name"] for r in release_info]

        except Exception as e:
            print(f"  [警告] Release获取失败 ({repo_full_name}): {e}")
            return []

    async def run(self, test_mode: bool = False) -> None:
        """执行完整下载流程。"""
        max_repos = 3 if test_mode else self.max_repos

        print("=" * 60)
        print(f"  GitHub 数据下载 {'[测试模式]' if test_mode else ''}")
        print(f"  目标: {max_repos} 个仓库")
        print("=" * 60)

        if not self.token:
            print("\n  [提示] 未配置 GITHUB_TOKEN，速率限制为60次/小时")
            print("  建议在 .env 中配置 GITHUB_TOKEN")

        self.repos_dir.mkdir(parents=True, exist_ok=True)
        self.releases_dir.mkdir(parents=True, exist_ok=True)

        async with httpx.AsyncClient() as client:
            print("\n搜索关键词: robot grasping")
            repos = await self.search_repos(client, "robot grasping", max_repos)
            print(f"  找到 {len(repos)} 个仓库\n")

            if not repos:
                print("  未找到仓库")
                return

            # 保存搜索结果汇总
            summary_path = self.repos_dir / "repos_summary.json"
            summary_path.write_text(
                json.dumps(repos, ensure_ascii=False, indent=2), encoding="utf-8"
            )

            tracker = ProgressTracker(len(repos), "下载仓库数据")
            success_count = 0

            for repo in repos:
                full_name = repo["full_name"]
                print(f"  处理: {full_name} (⭐{repo['stars']})")

                repo_dir = self.repos_dir / full_name.replace("/", "_")
                repo_dir.mkdir(parents=True, exist_ok=True)

                # 保存仓库元数据
                meta_path = repo_dir / "repo_meta.json"
                meta_path.write_text(
                    json.dumps(repo, ensure_ascii=False, indent=2), encoding="utf-8"
                )

                # 下载 README
                readme_ok = await self.download_readme(client, full_name, repo_dir)
                if readme_ok:
                    print(f"    ✅ README")
                else:
                    print(f"    ⚠️ 无 README")

                # 下载 Release 信息
                releases = await self.download_releases(client, full_name, repo_dir)
                if releases:
                    print(f"    ✅ Releases: {', '.join(releases)}")

                success_count += 1
                tracker.update()

        print(f"\n下载完成: {success_count}/{len(repos)} 个仓库处理成功")
        print(f"仓库目录: {self.repos_dir}")
        print(f"Release目录: {self.releases_dir}")


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="GitHub 数据下载")
    parser.add_argument("--test", action="store_true", help="测试模式，只下载3个仓库")
    args = parser.parse_args()

    downloader = GitHubDownloader(max_repos=config.GITHUB_REPO_COUNT)
    asyncio.run(downloader.run(test_mode=args.test))


if __name__ == "__main__":
    main()
