"""数据完整性校验脚本。

遍历 data/sources/ 下所有目录，对每个数据源检查：
1. 文件数量是否符合预期（如果配置了预期数量）
2. 每个文件大小 > 0
3. 对 .md5 校验和文件做 MD5 验证

生成 data/verification_report.md 报告。
报告格式包含：数据源名、目录路径、文件数量、通过/失败/空文件数量。

用法：
    python scripts/verify_data.py
    python scripts/verify_data.py --source graspnet --output data/verification_report.md
"""

from __future__ import annotations

import argparse
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

# ─── 常量 ──────────────────────────────────────────────────────────────
SOURCES_ROOT = Path("data/sources")
DEFAULT_REPORT = Path("data/verification_report.md")

# 每个数据源预期的文件数量配置（0 或缺失表示不校验数量）
EXPECTED_FILE_COUNTS: dict[str, int] = {
    "api/arxiv/metadata": 20,
    "api/arxiv/pdfs": 20,
    "api/github/repos": 30,
    "api/github/releases": 0,
    "api/huggingface/models": 0,
    "api/zenodo/records": 0,
    "api/ieee/metadata": 0,
    "api/ieee/pdfs": 0,
    "web/franka/panda": 1,
    "web/robotiq/grippers": 1,
    "web/allegro/hand": 1,
    "web/paperswithcode/papers": 0,
    "web/mujoco/examples": 1,
    "web/isaac/examples": 1,
    "datasets/graspnet/dataset": 0,
    "datasets/dexgraspnet/data": 0,
    "datasets/ycb/models": 20,
    "datasets/google_scanned/models": 0,
}


# ─── 数据结构 ──────────────────────────────────────────────────────────
@dataclass
class SourceResult:
    """单个数据源的校验结果。"""

    name: str
    path: Path
    file_count: int = 0
    passed: int = 0
    failed: int = 0
    empty_count: int = 0
    md5_total: int = 0
    md5_passed: int = 0
    md5_failed: int = 0
    expected_count: int | None = None
    errors: list[str] = field(default_factory=list)


# ─── 工具函数 ──────────────────────────────────────────────────────────
def compute_md5(path: Path, *, chunk_size: int = 1 << 20) -> str:
    """计算文件 MD5 哈希值。"""
    md5 = hashlib.md5()
    with path.open("rb") as f:
        while chunk := f.read(chunk_size):
            md5.update(chunk)
    return md5.hexdigest()


def parse_md5_file(md5_path: Path) -> dict[str, str]:
    """解析 MD5 校验和文件，返回 {filename: md5sum} 映射。"""
    mapping: dict[str, str] = {}
    for line in md5_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line and "  " not in line:
            name, _, value = line.partition(":")
            mapping[name.strip()] = value.strip().lower()
        else:
            parts = line.split()
            if len(parts) >= 2:
                value, name = parts[0], parts[-1]
                mapping[Path(name).name] = value.lower()
    return mapping


def is_md5_checksum_file(path: Path) -> bool:
    """判断是否为 MD5 校验和文件。"""
    name = path.name.lower()
    return name in ("md5sum.txt", "md5sums", "md5.txt", "checksums.md5") or name.endswith(".md5")


# ─── 校验逻辑 ──────────────────────────────────────────────────────────
def verify_source(source_root: Path, name: str) -> SourceResult:
    """校验单个数据源目录。"""
    path = source_root / name
    result = SourceResult(name=name, path=path, expected_count=EXPECTED_FILE_COUNTS.get(name))

    if not path.exists():
        result.errors.append("目录不存在")
        return result

    # 收集所有文件（递归）
    all_files: list[Path] = [p for p in path.rglob("*") if p.is_file()]
    # 分类为：MD5 校验和文件 vs 普通文件
    md5_files = [p for p in all_files if is_md5_checksum_file(p)]
    normal_files = [p for p in all_files if not is_md5_checksum_file(p)]

    result.file_count = len(normal_files)

    # 1. 检查文件数量是否符合预期
    if result.expected_count is not None and result.expected_count > 0:
        if len(normal_files) < result.expected_count:
            result.errors.append(
                f"文件数量不足: 实际 {len(normal_files)}，预期 {result.expected_count}"
            )

    # 2. 检查每个普通文件大小 > 0
    for f in normal_files:
        try:
            size = f.stat().st_size
        except OSError as e:
            result.errors.append(f"无法读取文件 {f.name}: {e}")
            result.failed += 1
            continue
        if size == 0:
            result.empty_count += 1
            result.failed += 1
        else:
            result.passed += 1

    # 3. MD5 校验和验证
    for md5_path in md5_files:
        mapping = parse_md5_file(md5_path)
        base_dir = md5_path.parent
        for filename, expected_md5 in mapping.items():
            result.md5_total += 1
            target = base_dir / filename
            if not target.exists():
                # 在整个数据源目录范围内查找
                candidates = list(path.rglob(filename))
                if candidates:
                    target = candidates[0]
                else:
                    result.errors.append(f"MD5 校验缺失文件: {filename}")
                    result.md5_failed += 1
                    continue
            try:
                actual = compute_md5(target)
            except OSError as e:
                result.errors.append(f"MD5 校验读取失败 {filename}: {e}")
                result.md5_failed += 1
                continue
            if actual == expected_md5:
                result.md5_passed += 1
            else:
                result.errors.append(
                    f"MD5 校验失败 {filename}: 期望 {expected_md5[:12]}... 实际 {actual[:12]}..."
                )
                result.md5_failed += 1

    # 综合判定
    if result.failed == 0 and result.md5_failed == 0 and not result.errors:
        result.passed = result.file_count
    else:
        # 有错误时 failed 已包含空文件数
        if result.passed == 0 and result.file_count > 0:
            result.passed = result.file_count - result.empty_count

    return result


def generate_report(results: list[SourceResult], output_path: Path) -> str:
    """生成 Markdown 报告。"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 数据完整性校验报告",
        "",
        f"> 生成时间：{now}",
        f"> 数据根目录：{SOURCES_ROOT}",
        "",
        "## 校验结果汇总",
        "",
        "| 数据源 | 目录路径 | 文件数量 | 通过 | 失败 | 空文件 | MD5校验通过 | MD5校验失败 | 预期数量 | 状态 |",
        "|--------|----------|----------|------|------|--------|-------------|-------------|----------|------|",
    ]

    total_pass = 0
    total_fail = 0
    for r in results:
        status = "通过" if (r.failed == 0 and r.md5_failed == 0 and not r.errors) else "失败"
        expected = str(r.expected_count) if r.expected_count is not None else "-"
        lines.append(
            f"| {r.name} | {r.path} | {r.file_count} | {r.passed} | {r.failed} | "
            f"{r.empty_count} | {r.md5_passed} | {r.md5_failed} | {expected} | {status} |"
        )
        if status == "通过":
            total_pass += 1
        else:
            total_fail += 1

    lines.extend(["", "## 详细结果", ""])

    for r in results:
        lines.extend(
            [
                f"### {r.name}",
                f"- 目录路径: `{r.path}`",
                f"- 文件数量: {r.file_count}",
                f"- 通过: {r.passed}",
                f"- 失败: {r.failed}",
                f"- 空文件数: {r.empty_count}",
                f"- MD5 校验: 总计 {r.md5_total}，通过 {r.md5_passed}，失败 {r.md5_failed}",
                f"- 预期文件数量: {r.expected_count if r.expected_count is not None else '未配置'}",
            ]
        )
        if r.errors:
            lines.append("- 错误列表:")
            for err in r.errors[:50]:  # 限制错误条目数量
                lines.append(f"  - {err}")
            if len(r.errors) > 50:
                lines.append(f"  - ... 以及其他 {len(r.errors) - 50} 条错误")
        lines.append("")

    lines.extend(
        [
            "## 统计",
            "",
            f"- 数据源总数: {len(results)}",
            f"- 通过: {total_pass}",
            f"- 失败: {total_fail}",
            "",
        ]
    )

    return "\n".join(lines)


# ─── 主流程 ────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="数据完整性校验脚本")
    parser.add_argument(
        "--source",
        type=str,
        default="",
        help="仅检查指定数据源（相对路径，如 graspnet 或 api/arxiv/metadata）",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"报告输出路径（默认: {DEFAULT_REPORT}）",
    )
    args = parser.parse_args()

    print("=" * 70)
    print("数据完整性校验")
    print("=" * 70)
    print(f"  数据根目录: {SOURCES_ROOT}")
    print(f"  报告输出: {args.output}")
    if args.source:
        print(f"  仅检查: {args.source}")
    print()

    if not SOURCES_ROOT.exists():
        print(f"  [错误] 数据根目录不存在: {SOURCES_ROOT}")
        return

    # 确定要检查的数据源列表
    if args.source:
        # 支持多种输入：graspnet / datasets/graspnet / datasets/graspnet/dataset
        candidates = [args.source]
        # 尝试补全为已知 key
        if args.source in EXPECTED_FILE_COUNTS:
            sources_to_check = [args.source]
        else:
            # 模糊匹配：在 EXPECTED_FILE_COUNTS 中查找包含输入的 key
            matched = [k for k in EXPECTED_FILE_COUNTS if args.source in k]
            if matched:
                sources_to_check = matched
            else:
                # 作为目录名直接检查
                sources_to_check = candidates
    else:
        sources_to_check = list(EXPECTED_FILE_COUNTS.keys())

    # 同时检测 data/sources 下实际存在的目录，补全未在配置中的数据源
    if not args.source and SOURCES_ROOT.exists():
        actual_dirs: list[str] = []
        for p in SOURCES_ROOT.rglob("*"):
            if p.is_dir():
                rel = p.relative_to(SOURCES_ROOT).as_posix()
                if rel and rel != ".":
                    actual_dirs.append(rel)
        for d in actual_dirs:
            if d not in sources_to_check and not any(d.startswith(k + "/") for k in sources_to_check):
                sources_to_check.append(d)

    results: list[SourceResult] = []
    for name in sources_to_check:
        print(f">>> 校验数据源 [{name}]")
        r = verify_source(SOURCES_ROOT, name)
        results.append(r)
        status_emoji = "✅" if (r.failed == 0 and r.md5_failed == 0 and not r.errors) else "❌"
        print(
            f"  {status_emoji} 文件 {r.file_count} | 通过 {r.passed} | 失败 {r.failed} | "
            f"空 {r.empty_count} | MD5通过 {r.md5_passed}/{r.md5_total}"
        )
        if r.errors:
            for err in r.errors[:5]:
                print(f"     - {err}")

    # 生成报告
    print()
    print("正在生成校验报告...")
    report = generate_report(results, args.output)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(f"  [完成] 报告已生成: {args.output}")

    total_pass = sum(1 for r in results if r.failed == 0 and r.md5_failed == 0 and not r.errors)
    total_fail = len(results) - total_pass
    print()
    print("=" * 70)
    print(f"校验完成: 通过 {total_pass}，失败 {total_fail}，共 {len(results)} 个数据源")
    print("=" * 70)


if __name__ == "__main__":
    main()