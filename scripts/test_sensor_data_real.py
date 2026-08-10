"""SensorDataSkill 真实生数据测试脚本。

目的
----
把一份**真实的** Franka 力/力矩(F/T)传感器时序数据喂给 ``SensorDataSkill``，
打印 ``process()`` + ``validate()`` 的完整结果，用于评估 Skill 对真实生数据的
处理能力（这是第二次联调未覆盖、组长在第三轮指派的测试任务）。

为什么是「Skill 单元层」而不是端到端
------------------------------------
端到端要走 ``retrieve_data → parse_convert → validate → assemble``，而
``SENSOR_DATA`` 的候选数据源是 GitHubAdapter / ZenodoAdapter（通用搜索源），
不保证能搜到可直接解析的 F/T 时序文件，可能在取数阶段就拿不到数据，那样就
测不到 Skill 本身了。本脚本直接调 Skill，聚焦「解析/校验逻辑能否消化真实数据」。

用法
----
    # 指定数据文件
    uv run python scripts/test_sensor_data_real.py --file data/sensor_real/franka_ft.csv
    # 不指定则自动找 data/sensor_real/ 下首个 .csv / .json
    uv run python scripts/test_sensor_data_real.py

数据格式要求（必须满足，否则 Skill 会降级或丢列）
------------------------------------------------
- CSV：首行表头；时间戳列名必须是 timestamp / time / t（大小写不敏感）；
  其余列必须为纯数值（不能含 NaN/空串/单位字符串，否则该列被静默丢弃）。
- JSON：list 形 ``[{"timestamp":0.0,"fx":1.2,...}, ...]``
  或 dict 形 ``{"signals":{"fx":[...]},"timestamps":[...]}``。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from rdi.skills.sensor_data import SensorDataset, SensorDataSkill

# 项目根目录（scripts/ 的上一级）
ROOT = Path(__file__).resolve().parent.parent
# 默认数据目录：data/ 已被 .gitignore 忽略，真实数据放这里不入库
DEFAULT_DIR = ROOT / "data" / "sensor_real"


def find_default_data() -> Path | None:
    """在 ``data/sensor_real/`` 下按 csv → json 顺序找首个数据文件。"""
    if not DEFAULT_DIR.is_dir():
        return None
    for pattern in ("*.csv", "*.json"):
        matches = sorted(DEFAULT_DIR.glob(pattern))
        if matches:
            return matches[0]
    return None


def fmt_from_suffix(path: Path) -> str:
    """由文件后缀推断 Skill 的 fmt 参数（csv / json）。"""
    return "csv" if path.suffix.lower() == ".csv" else "json"


def print_section(title: str) -> None:
    print(f"\n{'─' * 60}\n{title}\n{'─' * 60}")


def print_result(result, report, data_file: Path, fmt: str) -> None:
    """结构化打印 Skill 处理与校验结果。

    打印的字段都是判断「Skill 能否处理真实数据」的直接证据：
    - success/errors/warnings：处理是否成功、失败原因、降级提示
    - completeness_pct/confidence_score：完整度与置信度（降级会明显下降）
    - SensorDataset 细节：时间戳形状、信号列表、采样率、经历的转换
    - ValidationReport：是否通过校验、有哪些 WARNING/ERROR
    """
    print_section("① 输入")
    print(f"  文件: {data_file}")
    print(f"  格式(fmt): {fmt}")
    print(f"  大小: {data_file.stat().st_size} bytes")

    print_section("② process() 结果 (StandardResult)")
    print(f"  success          = {result.success}")
    print(f"  canonical_format = {result.canonical_format}   # 应为 'SensorDataset'")
    print(f"  completeness_pct = {result.completeness_pct}   # 100=完整, 70=缺时间戳降级")
    print(f"  confidence_score = {result.confidence_score}   # 1.0=正常, 0.7=降级")
    print(f"  output_path      = {result.output_path}")
    if result.errors:
        print(f"  errors ({len(result.errors)}):")
        for e in result.errors:
            print(f"    - {e}")
    if result.warnings:
        print(f"  warnings ({len(result.warnings)}):")
        for w in result.warnings:
            print(f"    - {w}")

    # data 是 SensorDataset 中间表示（处理失败时为 None）
    dataset = result.data
    if result.success and isinstance(dataset, SensorDataset):
        print_section("③ SensorDataset 中间表示")
        print(f"  source_format  = {dataset.source_format}")
        print(f"  transformations = {dataset.transformations}   # 含 infer_timestamps_from_index 表示时间戳是行号兜底")
        print(f"  timestamps.shape = {dataset.timestamps.shape}")
        if dataset.timestamps.size >= 2:
            print(f"  timestamps 范围 = [{dataset.timestamps[0]}, {dataset.timestamps[-1]}]")
        print(f"  sample_rate_hz = {dataset.sample_rate_hz:.4f}   # 由时间戳差分中位数推算")
        print(f"  signals ({len(dataset.signals)} 路):")
        for name, arr in dataset.signals.items():
            # 每路信号打印长度与统计量，便于核对真实数据特征是否被正确读入
            print(
                f"    - {name}: len={arr.size}, "
                f"min={float(arr.min()):.4f}, max={float(arr.max()):.4f}, "
                f"mean={float(arr.mean()):.4f}"
            )
        if not dataset.signals:
            print("    (空 — 所有数值列都被丢弃，通常是列里混了非数值)")
    else:
        print_section("③ SensorDataset 中间表示")
        print("  (处理失败或 data 为 None，无可打印的中间表示)")

    print_section("④ validate() 结果 (ValidationReport)")
    print(f"  is_valid = {report.is_valid}   # 无 ERROR 即 True；WARNING 不影响")
    print(f"  summary  = {report.summary}")
    if report.issues:
        print(f"  issues ({len(report.issues)}):")
        for vi in report.issues:
            print(f"    [{vi.severity}] {vi.message}")
            if vi.suggestion:
                print(f"        建议: {vi.suggestion}")
    else:
        print("  issues: (无)")

    print_section("⑤ 结论分类（对照计划 6.3 自动判读）")
    _print_verdict(result, report)


def _print_verdict(result, report) -> None:
    """根据结果字段自动归类，给出修复方向建议。"""
    if not result.success:
        print("  ❌ 处理失败 — Skill 无法解析该真实数据。")
        print("     修复方向: 检查 errors；若是格式问题需预处理数据，若是 Skill bug 需修 sensor_data.py。")
        return
    ds = result.data
    if result.confidence_score < 1.0:
        print("  ⚠️ 降级可用 — 时间戳列名不匹配 timestamp/time/t，用行号兜底。")
        print("     修复方向: 预处理数据把时间戳列改名为 timestamp；或放宽 Skill 的列名匹配。")
    if isinstance(ds, SensorDataset) and not ds.signals:
        print("  ⚠️ 信号全丢 — 所有数值列被静默丢弃（含 None/非数值字符串）。")
        print("     修复方向: 清洗脏值；或让 Skill 对丢列给出明确告警而非静默。")
    if isinstance(ds, SensorDataset) and ds.signals and result.confidence_score >= 1.0:
        print("  ✅ 完全成功 — Skill 能正确解析该真实数据（时间戳命中、信号保留、校验通过）。")
    # 时间戳非单调也会在 issues 里体现
    for vi in report.issues:
        if "非严格单调" in vi.message:
            print("  ⚠️ 时间戳非单调 — 真实采集抖动常见，Skill 给 WARNING（不影响 is_valid）。")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="用真实 Franka F/T 时序数据测试 SensorDataSkill。",
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=None,
        help="数据文件路径（csv/json）。不指定则自动找 data/sensor_real/ 下首个文件。",
    )
    args = parser.parse_args()

    # 1. 定位数据文件
    data_file = args.file if args.file else find_default_data()
    if data_file is None:
        print(f"[ERROR] 未指定 --file，且 {DEFAULT_DIR} 下无 csv/json 文件。")
        print("        请把真实 F/T 数据放到 data/sensor_real/ 下，或用 --file 指定路径。")
        return 2
    if not data_file.exists():
        print(f"[ERROR] 文件不存在: {data_file}")
        return 2

    # 2. 推断格式（Skill 只认 csv / json）
    fmt = fmt_from_suffix(data_file)
    if fmt not in ("csv", "json"):
        print(f"[ERROR] 不支持的格式: {data_file.suffix}（Skill 仅支持 csv/json，bag 会降级）。")
        print("        若原始数据是 .bag/.mat/.h5，请先预处理为 csv/json。")
        return 2

    # 3. 读字节 → process → validate
    data_bytes = data_file.read_bytes()
    skill = SensorDataSkill()

    print(f"[1/2] process()  file={data_file.name}  fmt={fmt}  size={len(data_bytes)}B")
    result = skill.process(data_bytes, fmt=fmt, name=data_file.stem)

    print("[2/2] validate()")
    report = skill.validate(result)

    # 4. 结构化打印
    print_result(result, report, data_file, fmt)

    # 退出码：处理失败返回 1（便于在 CI/脚本里判断），成功返回 0
    return 0 if result.success else 1


if __name__ == "__main__":
    sys.exit(main())
