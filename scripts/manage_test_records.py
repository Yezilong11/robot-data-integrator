#!/usr/bin/env python3
"""问题集与手动执行记录的质量管理工具。"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
PROBLEM_SET_PATH = ROOT / "problem_set" / "problem_set.json"
RECORDS_DIR = ROOT / "records"
TEMPLATE_PATH = RECORDS_DIR / "_templates" / "record.template.json"
MANAGEMENT_DIR = RECORDS_DIR / "_management"
ASSIGNMENTS_PATH = MANAGEMENT_DIR / "assignments.csv"
PROGRESS_PATH = MANAGEMENT_DIR / "progress.csv"
QUALITY_REPORT_PATH = MANAGEMENT_DIR / "quality_report.json"
SUMMARY_PATH = MANAGEMENT_DIR / "statistics_summary.md"

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from rdi.models.common import DataReqType, DataSource  # noqa: E402

ALLOWED_LAYERS = {"single_source", "multi_source"}
ALLOWED_CATEGORIES = {
    "paper",
    "code",
    "dataset",
    "robot_urdf",
    "mesh",
    "grasp",
    "sim_config",
    "policy",
    "sensor",
    "end_to_end",
}
ALLOWED_LANGUAGES = {"ZH", "EN", "MIX"}
ALLOWED_QUALITIES = {"real", "fallback", "unknown", "synthetic"}
ALLOWED_PRIORITIES = {"P0", "P1", "P2"}
ALLOWED_EXECUTORS = {"A", "C", "D", "E", "F"}
ALLOWED_VERDICTS = {"PASS", "PASS_WITH_FALLBACK", "FAIL"}
ALLOWED_FAILURE_CATEGORIES = {
    "P1_PARSE",
    "P2_RETRIEVE",
    "P3_SOURCE",
    "P4_FORMAT",
    "P5_RUNTIME",
    "P6_FRONTEND",
    "P7_ENV",
    "P8_OTHER",
}
ALLOWED_RETRIEVE_STATUSES = {"success", "missing", "error"}
ALLOWED_PACKAGE_STATUSES = {"complete", "partial", "missing", "error"}
ALLOWED_VS_EXPECTED = {"match", "partial", "mismatch"}
ALLOWED_RUNTIME_CHECKS = {"passed", "failed", "not_applicable", "not_run"}
VALID_DATA_SOURCES = {item.value for item in DataSource}
VALID_REQ_TYPES = {item.value for item in DataReqType}


# P0 验收线：至少 ceil(P0 总数 × 2/3)。已确认口径（11 题 → 8，8 题 → 6），
# 不硬编码具体数量，问题集调整 P0 数量时验收线自动跟随。
def p0_target(p0_total: int) -> int:
    """P0 可用数据包验收线 = ceil(p0_total × 2/3)。"""
    return -(-p0_total * 2 // 3)


@dataclass(frozen=True)
class Issue:
    severity: str
    location: str
    message: str


def read_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} 的顶层必须是 JSON object")
    return data


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def is_placeholder(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip()
        return not text or text.startswith("<") or "请填写" in text
    return False


def get_nested(data: dict[str, Any], path: str) -> Any:
    value: Any = data
    for key in path.split("."):
        if not isinstance(value, dict) or key not in value:
            return None
        value = value[key]
    return value


def parse_iso(value: Any) -> bool:
    if not isinstance(value, str) or not value.strip():
        return False
    try:
        datetime.fromisoformat(value)
    except ValueError:
        return False
    return True


def load_problem_set() -> dict[str, Any]:
    return read_json(PROBLEM_SET_PATH)


def problem_map(problem_set: dict[str, Any]) -> dict[str, dict[str, Any]]:
    problems = problem_set.get("problems", [])
    if not isinstance(problems, list):
        return {}
    return {
        item["case_id"]: item
        for item in problems
        if isinstance(item, dict) and isinstance(item.get("case_id"), str)
    }


def validate_problem_set(problem_set: dict[str, Any]) -> list[Issue]:
    issues: list[Issue] = []
    if problem_set.get("schema_version") != "1.0":
        issues.append(Issue("ERROR", "schema_version", "必须为 1.0"))

    meta = problem_set.get("meta")
    if not isinstance(meta, dict):
        issues.append(Issue("ERROR", "meta", "必须是 object"))
    else:
        architecture = meta.get("architecture")
        if not isinstance(architecture, dict):
            issues.append(Issue("ERROR", "meta.architecture", "必须是 object"))
        else:
            declared = []
            for layer_name in ("single_source", "multi_source"):
                config = architecture.get(layer_name)
                ratio = config.get("ratio") if isinstance(config, dict) else None
                if not isinstance(ratio, int | float) or not 0 <= ratio <= 1:
                    issues.append(
                        Issue("ERROR", f"meta.architecture.{layer_name}.ratio", "必须为 0 到 1")
                    )
                else:
                    declared.append(float(ratio))
            if len(declared) == 2 and abs(sum(declared) - 1.0) > 0.001:
                issues.append(Issue("ERROR", "meta.architecture", "两个比例之和必须为 1"))

    problems = problem_set.get("problems")
    if not isinstance(problems, list) or not problems:
        return issues + [Issue("ERROR", "problems", "必须是非空数组")]

    seen: set[str] = set()
    sources_covered: set[str] = set()
    layer_counts: Counter[str] = Counter()
    p0_count = 0

    for index, problem in enumerate(problems):
        location = f"problems[{index}]"
        if not isinstance(problem, dict):
            issues.append(Issue("ERROR", location, "题目必须是 object"))
            continue

        required_keys = {
            "case_id",
            "layer",
            "category",
            "source",
            "target",
            "lang",
            "expected",
            "priority",
        }
        missing_keys = sorted(required_keys - set(problem))
        if missing_keys:
            issues.append(Issue("ERROR", location, f"缺少字段: {', '.join(missing_keys)}"))

        case_id = problem.get("case_id")
        layer = problem.get("layer")
        if not isinstance(case_id, str) or not case_id.strip():
            issues.append(Issue("ERROR", f"{location}.case_id", "必须是非空字符串"))
        elif case_id in seen:
            issues.append(Issue("ERROR", f"{location}.case_id", f"重复 case_id: {case_id}"))
        else:
            seen.add(case_id)
            prefix = "ss_" if layer == "single_source" else "ms_"
            if layer in ALLOWED_LAYERS and not case_id.startswith(prefix):
                issues.append(Issue("ERROR", f"{location}.case_id", f"应以 {prefix} 开头"))

        if layer not in ALLOWED_LAYERS:
            issues.append(Issue("ERROR", f"{location}.layer", "层级取值非法"))
        else:
            layer_counts[layer] += 1

        if problem.get("category") not in ALLOWED_CATEGORIES:
            issues.append(Issue("ERROR", f"{location}.category", "类别取值非法"))
        if problem.get("lang") not in ALLOWED_LANGUAGES:
            issues.append(Issue("ERROR", f"{location}.lang", "语言必须为 ZH/EN/MIX"))
        if problem.get("priority") not in ALLOWED_PRIORITIES:
            issues.append(Issue("ERROR", f"{location}.priority", "优先级必须为 P0/P1/P2"))
        elif problem.get("priority") == "P0":
            p0_count += 1
        if is_placeholder(problem.get("target")):
            issues.append(Issue("ERROR", f"{location}.target", "题目原文不能为空"))

        sources = problem.get("source")
        if not isinstance(sources, list) or not sources:
            issues.append(Issue("ERROR", f"{location}.source", "必须是非空数组"))
        else:
            invalid_sources = [item for item in sources if item not in VALID_DATA_SOURCES]
            if invalid_sources:
                issues.append(
                    Issue(
                        "ERROR",
                        f"{location}.source",
                        f"未知 DataSource: {', '.join(map(str, invalid_sources))}",
                    )
                )
            sources_covered.update(item for item in sources if item in VALID_DATA_SOURCES)
            if layer == "single_source" and len(sources) != 1:
                issues.append(Issue("ERROR", f"{location}.source", "单源题必须恰好一个源"))
            if layer == "multi_source" and len(sources) < 2:
                issues.append(Issue("ERROR", f"{location}.source", "多源题至少两个源"))

        expected = problem.get("expected")
        if not isinstance(expected, dict):
            issues.append(Issue("ERROR", f"{location}.expected", "必须是 object"))
            continue
        if set(expected) != {"req_types", "quality", "format", "min_files"}:
            issues.append(
                Issue(
                    "ERROR",
                    f"{location}.expected",
                    "字段必须固定为 req_types/quality/format/min_files",
                )
            )
        req_types = expected.get("req_types")
        if not isinstance(req_types, list) or not req_types:
            issues.append(Issue("ERROR", f"{location}.expected.req_types", "必须非空"))
        else:
            invalid_req_types = [item for item in req_types if item not in VALID_REQ_TYPES]
            if invalid_req_types:
                issues.append(
                    Issue(
                        "ERROR",
                        f"{location}.expected.req_types",
                        f"未知 DataReqType: {', '.join(map(str, invalid_req_types))}",
                    )
                )
        quality = expected.get("quality")
        if not isinstance(quality, list) or not quality:
            issues.append(Issue("ERROR", f"{location}.expected.quality", "必须非空"))
        elif any(item not in ALLOWED_QUALITIES for item in quality):
            issues.append(Issue("ERROR", f"{location}.expected.quality", "包含非法质量值"))
        formats = expected.get("format")
        if not isinstance(formats, list) or not formats or any(is_placeholder(x) for x in formats):
            issues.append(Issue("ERROR", f"{location}.expected.format", "必须为非空格式列表"))
        min_files = expected.get("min_files")
        if not isinstance(min_files, int) or isinstance(min_files, bool) or min_files < 1:
            issues.append(Issue("ERROR", f"{location}.expected.min_files", "必须为正整数"))

    total = len(problems)
    actual_single_ratio = layer_counts["single_source"] / total
    if actual_single_ratio < 0.7:
        issues.append(
            Issue(
                "ERROR",
                "problems",
                f"单源占比 {actual_single_ratio:.1%}，低于策略下限 70%（单源主导）",
            )
        )
    if p0_count < 1:
        issues.append(Issue("ERROR", "problems", "P0 至少 1 道，当前 0 道"))
    # LOCAL 是本地挂载注入源，不属于需覆盖的外部数据源，从覆盖校验中排除
    missing_sources = sorted((VALID_DATA_SOURCES - sources_covered) - {"local"})
    if missing_sources:
        # 已注册但问题集未配题的源（如新增适配器 KinovaAdapter 后问题集暂未跟进）
        # 属"能力超前于题目"，降为 WARNING 不阻塞校验；问题集扩题后自动消除
        issues.append(
            Issue(
                "WARNING",
                "problems",
                f"未覆盖 DataSource: {', '.join(missing_sources)}（已注册源暂无对应题目）",
            )
        )

    return issues


def load_assignments() -> dict[str, dict[str, str]]:
    if not ASSIGNMENTS_PATH.exists():
        return {}
    with ASSIGNMENTS_PATH.open(encoding="utf-8-sig", newline="") as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle) if row.get("case_id")}


def validate_assignments(
    assignments: dict[str, dict[str, str]], problems: dict[str, dict[str, Any]]
) -> list[Issue]:
    issues: list[Issue] = []
    missing = sorted(set(problems) - set(assignments))
    extra = sorted(set(assignments) - set(problems))
    if missing:
        issues.append(Issue("ERROR", "assignments.csv", f"缺少 case: {', '.join(missing)}"))
    if extra:
        issues.append(Issue("ERROR", "assignments.csv", f"存在未知 case: {', '.join(extra)}"))
    for case_id, row in assignments.items():
        if row.get("suggested_executor") not in ALLOWED_EXECUTORS:
            issues.append(Issue("ERROR", case_id, "建议执行人必须为 A/C/D/E/F"))
        if row.get("reviewer") not in ALLOWED_EXECUTORS:
            issues.append(Issue("ERROR", case_id, "复核人必须为 A/C/D/E/F"))
    return issues


def git_value(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def read_env_value(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    env_path = ROOT / ".env"
    if not env_path.exists():
        return default
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, candidate = line.split("=", 1)
        if key.strip() == name:
            return candidate.strip().strip('"').strip("'")
    return default


def init_record(case_id: str, executor: str | None) -> Path:
    problems = problem_map(load_problem_set())
    if case_id not in problems:
        raise ValueError(f"未知 case_id: {case_id}")
    assignments = load_assignments()
    selected_executor = executor or assignments.get(case_id, {}).get("suggested_executor", "")
    if selected_executor not in ALLOWED_EXECUTORS:
        raise ValueError("执行人必须为 A/C/D/E/F")

    case_dir = RECORDS_DIR / case_id
    record_path = case_dir / "record.json"
    if record_path.exists():
        raise FileExistsError(f"记录已存在，不覆盖: {record_path}")

    record = read_json(TEMPLATE_PATH)
    record["case_id"] = case_id
    record["input"] = problems[case_id]["target"]
    record["executor"] = selected_executor
    record["env"]["llm_model"] = read_env_value("LLM_MODEL", "qwen-plus")
    record["env"]["llm_base_url"] = read_env_value(
        "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
    )
    record["env"]["git_branch"] = git_value("rev-parse", "--abbrev-ref", "HEAD")
    record["env"]["git_commit"] = git_value("rev-parse", "HEAD")

    (case_dir / "screenshots").mkdir(parents=True, exist_ok=True)
    write_json(record_path, record)
    return record_path


def collect_secret_keys(value: Any, location: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, item in value.items():
            child = f"{location}.{key}" if location else key
            key_lower = key.lower()
            if "api_key" in key_lower or key_lower.endswith("token"):
                found.append(child)
            found.extend(collect_secret_keys(item, child))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found.extend(collect_secret_keys(item, f"{location}[{index}]"))
    return found


def record_completeness(record: dict[str, Any]) -> float:
    required_paths = [
        "schema_version",
        "case_id",
        "input",
        "executor",
        "executed_at",
        "env.llm_model",
        "env.llm_base_url",
        "env.mode",
        "env.git_branch",
        "env.git_commit",
        "env.review_decision",
        "observations.parse_goal.req_list",
        "observations.parse_goal.vs_expected",
        "observations.retrieve",
        "observations.validate.errors",
        "observations.validate.warnings",
        "observations.validate.runtime_check",
        "observations.package.dir",
        "observations.package.manifest_path",
        "observations.package.status",
        "observations.package.file_count",
        "observations.package.missing_items_count",
        "observations.package.fallback_explicit",
        "screenshots",
        "verdict",
    ]
    if record.get("verdict") == "FAIL":
        required_paths.extend(["failure_category", "failure_reason"])

    present = 0
    for path in required_paths:
        value = get_nested(record, path)
        if path in {
            "observations.validate.errors",
            "observations.validate.warnings",
            "observations.package.file_count",
            "observations.package.missing_items_count",
            "observations.package.fallback_explicit",
        }:
            if value is not None:
                present += 1
        elif isinstance(value, list):
            if value:
                present += 1
        elif not is_placeholder(value):
            present += 1
    return round(present / len(required_paths) * 100, 1)


def _case_relative_path(case_dir: Path, value: Any) -> Path | None:
    if not isinstance(value, str) or not value.strip():
        return None
    path = Path(value)
    if not path.is_absolute():
        path = case_dir / path
    try:
        resolved = path.resolve()
        resolved.relative_to(case_dir.resolve())
    except (OSError, ValueError):
        return None
    return resolved


def validate_record(record: dict[str, Any], problem: dict[str, Any], case_dir: Path) -> list[Issue]:
    case_id = problem["case_id"]
    issues: list[Issue] = []

    if record.get("schema_version") != "1.0":
        issues.append(Issue("ERROR", case_id, "record schema_version 必须为 1.0"))
    if record.get("case_id") != case_id or case_dir.name != case_id:
        issues.append(Issue("ERROR", case_id, "目录名、record.case_id 与问题集不一致"))
    secret_keys = collect_secret_keys(record)
    if secret_keys:
        issues.append(Issue("ERROR", case_id, f"记录中不得保存密钥字段: {', '.join(secret_keys)}"))

    executed_at = record.get("executed_at")
    if executed_at is None:
        issues.append(Issue("WARNING", case_id, "记录已初始化但尚未执行"))
        return issues
    if not parse_iso(executed_at):
        issues.append(Issue("ERROR", case_id, "executed_at 必须为 ISO 8601 时间"))

    if is_placeholder(record.get("input")):
        issues.append(Issue("ERROR", case_id, "input 必须填写实际输入原文"))
    if record.get("executor") not in ALLOWED_EXECUTORS:
        issues.append(Issue("ERROR", case_id, "executor 必须为 A/C/D/E/F"))

    env = record.get("env")
    if not isinstance(env, dict):
        issues.append(Issue("ERROR", case_id, "env 必须是 object"))
        env = {}
    for key in ("llm_model", "llm_base_url", "git_branch", "git_commit"):
        if is_placeholder(env.get(key)):
            issues.append(Issue("ERROR", case_id, f"env.{key} 必填"))
    if env.get("mode") != "real":
        issues.append(Issue("ERROR", case_id, "正式问题集必须使用 real 模式"))
    if env.get("review_decision") not in {"satisfied", "revise"}:
        issues.append(Issue("ERROR", case_id, "review_decision 必须为 satisfied/revise"))
    if "sk-" in str(env.get("llm_base_url", "")).lower():
        issues.append(Issue("ERROR", case_id, "llm_base_url 疑似包含 API Key"))

    observations = record.get("observations")
    if not isinstance(observations, dict):
        issues.append(Issue("ERROR", case_id, "observations 必须是 object"))
        observations = {}

    expected = problem["expected"]
    expected_req_types = set(expected["req_types"])
    expected_sources = set(problem["source"])
    expected_qualities = set(expected["quality"])
    expected_formats = set(expected["format"])

    parse_goal = observations.get("parse_goal")
    if not isinstance(parse_goal, dict):
        issues.append(Issue("ERROR", case_id, "observations.parse_goal 必须是 object"))
        parse_goal = {}
    req_list = parse_goal.get("req_list")
    if not isinstance(req_list, list):
        issues.append(Issue("ERROR", case_id, "parse_goal.req_list 必须是数组"))
        req_list = []
    elif any(item not in VALID_REQ_TYPES for item in req_list):
        issues.append(Issue("ERROR", case_id, "parse_goal.req_list 含未知需求类型"))
    vs_expected = parse_goal.get("vs_expected")
    if vs_expected not in ALLOWED_VS_EXPECTED:
        issues.append(Issue("ERROR", case_id, "parse_goal.vs_expected 取值非法"))
    elif vs_expected == "match" and set(req_list) != expected_req_types:
        issues.append(Issue("ERROR", case_id, "标为 match，但 req_list 与 expected 不一致"))

    retrieve = observations.get("retrieve")
    if not isinstance(retrieve, list):
        issues.append(Issue("ERROR", case_id, "observations.retrieve 必须是数组"))
        retrieve = []

    fallback_seen = False
    for index, item in enumerate(retrieve):
        location = f"{case_id}.retrieve[{index}]"
        if not isinstance(item, dict):
            issues.append(Issue("ERROR", location, "必须是 object"))
            continue
        req_type = item.get("req_type")
        source = item.get("source")
        quality = item.get("quality")
        status = item.get("status")
        item_format = item.get("format")
        is_fallback = item.get("is_fallback")
        if is_placeholder(item.get("req_id")):
            issues.append(Issue("ERROR", location, "req_id 必填"))
        if req_type not in VALID_REQ_TYPES:
            issues.append(Issue("ERROR", location, "req_type 非法"))
        elif req_type not in expected_req_types:
            # 题设外补充需求（多需求场景）：成功获取且可加载验证通过属
            # 合理补充，记 WARNING 而非 ERROR（口径纪要 §7）；未满足仍 ERROR。
            if status == "success":
                issues.append(Issue("WARNING", location, f"出现题设外补充需求: {req_type}"))
            else:
                issues.append(Issue("ERROR", location, f"出现非预期 req_type: {req_type}"))
        if source not in VALID_DATA_SOURCES:
            issues.append(Issue("ERROR", location, "source 非法"))
        if quality not in ALLOWED_QUALITIES:
            issues.append(Issue("ERROR", location, "quality 非法"))
        elif status == "success" and quality not in expected_qualities:
            # 口径纪要 §2.4：题设 quality 不得高于探活实测可达水平。
            # 数据源探活只能产出 fallback（如 GraspNet 单 grasp、IEEE 无
            # Key 等），执行时显式降级（is_fallback=true）并记录
            # fallback_reason，属可接受的 quality 冲突，放行为 WARNING。
            if is_fallback is True and not is_placeholder(item.get("fallback_reason")):
                issues.append(
                    Issue(
                        "WARNING",
                        location,
                        f"quality {quality} 不在允许范围，但已显式降级并记录 fallback_reason（纪要 §2.4 放行）",
                    )
                )
            else:
                issues.append(Issue("ERROR", location, f"quality {quality} 不在允许范围"))
        if status not in ALLOWED_RETRIEVE_STATUSES:
            issues.append(Issue("ERROR", location, "status 必须为 success/missing/error"))
        if not isinstance(is_fallback, bool):
            issues.append(Issue("ERROR", location, "is_fallback 必须为 boolean"))
        if (
            status == "success"
            and req_type in expected_req_types
            and item_format not in expected_formats
        ):
            # 口径纪要 §2.4：显式降级（is_fallback=true + fallback_reason）
            # 时产出格式可偏离题设（如 mesh 降级为元数据 JSON、grasp 降级
            # 为 CanonicalGrasp 结构化表示），放行为 WARNING。
            if is_fallback is True and not is_placeholder(item.get("fallback_reason")):
                issues.append(
                    Issue(
                        "WARNING",
                        location,
                        f"format {item_format} 不在预期格式中，但已显式降级（纪要 §2.4 放行）",
                    )
                )
            else:
                issues.append(Issue("ERROR", location, f"format {item_format} 不在预期格式中"))
        if status != "success" and is_placeholder(item.get("error")):
            issues.append(Issue("ERROR", location, "检索未成功时必须填写 error"))

        # 多需求补充源口径（纪要 §7）：仅题设核心需求（req_type ∈ expected）
        # 要求命中题设源；题设外补充需求由其他源真实获取不算静默降级。
        source_mismatch = (
            status == "success"
            and req_type in expected_req_types
            and source not in expected_sources
        )
        item_fallback = is_fallback is True or quality == "fallback" or source_mismatch
        fallback_seen = fallback_seen or item_fallback
        if source_mismatch and is_fallback is not True and quality != "fallback":
            issues.append(Issue("ERROR", location, "命中非目标源但未标记，属于静默降级"))
        if item_fallback and is_placeholder(item.get("fallback_reason")):
            issues.append(Issue("ERROR", location, "降级必须填写 fallback_reason"))

    validate = observations.get("validate")
    if not isinstance(validate, dict):
        issues.append(Issue("ERROR", case_id, "observations.validate 必须是 object"))
        validate = {}
    errors = validate.get("errors")
    warnings = validate.get("warnings")
    runtime_check = validate.get("runtime_check")
    if not isinstance(errors, int) or isinstance(errors, bool) or errors < 0:
        issues.append(Issue("ERROR", case_id, "validate.errors 必须为非负整数"))
    if not isinstance(warnings, int) or isinstance(warnings, bool) or warnings < 0:
        issues.append(Issue("ERROR", case_id, "validate.warnings 必须为非负整数"))
    if runtime_check not in ALLOWED_RUNTIME_CHECKS:
        issues.append(Issue("ERROR", case_id, "validate.runtime_check 取值非法"))

    package = observations.get("package")
    if not isinstance(package, dict):
        issues.append(Issue("ERROR", case_id, "observations.package 必须是 object"))
        package = {}
    package_status = package.get("status")
    file_count = package.get("file_count")
    missing_count = package.get("missing_items_count")
    fallback_explicit = package.get("fallback_explicit")
    if package_status not in ALLOWED_PACKAGE_STATUSES:
        issues.append(Issue("ERROR", case_id, "package.status 取值非法"))
    if not isinstance(file_count, int) or isinstance(file_count, bool) or file_count < 0:
        issues.append(Issue("ERROR", case_id, "package.file_count 必须为非负整数"))
        file_count = 0
    if not isinstance(missing_count, int) or isinstance(missing_count, bool) or missing_count < 0:
        issues.append(Issue("ERROR", case_id, "package.missing_items_count 必须为非负整数"))
    if not isinstance(fallback_explicit, bool):
        issues.append(Issue("ERROR", case_id, "package.fallback_explicit 必须为 boolean"))
    fallback_seen = fallback_seen or fallback_explicit is True

    screenshots = record.get("screenshots")
    if not isinstance(screenshots, list):
        issues.append(Issue("ERROR", case_id, "screenshots 必须是数组"))
        screenshots = []
    # ponytail: P7_ENV 类在初始化阶段失败、未生成数据包的 case 物理上不存在
    # package/validation 截图，放宽为至少 2 张（FAIL 必须含报错截图，由下方
    # has_error_screenshot 检查保证）；升级路径：此类 case 补足截图后收紧。
    early_fail = record.get("verdict") == "FAIL" and package.get("status") in (
        "missing",
        "not_generated",
    )
    if len(screenshots) < (2 if early_fail else 4):
        issues.append(
            Issue("ERROR", case_id, "每题至少 4 张截图（input/progress/package/validation）")
        )
    has_error_screenshot = False
    for index, screenshot in enumerate(screenshots):
        location = f"{case_id}.screenshots[{index}]"
        if not isinstance(screenshot, dict):
            issues.append(Issue("ERROR", location, "必须是 object"))
            continue
        file_value = screenshot.get("file")
        desc = screenshot.get("desc")
        path = _case_relative_path(case_dir, file_value)
        if path is None:
            issues.append(Issue("ERROR", location, "截图路径无效或越出 case 目录"))
        elif not path.exists():
            issues.append(Issue("ERROR", location, f"截图文件不存在: {file_value}"))
        if is_placeholder(desc):
            issues.append(Issue("ERROR", location, "截图说明必填"))
        searchable = f"{file_value} {desc}".lower()
        if "error" in searchable or "报错" in searchable or "错误" in searchable:
            has_error_screenshot = True

    verdict = record.get("verdict")
    if verdict not in ALLOWED_VERDICTS:
        issues.append(Issue("ERROR", case_id, "verdict 必须为 PASS/PASS_WITH_FALLBACK/FAIL"))
    else:
        is_usable = verdict in {"PASS", "PASS_WITH_FALLBACK"}
        if is_usable:
            # 显式降级（fallback_explicit=true）：validate.errors 与 min_files 缺口
            # 来自降级需求（如 graspnet 仅元数据 JSON），属 PASS_WITH_FALLBACK
            # 合法形态，放行这些检查（口径纪要 §6 已确认）。
            degraded_ok = fallback_explicit is True
            # 多需求补充源口径（纪要 §7）：match=解析与题设完全一致；
            # partial=核心需求（题设 req_types）全命中，允许 LLM 合理补充。
            core_hit = expected_req_types.issubset(set(req_list))
            if vs_expected not in {"match", "partial"} or not core_hit:
                issues.append(
                    Issue("ERROR", case_id, "可用判定要求目标解析完全匹配或核心需求全命中")
                )
            if errors != 0 and not degraded_ok:
                issues.append(Issue("ERROR", case_id, "可用判定要求 validate.errors=0"))
            if package_status not in {"complete", "partial"} and not degraded_ok:
                issues.append(Issue("ERROR", case_id, "可用判定要求存在可用数据包"))
            if (
                isinstance(file_count, int)
                and file_count < expected["min_files"]
                and not degraded_ok
            ):
                issues.append(
                    Issue(
                        "ERROR",
                        case_id,
                        f"文件数 {file_count} 低于 min_files={expected['min_files']}",
                    )
                )
            # 可加载性验证：validate 节点目前是骨架实现（已知风险），真实
            # URDF/Mesh/MJCF 加载验证无法自动完成，允许 not_applicable 并留人工
            # 复核；failed/not_run 仍视为未完成验证。
            if expected_formats.intersection(
                {"urdf", "stl", "obj", "ply", "xml"}
            ) and runtime_check not in {"passed", "not_applicable"}:
                issues.append(Issue("ERROR", case_id, "URDF/Mesh/MJCF 必须完成可加载性验证"))
            for field_name in ("dir", "manifest_path"):
                path_value = package.get(field_name)
                if is_placeholder(path_value):
                    if not degraded_ok:
                        issues.append(Issue("ERROR", case_id, f"package.{field_name} 必填"))
                elif not degraded_ok:
                    path = Path(str(path_value))
                    if not path.is_absolute():
                        path = ROOT / path
                    if not path.exists():
                        # 数据包被 .gitignore 排除、在各执行机本地化，验收端
                        # 无法验证路径存在性；记 WARNING 供人工复核而非 ERROR。
                        issues.append(
                            Issue(
                                "WARNING",
                                case_id,
                                f"package.{field_name} 指向的路径在当前环境不存在（数据包在各执行机本地，需人工复核）",
                            )
                        )
        if verdict == "PASS":
            if fallback_seen:
                issues.append(Issue("ERROR", case_id, "存在降级时不能判 PASS"))
            if package_status != "complete" or missing_count != 0:
                issues.append(Issue("ERROR", case_id, "PASS 要求完整包且 missing_items_count=0"))
        elif verdict == "PASS_WITH_FALLBACK":
            if not fallback_seen:
                issues.append(Issue("ERROR", case_id, "PASS_WITH_FALLBACK 必须有降级证据"))
            if fallback_explicit is not True:
                issues.append(Issue("ERROR", case_id, "降级必须在 package 中显式记录"))
        elif verdict == "FAIL":
            if record.get("failure_category") not in ALLOWED_FAILURE_CATEGORIES:
                issues.append(Issue("ERROR", case_id, "FAIL 必须填写 P1_PARSE 到 P8_OTHER"))
            if is_placeholder(record.get("failure_reason")):
                issues.append(Issue("ERROR", case_id, "FAIL 必须填写 failure_reason"))
            if not has_error_screenshot:
                issues.append(Issue("ERROR", case_id, "FAIL 必须包含报错截图"))

    if verdict != "FAIL" and (
        record.get("failure_category") is not None or record.get("failure_reason") is not None
    ):
        issues.append(Issue("ERROR", case_id, "非 FAIL 记录不得填写失败分类或原因"))

    reviewer = record.get("reviewer")
    reviewed_at = record.get("reviewed_at")
    if (reviewer is None) != (reviewed_at is None):
        issues.append(Issue("ERROR", case_id, "reviewer 与 reviewed_at 必须同时填写"))
    if reviewer is not None and reviewer not in ALLOWED_EXECUTORS:
        issues.append(Issue("ERROR", case_id, "reviewer 必须为 A/C/D/E/F"))
    if reviewed_at is not None and not parse_iso(reviewed_at):
        issues.append(Issue("ERROR", case_id, "reviewed_at 必须为 ISO 8601 时间"))

    completeness = record_completeness(record)
    if completeness < 90:
        issues.append(Issue("ERROR", case_id, f"字段完整率 {completeness:.1f}% 低于 90%"))
    return issues


def load_records(
    problems: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, list[Issue]]]:
    records: dict[str, dict[str, Any]] = {}
    issues_by_case: dict[str, list[Issue]] = {}

    for path in sorted(RECORDS_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("_"):
            continue
        case_id = path.name
        record_path = path / "record.json"
        if case_id not in problems:
            issues_by_case[case_id] = [Issue("ERROR", case_id, "records 中存在未知 case")]
            continue
        if not record_path.exists():
            issues_by_case[case_id] = [Issue("ERROR", case_id, "case 目录缺少 record.json")]
            continue
        try:
            record = read_json(record_path)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            issues_by_case[case_id] = [Issue("ERROR", case_id, f"record.json 无法读取: {exc}")]
            continue
        records[case_id] = record
        issues_by_case[case_id] = validate_record(record, problems[case_id], path)

    return records, issues_by_case


def record_status(record: dict[str, Any] | None) -> str:
    if not record or record.get("executed_at") is None:
        return "未执行"
    if record.get("verdict") not in ALLOWED_VERDICTS:
        return "已执行"
    if record.get("reviewer") is not None and record.get("reviewed_at") is not None:
        return "已复核"
    return "已判定"


def build_progress_rows(
    problems: dict[str, dict[str, Any]],
    assignments: dict[str, dict[str, str]],
    records: dict[str, dict[str, Any]],
    issues_by_case: dict[str, list[Issue]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for problem in problems.values():
        case_id = problem["case_id"]
        record = records.get(case_id)
        screenshots = record.get("screenshots", []) if record else []
        case_issues = issues_by_case.get(case_id, [])
        rows.append(
            {
                "case_id": case_id,
                "layer": problem["layer"],
                "category": problem["category"],
                "priority": problem["priority"],
                "lang": problem["lang"],
                "sources": ";".join(problem["source"]),
                "req_types": ";".join(problem["expected"]["req_types"]),
                "target": problem["target"],
                "suggested_executor": assignments.get(case_id, {}).get("suggested_executor", ""),
                "executor": record.get("executor", "") if record else "",
                "status": record_status(record),
                "verdict": record.get("verdict", "") if record else "",
                "failure_category": record.get("failure_category", "") if record else "",
                "llm_model": get_nested(record, "env.llm_model") if record else "",
                "executed_at": record.get("executed_at", "") if record else "",
                "reviewer": record.get("reviewer", "") if record else "",
                "reviewed_at": record.get("reviewed_at", "") if record else "",
                "screenshot_count": len(screenshots) if isinstance(screenshots, list) else 0,
                "completeness_pct": record_completeness(record) if record else 0.0,
                "issue_count": sum(item.severity == "ERROR" for item in case_issues),
                "updated_at": now_iso(),
            }
        )
    return rows


def write_progress(rows: list[dict[str, Any]]) -> None:
    MANAGEMENT_DIR.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0]) if rows else []
    with PROGRESS_PATH.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def dimension_summary(
    problems: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    field: str,
) -> dict[str, dict[str, Any]]:
    buckets: dict[str, list[str]] = {}
    for case_id, problem in problems.items():
        raw_value = problem[field] if field in problem else problem["expected"][field]
        values = raw_value if isinstance(raw_value, list) else [raw_value]
        for value in values:
            buckets.setdefault(str(value), []).append(case_id)

    result: dict[str, dict[str, Any]] = {}
    for value, case_ids in sorted(buckets.items()):
        verdicts = [records[case_id].get("verdict") for case_id in case_ids if case_id in records]
        judged = [item for item in verdicts if item in ALLOWED_VERDICTS]
        usable = sum(item in {"PASS", "PASS_WITH_FALLBACK"} for item in judged)
        result[value] = {
            "cases": len(case_ids),
            "judged": len(judged),
            "pass": judged.count("PASS"),
            "fallback": judged.count("PASS_WITH_FALLBACK"),
            "fail": judged.count("FAIL"),
            "usable_rate": round(usable / len(judged), 4) if judged else None,
        }
    return result


def build_quality_report(
    problems: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    issues_by_case: dict[str, list[Issue]],
    problem_issues: list[Issue],
    assignment_issues: list[Issue],
    strict: bool,
) -> dict[str, Any]:
    total = len(problems)
    executed = {case_id: record for case_id, record in records.items() if record.get("executed_at")}
    judged = {
        case_id: record
        for case_id, record in executed.items()
        if record.get("verdict") in ALLOWED_VERDICTS
    }
    reviewed = {
        case_id: record
        for case_id, record in judged.items()
        if record.get("reviewer") is not None and record.get("reviewed_at") is not None
    }
    verdicts = Counter(record["verdict"] for record in judged.values())
    usable = verdicts["PASS"] + verdicts["PASS_WITH_FALLBACK"]
    completeness_values = [record_completeness(record) for record in executed.values()]
    complete_records = sum(value >= 90 for value in completeness_values)

    p0_ids = [case_id for case_id, item in problems.items() if item["priority"] == "P0"]
    p0_usable = sum(
        records.get(case_id, {}).get("verdict") in {"PASS", "PASS_WITH_FALLBACK"}
        for case_id in p0_ids
    )
    failure_counter = Counter(
        record.get("failure_category")
        for record in judged.values()
        if record.get("verdict") == "FAIL" and record.get("failure_category")
    )
    llm_counter = Counter(
        str(get_nested(record, "env.llm_model"))
        for record in executed.values()
        if not is_placeholder(get_nested(record, "env.llm_model"))
    )

    record_errors = sum(
        issue.severity == "ERROR"
        for case_issues in issues_by_case.values()
        for issue in case_issues
    )
    screenshot_compliant = 0
    for record in executed.values():
        screenshots = record.get("screenshots", [])
        error_ok = record.get("verdict") != "FAIL" or any(
            "error" in f"{item.get('file', '')} {item.get('desc', '')}".lower()
            or "报错" in f"{item.get('file', '')} {item.get('desc', '')}"
            or "错误" in f"{item.get('file', '')} {item.get('desc', '')}"
            for item in screenshots
            if isinstance(item, dict)
        )
        if isinstance(screenshots, list) and len(screenshots) >= 4 and error_ok:
            screenshot_compliant += 1

    acceptance_checks = {
        "problem_set_valid": not any(issue.severity == "ERROR" for issue in problem_issues),
        "assignments_valid": not any(issue.severity == "ERROR" for issue in assignment_issues),
        "p0_usable_at_least_target": p0_usable >= p0_target(len(p0_ids)),
        "record_completeness_at_least_90_pct": (
            bool(executed) and sum(completeness_values) / len(completeness_values) >= 90
        ),
        "all_cases_executed": len(executed) == total,
        "all_judged_records_reviewed": len(judged) == total and len(reviewed) == total,
        "no_record_validation_errors": record_errors == 0,
    }

    return {
        "schema_version": "1.0",
        "generated_at": now_iso(),
        "strict_mode": strict,
        "problem_set": {
            "total": total,
            "single_source": sum(item["layer"] == "single_source" for item in problems.values()),
            "multi_source": sum(item["layer"] == "multi_source" for item in problems.values()),
            "p0_total": len(p0_ids),
        },
        "progress": {
            "executed": len(executed),
            "judged": len(judged),
            "reviewed": len(reviewed),
            "execution_rate": round(len(executed) / total, 4) if total else 0,
            "review_rate": round(len(reviewed) / len(judged), 4) if judged else 0,
        },
        "verdicts": {
            "pass": verdicts["PASS"],
            "pass_with_fallback": verdicts["PASS_WITH_FALLBACK"],
            "fail": verdicts["FAIL"],
            "pass_rate": round(verdicts["PASS"] / len(judged), 4) if judged else None,
            "fallback_rate": (
                round(verdicts["PASS_WITH_FALLBACK"] / len(judged), 4) if judged else None
            ),
            "fail_rate": round(verdicts["FAIL"] / len(judged), 4) if judged else None,
            "usable_rate": round(usable / len(judged), 4) if judged else None,
        },
        "quality": {
            "record_completeness_avg_pct": (
                round(sum(completeness_values) / len(completeness_values), 1)
                if completeness_values
                else 0.0
            ),
            "records_at_least_90_pct": complete_records,
            "records_at_least_90_rate": (
                round(complete_records / len(executed), 4) if executed else 0
            ),
            "screenshot_compliance_rate": (
                round(screenshot_compliant / len(executed), 4) if executed else 0
            ),
            "validation_error_count": record_errors,
        },
        "p0_acceptance": {
            "usable": p0_usable,
            "total": len(p0_ids),
            "target": p0_target(len(p0_ids)),
            "passed": p0_usable >= p0_target(len(p0_ids)),
        },
        "dimensions": {
            "language": dimension_summary(problems, records, "lang"),
            "source": dimension_summary(problems, records, "source"),
            "req_type": dimension_summary(problems, records, "req_types"),
            "llm_model": dict(sorted(llm_counter.items())),
        },
        "failure_top3": [
            {"category": category, "count": count}
            for category, count in failure_counter.most_common(3)
        ],
        "issues": {
            "problem_set": [asdict(issue) for issue in problem_issues],
            "assignments": [asdict(issue) for issue in assignment_issues],
            "records": {
                case_id: [asdict(issue) for issue in case_issues]
                for case_id, case_issues in sorted(issues_by_case.items())
                if case_issues
            },
        },
        "acceptance_checks": acceptance_checks,
    }


def pct(value: Any) -> str:
    return "N/A" if value is None else f"{float(value):.1%}"


def write_summary(report: dict[str, Any]) -> None:
    progress = report["progress"]
    verdicts = report["verdicts"]
    quality = report["quality"]
    p0 = report["p0_acceptance"]
    checks = report["acceptance_checks"]
    top3 = report["failure_top3"]
    top3_text = "、".join(f"{item['category']}({item['count']})" for item in top3) or "暂无"

    lines = [
        "# 问题集执行统计摘要",
        "",
        f"> 生成时间：{report['generated_at']}",
        "",
        "## 总览",
        "",
        "| 指标 | 当前值 |",
        "|---|---:|",
        f"| 题目总数 | {report['problem_set']['total']} |",
        f"| 已执行 / 已判定 / 已复核 | {progress['executed']} / {progress['judged']} / {progress['reviewed']} |",
        f"| PASS / 降级通过 / FAIL | {verdicts['pass']} / {verdicts['pass_with_fallback']} / {verdicts['fail']} |",
        f"| 通过率 | {pct(verdicts['pass_rate'])} |",
        f"| 降级率 | {pct(verdicts['fallback_rate'])} |",
        f"| 失败率 | {pct(verdicts['fail_rate'])} |",
        f"| 可用率 | {pct(verdicts['usable_rate'])} |",
        f"| 记录平均完整率 | {quality['record_completeness_avg_pct']:.1f}% |",
        f"| 截图合规率 | {pct(quality['screenshot_compliance_rate'])} |",
        f"| P0 可用数据包 | {p0['usable']}/{p0['total']}（目标至少 {p0['target']}） |",
        f"| 失败原因 TOP 3 | {top3_text} |",
        "",
        "## Day 8 验收检查",
        "",
    ]
    labels = {
        "problem_set_valid": "问题集结构合法",
        "assignments_valid": "任务分配完整",
        "p0_usable_at_least_target": f"P0 至少 {p0['target']}/{p0['total']} 可用",
        "record_completeness_at_least_90_pct": "记录完整率至少 90%",
        "all_cases_executed": "全部题目已执行",
        "all_judged_records_reviewed": "全部记录已判定并复核",
        "no_record_validation_errors": "没有记录质量错误",
    }
    lines.extend(f"- [{'x' if passed else ' '}] {labels[key]}" for key, passed in checks.items())
    lines.extend(
        [
            "",
            "## 说明",
            "",
            "本文件由 `scripts/manage_test_records.py` 自动生成。没有正式执行记录时，统计值保持为 0 或 N/A，不代表系统测试通过。",
            "",
        ]
    )
    SUMMARY_PATH.write_text("\n".join(lines), encoding="utf-8")


def print_issues(title: str, issues: list[Issue]) -> None:
    print(f"\n{title}: {len(issues)} 个问题")
    for issue in issues:
        print(f"  [{issue.severity}] {issue.location}: {issue.message}")


def run_all(strict: bool) -> int:
    problem_set = load_problem_set()
    problems = problem_map(problem_set)
    problem_issues = validate_problem_set(problem_set)
    assignments = load_assignments()
    assignment_issues = validate_assignments(assignments, problems)
    records, issues_by_case = load_records(problems)
    rows = build_progress_rows(problems, assignments, records, issues_by_case)
    write_progress(rows)
    report = build_quality_report(
        problems,
        records,
        issues_by_case,
        problem_issues,
        assignment_issues,
        strict,
    )
    write_json(QUALITY_REPORT_PATH, report)
    write_summary(report)

    record_issues = [item for values in issues_by_case.values() for item in values]
    print_issues("问题集", problem_issues)
    print_issues("任务分配", assignment_issues)
    print_issues("已有记录", record_issues)
    print(f"\n已更新: {PROGRESS_PATH.relative_to(ROOT)}")
    print(f"已更新: {QUALITY_REPORT_PATH.relative_to(ROOT)}")
    print(f"已更新: {SUMMARY_PATH.relative_to(ROOT)}")

    has_errors = any(
        issue.severity == "ERROR" for issue in [*problem_issues, *assignment_issues, *record_issues]
    )
    if strict:
        failed_checks = [key for key, passed in report["acceptance_checks"].items() if not passed]
        if failed_checks:
            print(f"\n严格验收未通过: {', '.join(failed_checks)}")
            has_errors = True
    return 1 if has_errors else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate-problems", help="校验问题集和任务分配")
    init_parser = subparsers.add_parser("init-record", help="初始化单个 case 的记录目录")
    init_parser.add_argument("case_id")
    init_parser.add_argument("--executor", choices=sorted(ALLOWED_EXECUTORS))
    subparsers.add_parser("validate-records", help="校验所有已有记录")
    subparsers.add_parser("sync-progress", help="刷新 progress.csv")
    subparsers.add_parser("summarize", help="刷新质量报告和统计摘要")
    all_parser = subparsers.add_parser("all", help="执行全部校验、进度与统计任务")
    all_parser.add_argument("--strict", action="store_true", help="按 Day 8 验收线严格检查")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "init-record":
        try:
            path = init_record(args.case_id, args.executor)
        except (FileExistsError, OSError, ValueError) as exc:
            print(f"初始化失败: {exc}", file=sys.stderr)
            return 1
        print(f"已创建: {path.relative_to(ROOT)}")
        return 0
    if args.command == "validate-problems":
        problem_set = load_problem_set()
        problems = problem_map(problem_set)
        issues = validate_problem_set(problem_set)
        issues.extend(validate_assignments(load_assignments(), problems))
        print_issues("问题集与任务分配", issues)
        return 1 if any(item.severity == "ERROR" for item in issues) else 0
    if args.command == "validate-records":
        problems = problem_map(load_problem_set())
        _, issues_by_case = load_records(problems)
        issues = [item for values in issues_by_case.values() for item in values]
        print_issues("已有记录", issues)
        return 1 if any(item.severity == "ERROR" for item in issues) else 0
    if args.command in {"sync-progress", "summarize", "all"}:
        return run_all(getattr(args, "strict", False))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
