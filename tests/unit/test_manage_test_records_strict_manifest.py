"""Task 12：严口径台账判定 —— manifest 含 downloaded=false 主文件项必须判 FAIL。

覆盖 validate_record 新增规则：
1. manifest 含 downloaded=false 项 + verdict=PASS_WITH_FALLBACK → ERROR；
2. verdict=FAIL → 放行（无严口径 ERROR）；
3. manifest_path 缺失/指向不存在路径 → 跳过；
4. manifest 全部 downloaded=true → 不触发（downloaded=false 是必要条件）；
5. manifest 文件存在但不可解析（损坏 JSON）→ 跳过。
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import pytest

ROOT = Path(__file__).resolve().parents[2]
MANAGE_PATH = ROOT / "scripts" / "manage_test_records.py"

CASE_ID = "ss_allegro_005"
TARGET = "我要在仿真里用 Allegro 手抓物体，帮我找它的 URDF 模型"


@pytest.fixture(scope="module")
def manage() -> Any:
    spec = importlib.util.spec_from_file_location("manage_test_records", MANAGE_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def make_problem() -> dict[str, Any]:
    return {
        "case_id": CASE_ID,
        "layer": "single_source",
        "category": "robot_urdf",
        "source": ["allegro"],
        "target": TARGET,
        "lang": "ZH",
        "priority": "P2",
        "expected": {
            "req_types": ["robot_urdf"],
            "quality": ["real", "fallback"],
            "format": ["urdf"],
            "min_files": 1,
        },
    }


def make_record_and_files(case_dir: Path, verdict: str) -> dict[str, Any]:
    """构造一条基本合规的执行记录，并在 case 目录内落盘截图与 manifest。

    用 `__` 前缀的字段（__manifest_path）由用例按需改写。
    """
    screenshots = case_dir / "screenshots"
    screenshots.mkdir(parents=True, exist_ok=True)
    descs = ["parse-goal", "retrieve", "package", "validation-error" if verdict == "FAIL" else "validation"]
    shots = []
    for index, desc in enumerate(descs, start=1):
        (screenshots / f"{index:02d}.png").write_bytes(b"fake")
        shots.append({"file": f"screenshots/{index:02d}.png", "desc": desc})

    record: dict[str, Any] = {
        "schema_version": "1.0",
        "case_id": case_dir.name,
        "input": TARGET,
        "executor": "A",
        "executed_at": "2026-08-22T07:51:52",
        "env": {
            "llm_model": "qwen-plus",
            "llm_base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
            "mode": "real",
            "git_branch": "feat/integration-v3",
            "git_commit": "5fffe267",
            "review_decision": "satisfied",
        },
        "observations": {
            "parse_goal": {"req_list": ["robot_urdf"], "vs_expected": "match", "notes": ""},
            "retrieve": [
                {
                    "req_id": "req_000",
                    "req_type": "robot_urdf",
                    "source": "allegro",
                    "status": "success",
                    "format": "urdf",
                    "quality": "fallback",
                    "is_fallback": True,
                    "error": None,
                    "fallback_reason": "主源探活仅可达 fallback，已显式降级",
                }
            ],
            "validate": {"errors": 0, "warnings": 0, "runtime_check": "passed", "notes": ""},
            "package": {
                "dir": "data/output_packages/package-test",
                "manifest_path": "manifest.json",
                "status": "complete",
                "file_count": 1,
                "missing_items_count": 0,
                "fallback_explicit": True,
                "notes": "",
            },
        },
        "screenshots": shots,
        "verdict": verdict,
        "failure_category": "P7_PACKAGE" if verdict == "FAIL" else None,
        "failure_reason": "manifest 含未下载文件项" if verdict == "FAIL" else None,
        "notes": "",
        "reviewer": "C",
        "reviewed_at": "2026-08-22T08:00:00",
    }
    return record


def write_manifest(case_dir: Path, downloaded_flags: list[bool]) -> None:
    files = []
    for index, flag in enumerate(downloaded_flags):
        files.append(
            {
                "req_id": f"req_{index:03d}",
                "path": f"robots/req_{index:03d}.urdf",
                "format": "urdf",
                "downloaded": flag,
                "local_path": f"robots/req_{index:03d}.urdf" if flag else "",
            }
        )
    (case_dir / "manifest.json").write_text(
        json.dumps({"package_info": {"status": "complete"}, "files": files}, ensure_ascii=False),
        encoding="utf-8",
    )


def strict_issues(issues: list[Any]) -> list[Any]:
    return [issue for issue in issues if "严口径" in issue.message]


def test_undownloaded_manifest_with_fallback_reports_error(manage: Any, tmp_path: Path) -> None:
    case_dir = tmp_path / CASE_ID
    case_dir.mkdir()
    record = make_record_and_files(case_dir, verdict="PASS_WITH_FALLBACK")
    write_manifest(case_dir, [True, False, True])  # req_001 downloaded=false

    issues = manage.validate_record(record, make_problem(), case_dir)

    strict = strict_issues(issues)
    assert len(strict) == 1
    assert strict[0].severity == "ERROR"
    assert "必须判 FAIL" in strict[0].message and "指引照给" in strict[0].message


def test_undownloaded_manifest_with_fail_is_ok(manage: Any, tmp_path: Path) -> None:
    case_dir = tmp_path / CASE_ID
    case_dir.mkdir()
    record = make_record_and_files(case_dir, verdict="FAIL")
    write_manifest(case_dir, [True, False])  # 存在 downloaded=false，但 verdict=FAIL

    issues = manage.validate_record(record, make_problem(), case_dir)

    assert strict_issues(issues) == []


def test_missing_manifest_path_skips_rule(manage: Any, tmp_path: Path) -> None:
    case_dir = tmp_path / CASE_ID
    case_dir.mkdir()
    record = make_record_and_files(case_dir, verdict="PASS_WITH_FALLBACK")
    record["observations"]["package"]["manifest_path"] = "missing/manifest.json"

    issues = manage.validate_record(record, make_problem(), case_dir)

    assert strict_issues(issues) == []


def test_all_downloaded_manifest_skips_rule(manage: Any, tmp_path: Path) -> None:
    case_dir = tmp_path / CASE_ID
    case_dir.mkdir()
    record = make_record_and_files(case_dir, verdict="PASS_WITH_FALLBACK")
    write_manifest(case_dir, [True, True, True])  # 全部已下载

    issues = manage.validate_record(record, make_problem(), case_dir)

    assert strict_issues(issues) == []


def test_unreadable_manifest_skips_rule(manage: Any, tmp_path: Path) -> None:
    case_dir = tmp_path / CASE_ID
    case_dir.mkdir()
    record = make_record_and_files(case_dir, verdict="PASS_WITH_FALLBACK")
    (case_dir / "manifest.json").write_text("{not valid json", encoding="utf-8")

    issues = manage.validate_record(record, make_problem(), case_dir)

    assert strict_issues(issues) == []
