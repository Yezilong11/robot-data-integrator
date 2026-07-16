"""数据源连通性测试脚本。

测试 14 个数据源的 HTTP 连通性，验证响应格式，生成 Markdown 报告。

用法：
    python scripts/test_connectivity.py
"""

from __future__ import annotations

import asyncio
import os
import time
from dataclasses import dataclass, field
from datetime import datetime
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
TIMEOUT = 10.0
SLOW_TIMEOUT = 30.0  # 慢源（HuggingFace/Google Scanned 等）使用更长超时
REPORT_PATH = Path("data/connectivity_report.md")

# ─── 数据源测试配置 ────────────────────────────────────────────────────
SEARCH_QUERY = "robot grasping"


@dataclass
class TestResult:
    """单个数据源的测试结果。"""

    source: str
    url: str
    status: str = "pending"  # success | failed | timeout | auth_required
    status_code: int | None = None
    response_time: float = 0.0
    auth_required: bool = False
    error_message: str | None = None
    data_valid: bool = False
    notes: str = ""


class ConnectivityTester:
    """并发测试所有数据源连通性。"""

    def __init__(self) -> None:
        self.results: list[TestResult] = []
        self.github_token = os.getenv("GITHUB_TOKEN", "")
        self.ieee_api_key = os.getenv("IEEE_API_KEY", "")

    async def _get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
    ) -> tuple[int | None, str, float, httpx.Response | None]:
        """发送 GET 请求，返回 (status_code, error_msg, elapsed, response)。"""
        start = time.monotonic()
        try:
            resp = await client.get(
                url, params=params, headers=headers, timeout=timeout
            )
            elapsed = time.monotonic() - start
            return resp.status_code, "", elapsed, resp
        except httpx.TimeoutException:
            elapsed = time.monotonic() - start
            return None, "timeout", elapsed, None
        except httpx.ConnectError as e:
            elapsed = time.monotonic() - start
            return None, str(e), elapsed, None
        except Exception as e:
            elapsed = time.monotonic() - start
            return None, str(e), elapsed, None

    # ─── 论文源 ────────────────────────────────────────────────────────

    async def test_arxiv(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://export.arxiv.org/api/query"
        params = {"search_query": SEARCH_QUERY, "max_results": 1}
        code, err, elapsed, resp = await self._get(client, url, params=params)
        r = TestResult("arXiv", url, response_time=elapsed)
        if code == 200 and resp is not None:
            text = resp.text
            if "<entry>" in text:
                r.status = "success"
                r.status_code = code
                r.data_valid = True
            else:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应中未找到 <entry> 标签"
        else:
            r.status_code = code
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err or f"HTTP {code}"
        return r

    async def test_ieee(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://ieeexploreapi.ieee.org/api/v1/search/articles"
        if not self.ieee_api_key:
            return TestResult(
                "IEEE",
                url,
                status="auth_required",
                auth_required=True,
                notes="未配置 IEEE_API_KEY",
            )
        params = {"apikey": self.ieee_api_key, "max_records": 1, "querytext": "robot grasping"}
        code, err, elapsed, resp = await self._get(client, url, params=params, timeout=SLOW_TIMEOUT)
        r = TestResult("IEEE", url, response_time=elapsed, auth_required=True)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "total_records" in data or "articles" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
                else:
                    r.status = "failed"
                    r.status_code = code
                    r.error_message = f"响应缺少预期字段: {list(data.keys())[:5]}"
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        else:
            r.status_code = code
            r.status = "timeout" if err == "timeout" else "failed"
            body = resp.text[:200] if resp else ""
            r.error_message = err or f"HTTP {code}: {body}"
        return r

    # ─── 代码与模型源 ──────────────────────────────────────────────────

    async def test_github(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://api.github.com/search/repositories"
        params = {"q": SEARCH_QUERY, "per_page": 1}
        headers: dict[str, str] = {}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        code, err, elapsed, resp = await self._get(
            client, url, params=params, headers=headers
        )
        r = TestResult("GitHub", url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "total_count" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
                    remaining = resp.headers.get(
                        "X-RateLimit-Remaining", "?"
                    )
                    r.notes = f"速率限制剩余: {remaining}"
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        elif code == 403:
            r.status = "auth_required"
            r.status_code = code
            r.auth_required = True
            r.error_message = "速率限制（未认证 60次/小时）"
        else:
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err
        return r

    async def test_semantic_scholar(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://api.semanticscholar.org/graph/v1/paper/search"
        params = {"query": SEARCH_QUERY, "limit": 1, "fields": "title,externalIds"}
        code, err, elapsed, resp = await self._get(client, url, params=params, timeout=SLOW_TIMEOUT)
        r = TestResult("Semantic Scholar", url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "data" in data or "total" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
                    r.notes = "替代已停服的 Papers with Code API"
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        else:
            r.status_code = code
            if code == 429:
                r.status = "rate_limited"
                r.notes = "API 可用但触发限流（100次/5分钟）"
            else:
                r.status = "timeout" if err == "timeout" else "failed"
                r.error_message = err or f"HTTP {code}"
        return r

    async def test_huggingface(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://huggingface.co/api/models"
        params = {"search": SEARCH_QUERY, "limit": 1}
        code, err, elapsed, resp = await self._get(client, url, params=params, timeout=SLOW_TIMEOUT)
        r = TestResult("HuggingFace", url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if isinstance(data, list):
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        else:
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err
        return r

    # ─── 数据集源 ──────────────────────────────────────────────────────

    async def test_graspnet(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://graspnet.net/"
        return await self._test_html(client, "GraspNet", url)

    async def test_dexgraspnet(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://huggingface.co/api/datasets/lhrlhr/DexGraspNet2.0"
        code, err, elapsed, resp = await self._get(client, url, timeout=SLOW_TIMEOUT)
        r = TestResult("DexGraspNet", url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "id" in data or "tags" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        else:
            r.status_code = code
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err or f"HTTP {code}"
        return r

    async def test_ycb(self, client: httpx.AsyncClient) -> TestResult:
        url = "http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/"
        return await self._test_html(client, "YCB", url)

    async def test_google_scanned(
        self, client: httpx.AsyncClient
    ) -> TestResult:
        url = "http://storage.googleapis.com/gresearch/"
        return await self._test_html(client, "Google Scanned", url, timeout=SLOW_TIMEOUT)

    async def test_zenodo(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://zenodo.org/api/records"
        params = {"q": SEARCH_QUERY, "size": 1}
        code, err, elapsed, resp = await self._get(
            client, url, params=params
        )
        r = TestResult("Zenodo", url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "hits" in data or "total" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        else:
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err
        return r

    # ─── 硬件与仿真源 ──────────────────────────────────────────────────

    async def test_franka(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_html(client, "Franka", "https://franka.de/")

    async def test_robotiq(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_html(client, "Robotiq", "https://robotiq.com/")

    async def test_allegro(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://api.github.com/repos/simlabrobotics/allegro_hand_ros"
        return await self._test_github_repo(client, "Allegro", url)

    async def test_mujoco(self, client: httpx.AsyncClient) -> TestResult:
        url = "https://api.github.com/repos/deepmind/mujoco"
        return await self._test_github_repo(client, "MuJoCo", url)

    async def test_isaac(self, client: httpx.AsyncClient) -> TestResult:
        return await self._test_html(
            client,
            "Isaac Sim",
            "https://docs.isaacsim.omniverse.nvidia.com/",
        )

    # ─── 辅助方法 ──────────────────────────────────────────────────────

    async def _test_html(
        self,
        client: httpx.AsyncClient,
        source: str,
        url: str,
        timeout: float | None = None,
    ) -> TestResult:
        """测试返回 HTML 的数据源。"""
        code, err, elapsed, resp = await self._get(client, url, timeout=timeout)
        r = TestResult(source, url, response_time=elapsed)
        if code == 200 and resp is not None:
            ct = resp.headers.get("content-type", "")
            if "html" in ct or resp.text.strip().startswith("<"):
                r.status = "success"
                r.status_code = code
                r.data_valid = True
            else:
                r.status = "failed"
                r.status_code = code
                r.error_message = f"响应不是 HTML，content-type: {ct}"
        else:
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err
        return r

    async def _test_github_repo(
        self,
        client: httpx.AsyncClient,
        source: str,
        url: str,
    ) -> TestResult:
        """测试 GitHub 仓库 API（返回 JSON）。"""
        headers: dict[str, str] = {}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        code, err, elapsed, resp = await self._get(
            client, url, headers=headers
        )
        r = TestResult(source, url, response_time=elapsed)
        if code == 200 and resp is not None:
            try:
                data = resp.json()
                if "full_name" in data or "id" in data:
                    r.status = "success"
                    r.status_code = code
                    r.data_valid = True
            except Exception:
                r.status = "failed"
                r.status_code = code
                r.error_message = "响应不是有效 JSON"
        elif code == 403:
            r.status = "auth_required"
            r.status_code = code
            r.auth_required = True
            r.error_message = "GitHub API 速率限制"
        else:
            r.status = "timeout" if err == "timeout" else "failed"
            r.error_message = err
        return r

    # ─── 主流程 ────────────────────────────────────────────────────────

    async def test_all(self) -> None:
        """并发测试所有数据源。"""
        async with httpx.AsyncClient(timeout=TIMEOUT, follow_redirects=True, headers={"User-Agent": "RobotDataIntegrator/1.0"}) as client:
            tasks = [
                self.test_arxiv(client),
                self.test_ieee(client),
                self.test_github(client),
                self.test_semantic_scholar(client),
                self.test_huggingface(client),
                self.test_graspnet(client),
                self.test_dexgraspnet(client),
                self.test_ycb(client),
                self.test_google_scanned(client),
                self.test_zenodo(client),
                self.test_franka(client),
                self.test_robotiq(client),
                self.test_allegro(client),
                self.test_mujoco(client),
                self.test_isaac(client),
            ]
            self.results = await asyncio.gather(*tasks)

    def generate_report(self) -> str:
        """生成 Markdown 报告。"""
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines = [
            "# 数据源连通性测试报告",
            "",
            f"> 测试时间：{now}",
            f"> 测试环境：Python {__import__('sys').version.split()[0]}",
            "",
            "## 测试结果汇总",
            "",
            "| 数据源 | 状态 | 响应时间 | 认证需求 | 备注 |",
            "|--------|------|---------|---------|------|",
        ]

        status_emoji = {
            "success": "✅ 成功",
            "failed": "❌ 失败",
            "timeout": "⏰ 超时",
            "auth_required": "🔒 需凭证",
            "rate_limited": "⚠️ 限流",
        }

        for r in self.results:
            status = status_emoji.get(r.status, r.status)
            time_str = f"{r.response_time:.2f}s" if r.response_time > 0 else "-"
            auth = "是" if r.auth_required else "无"
            notes = r.notes or r.error_message or ""
            lines.append(
                f"| {r.source} | {status} | {time_str} | {auth} | {notes} |"
            )

        lines.extend(["", "## 详细结果", ""])

        for r in self.results:
            lines.extend(
                [
                    f"### {r.source}",
                    f"- URL: {r.url}",
                    f"- 状态码: {r.status_code or '-'}",
                    f"- 响应时间: {r.response_time:.2f}s"
                    if r.response_time > 0
                    else "- 响应时间: -",
                    f"- 认证: {'是' if r.auth_required else '无'}",
                    f"- 响应格式验证: {'✅' if r.data_valid else '❌'}",
                ]
            )
            if r.error_message:
                lines.append(f"- 错误: {r.error_message}")
            if r.notes:
                lines.append(f"- 备注: {r.notes}")
            lines.append("")

        return "\n".join(lines)


async def main() -> None:
    print("开始测试 15 个数据源连通性...\n")
    tester = ConnectivityTester()
    await tester.test_all()

    # 打印简要结果（用 ASCII 标记避免 Windows GBK 编码问题）
    for r in tester.results:
        mark = {
            "success": "[OK]",
            "failed": "[FAIL]",
            "timeout": "[TIMEOUT]",
            "auth_required": "[AUTH]",
            "rate_limited": "[RATE]",
        }.get(r.status, "[?]")
        time_str = f"{r.response_time:.2f}s" if r.response_time > 0 else "-"
        print(f"  {mark:12s} {r.source:20s}  {r.status:12s}  {time_str}")

    # 生成报告
    report = tester.generate_report()
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"\n报告已生成: {REPORT_PATH}")

    success_count = sum(1 for r in tester.results if r.status in ("success", "rate_limited"))
    print(f"总计: {success_count}/{len(tester.results)} 可用")


if __name__ == "__main__":
    asyncio.run(main())