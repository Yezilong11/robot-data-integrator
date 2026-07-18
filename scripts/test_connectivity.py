"""
数据源连通性测试脚本

功能：
- 异步测试15个数据源的HTTP连通性
- 验证API响应格式（Atom XML / JSON / HTML）
- 测量响应时间
- 检测认证需求
- 生成Markdown测试报告

输出：data/connectivity_report.md

作者：挑战杯团队
创建日期：2026-07-14
"""

import asyncio
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

import httpx

# 添加脚本目录到 path
sys.path.insert(0, str(__file__).rsplit("\\", 1)[0])
from config import config


@dataclass
class TestResult:
    """单个数据源测试结果。"""

    source: str
    url: str
    status: str = "pending"  # success | failed | timeout | auth_required
    status_code: Optional[int] = None
    response_time: float = 0.0
    auth_required: bool = False
    error_message: str = ""
    data_valid: bool = False
    extra_info: str = ""


# ─── 15个数据源测试配置 ───

SOURCE_TESTS: list[dict] = [
    {
        "source": "arXiv",
        "url": "http://export.arxiv.org/api/query?search_query=robot+grasping&max_results=1",
        "expected_format": "xml",
        "auth": "无",
    },
    {
        "source": "IEEE Xplore",
        "url": "https://ieeexplore.ieee.org/rest/search",
        "expected_format": "json",
        "auth": "API Key",
        "method": "POST",
    },
    {
        "source": "GitHub",
        "url": "https://api.github.com/search/repositories?q=robot+grasping&per_page=1",
        "expected_format": "json",
        "auth": "Token（可选）",
    },
    {
        "source": "Papers with Code",
        "url": "https://paperswithcode.com/api/v1/search/?q=robot+grasping",
        "expected_format": "json",
        "auth": "无",
    },
    {
        "source": "HuggingFace",
        "url": "https://huggingface.co/api/models?search=robot+grasping&limit=1",
        "expected_format": "json",
        "auth": "无",
    },
    {
        "source": "GraspNet",
        "url": "https://graspnet.net/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "DexGraspNet",
        "url": "https://huggingface.co/datasets/dexgraspnet",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "YCB",
        "url": "https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "Google Scanned",
        "url": "https://research.google/blog/scanned-objects-a-dataset-of-3d-scanned-everyday-objects/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "Zenodo",
        "url": "https://zenodo.org/api/records?q=robot+grasping&size=1",
        "expected_format": "json",
        "auth": "无",
    },
    {
        "source": "Franka",
        "url": "https://franka.de/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "Robotiq",
        "url": "https://robotiq.com/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "Allegro",
        "url": "https://www.wonikrobotics.com/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "MuJoCo",
        "url": "https://mujoco.readthedocs.io/",
        "expected_format": "html",
        "auth": "无",
    },
    {
        "source": "Isaac Sim",
        "url": "https://docs.isaacsim.omniverse.nvidia.com/",
        "expected_format": "html",
        "auth": "无",
    },
]


def _validate_response(text: str, expected_format: str) -> bool:
    """验证响应内容格式是否符合预期。"""
    if not text:
        return False
    text_lower = text.strip().lower()
    if expected_format == "json":
        return text_lower.startswith("{") or text_lower.startswith("[")
    elif expected_format == "xml":
        return text_lower.startswith("<?xml") or text_lower.startswith("<feed")
    elif expected_format == "html":
        return "<html" in text_lower or "<!doctype" in text_lower
    return False


async def test_source(
    client: httpx.AsyncClient, test_cfg: dict
) -> TestResult:
    """测试单个数据源。"""
    result = TestResult(
        source=test_cfg["source"],
        url=test_cfg["url"],
    )
    start = time.time()

    try:
        method = test_cfg.get("method", "GET")
        headers: dict[str, str] = {}

        # GitHub 使用 Token
        if test_cfg["source"] == "GitHub" and config.GITHUB_TOKEN:
            headers["Authorization"] = f"token {config.GITHUB_TOKEN}"

        if method == "POST":
            response = await client.post(
                test_cfg["url"],
                headers=headers,
                timeout=config.ADAPTER_TIMEOUT,
            )
        else:
            response = await client.get(
                test_cfg["url"],
                headers=headers,
                timeout=config.ADAPTER_TIMEOUT,
                follow_redirects=True,
            )

        result.status_code = response.status_code
        result.response_time = round(time.time() - start, 2)

        if response.status_code == 200:
            result.status = "success"
            text = response.text
            result.data_valid = _validate_response(text, test_cfg["expected_format"])

            # 提取额外信息
            if test_cfg["source"] == "GitHub" and config.GITHUB_TOKEN:
                remaining = response.headers.get("X-RateLimit-Remaining", "N/A")
                result.extra_info = f"速率限制剩余: {remaining}/5000"
            elif test_cfg["source"] == "arXiv":
                import xml.etree.ElementTree as ET

                try:
                    root = ET.fromstring(text)
                    ns = {"atom": "http://www.w3.org/2005/Atom"}
                    entries = root.findall("atom:entry", ns)
                    result.extra_info = f"返回 {len(entries)} 条记录"
                except Exception:
                    pass

        elif response.status_code == 401 or response.status_code == 403:
            result.status = "auth_required"
            result.auth_required = True
            result.error_message = f"HTTP {response.status_code}: 需要认证"
        else:
            result.status = "failed"
            result.error_message = f"HTTP {response.status_code}"

    except httpx.TimeoutException:
        result.status = "timeout"
        result.response_time = round(time.time() - start, 2)
        result.error_message = f"请求超时（>{config.ADAPTER_TIMEOUT}s）"
    except httpx.ConnectError as e:
        result.status = "failed"
        result.response_time = round(time.time() - start, 2)
        result.error_message = f"连接失败: {e}"
    except Exception as e:
        result.status = "failed"
        result.response_time = round(time.time() - start, 2)
        result.error_message = f"未知错误: {e}"

    return result


def generate_report(results: list[TestResult]) -> str:
    """生成 Markdown 测试报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 数据源连通性测试报告\n",
        f"> 测试时间：{now}",
        f"> 测试环境：Windows 11, Python 3.11\n",
        "## 测试结果汇总\n",
        "| 数据源 | 状态 | 响应时间 | 认证需求 | 响应格式 | 备注 |",
        "|--------|------|---------|---------|---------|------|",
    ]

    status_icons = {
        "success": "✅ 成功",
        "failed": "❌ 失败",
        "timeout": "⏱️ 超时",
        "auth_required": "🔐 需认证",
    }

    for r in results:
        status_str = status_icons.get(r.status, r.status)
        format_str = "✅" if r.data_valid else "❌"
        note = r.error_message if r.error_message else r.extra_info
        lines.append(
            f"| {r.source} | {status_str} | {r.response_time}s "
            f"| {r.auth_required} | {format_str} | {note} |"
        )

    # 详细结果
    lines.append("\n## 详细结果\n")
    for r in results:
        lines.append(f"### {r.source}\n")
        lines.append(f"- URL: `{r.url}`")
        lines.append(f"- 状态码: {r.status_code or 'N/A'}")
        lines.append(f"- 响应时间: {r.response_time}s")
        lines.append(f"- 响应格式验证: {'✅ 通过' if r.data_valid else '❌ 未通过'}")
        if r.auth_required:
            lines.append(f"- 认证: 需要认证")
        if r.error_message:
            lines.append(f"- 错误信息: {r.error_message}")
        if r.extra_info:
            lines.append(f"- 额外信息: {r.extra_info}")
        lines.append("")

    # 统计
    success_count = sum(1 for r in results if r.status == "success")
    total_count = len(results)
    lines.append(f"## 统计\n")
    lines.append(f"- 总计: {total_count} 个数据源")
    lines.append(f"- 成功: {success_count} 个")
    lines.append(f"- 失败: {total_count - success_count} 个")

    return "\n".join(lines)


async def run_tests() -> list[TestResult]:
    """运行所有数据源连通性测试。"""
    print("=" * 60)
    print("  数据源连通性测试")
    print("=" * 60)

    results: list[TestResult] = []
    async with httpx.AsyncClient() as client:
        for test_cfg in SOURCE_TESTS:
            print(f"\n测试: {test_cfg['source']} ...", end=" ", flush=True)
            result = await test_source(client, test_cfg)
            results.append(result)

            status_icons = {"success": "✅", "failed": "❌", "timeout": "⏱️", "auth_required": "🔐"}
            icon = status_icons.get(result.status, "?")
            print(f"{icon} {result.status} ({result.response_time}s)")

    # 生成报告
    report = generate_report(results)
    report_path = config.REPORT_DIR / "connectivity_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"\n测试报告已生成: {report_path}")

    return results


def main() -> None:
    results = asyncio.run(run_tests())
    success = sum(1 for r in results if r.status == "success")
    print(f"\n测试完成: {success}/{len(results)} 个数据源连通成功")


if __name__ == "__main__":
    main()
