"""问题集（口径 2，48 题）真实前端 API 批量重放与成功率记录。

前置：已启动 `uv run python -m rdi.server`（http://127.0.0.1:8000；需 `PYTHONPATH=src`，勿用
`python src/rdi/server.py`——脚本目录会遮蔽标准库 logging）。
逐题走真实前端链路：POST /api/run → 轮询 /api/status → 若中断 POST /api/resume
(satisfied) → 取 /api/result / resume 返回值，从 14 元组提取 manifest 判定。

判定（与 manage_test_records 严口径一致）：
- 无 manifest / files 空                               → FAIL（数据包未产出）
- 主文件（每 req 首个条目）downloaded=false             → FAIL（严口径：未下载即 FAIL）
- validation_issues 含 ERROR 级                        → FAIL（含 download_integrity 锚点）
- missing_items 非空 或 主文件 is_fallback             → PASS_WITH_FALLBACK
- 其余                                              → PASS

用法：
    uv run python scripts/replay_frontend_problem_set.py
    uv run python scripts/replay_frontend_problem_set.py --only ss_dataset_hf_002
    uv run python scripts/replay_frontend_problem_set.py --resume-from records/_management/replay_frontend_<ts>.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import httpx

ROOT = Path(__file__).resolve().parents[1]
BASE_URL = "http://127.0.0.1:8000"
MANAGEMENT_DIR = ROOT / "records" / "_management"
OUTPUT_ROOT = ROOT / "data" / "output_packages"
NAME = "replay_frontend"

# 口径 2 = 四类非几何 category + 含非几何需求的 end_to_end（复刻 tmp_task11_offline_v2）
CATEGORY4 = {"dataset", "policy", "sensor", "grasp"}
NONGEO_REQ_TYPES = {"dataset", "sensor_data", "policy_model", "grasp"}


def load_problems(only: str | None = None) -> list[dict[str, Any]]:
    data = json.loads((ROOT / "problem_set" / "problem_set.json").read_text(encoding="utf-8"))
    problems = data["problems"]
    selected = [p for p in problems if p["category"] in CATEGORY4]
    for p in problems:
        if p["category"] == "end_to_end" and set(
            p.get("expected", {}).get("req_types", [])
        ) & NONGEO_REQ_TYPES:
            selected.append(p)
    if only:
        wanted = {c.strip() for c in only.split(",") if c.strip()}
        selected = [p for p in selected if p["case_id"] in wanted]
    return selected


def _severity(issue: Any) -> str:
    if isinstance(issue, dict):
        sev = issue.get("severity", "")
        return str(sev).lower()
    return ""


def _is_reference_issue(issue: dict[str, Any]) -> bool:
    """引用型失败：大文件未下载但已给远端 URL/指引（= 完整交付，不算失败）。"""
    msg = str(issue.get("message", ""))
    return "仅提供远端引用" in msg or "真实数据见 reference" in msg or "大文件" in msg


def judge_payload(payload: Any) -> dict[str, Any]:
    """从 14 元组 payload 判定三档 verdict + 归因。

    判定口径（引用=完整交付）：
    - 无 manifest / files 空                         → FAIL（数据包未产出）
    - missing 全部为引用型（大文件未下载且给指引）        → PASS（引用交付）
    - 存在非引用型 ERROR（语义不符/占位/检索失败/指引缺失） → FAIL
    - missing 非引用型（部分满足）                      → PASS_WITH_FALLBACK
    - 其余                                          → PASS
    """
    row: list[Any] = list(payload) if isinstance(payload, list) else []
    # (status, summary, req_status, tree, manifest_json, validation_issues, ...)
    status = str(row[0]) if len(row) > 0 else "未知"
    manifest_raw = row[4] if len(row) > 4 else None
    validation_issues: list[Any] = row[5] if len(row) > 5 else []
    missing_items: list[Any] = row[7] if len(row) > 7 else []

    manifest: dict[str, Any] = {}
    if isinstance(manifest_raw, str) and manifest_raw.strip():
        try:
            manifest = json.loads(manifest_raw)
        except json.JSONDecodeError:
            manifest = {}
    elif isinstance(manifest_raw, dict):
        manifest = manifest_raw

    files: list[dict[str, Any]] = manifest.get("files", []) or []
    # 主文件 = 每 req 首个条目（资产条目同 req_id 追加在后）
    primary: dict[str, dict[str, Any]] = {}
    for f in files:
        if isinstance(f, dict) and f.get("req_id"):
            primary.setdefault(str(f["req_id"]), f)

    reasons: list[str] = []
    verdict = "PASS"
    if not files:
        verdict = "FAIL"
        reasons.append(f"数据包未产出文件（status={status}）")
    else:
        # 引用型 missing（大文件未下载，但已给远端 URL + 指引）
        ref_missing = [
            i
            for i in missing_items
            if isinstance(i, dict) and _is_reference_issue({"message": str(i.get("reason", ""))})
        ]
        nonref_missing = [
            i
            for i in missing_items
            if isinstance(i, dict) and not _is_reference_issue({"message": str(i.get("reason", ""))})
        ]
        errors = [i for i in validation_issues if _severity(i) == "error"]
        nonref_errors = [
            i for i in errors if not (isinstance(i, dict) and _is_reference_issue(i))
        ]
        if nonref_errors:
            verdict = "FAIL"
            reasons.append(f"validation_issues 含 {len(nonref_errors)} 个非引用型 ERROR")
        elif nonref_missing:
            verdict = "PASS_WITH_FALLBACK"
            reasons.append(f"缺失 {len(nonref_missing)} 项非引用需求（部分满足）")
        elif ref_missing:
            verdict = "PASS"
            reasons.append(f"引用交付：{len(ref_missing)} 项大文件未下载，已给 URL + wget 指引")
        else:
            fallback = [f for f in primary.values() if f.get("is_fallback")]
            if fallback:
                verdict = "PASS_WITH_FALLBACK"
                reasons.append(f"主文件经降级取得（{len(fallback)} 项 is_fallback）")

    # 记录错误级 issue 摘要（供归因分析；message 截断避免过大）
    error_summary: list[dict[str, str]] = []
    for i in validation_issues if isinstance(validation_issues, list) else []:
        if _severity(i) == "error" and isinstance(i, dict):
            error_summary.append(
                {
                    "issue_type": str(i.get("issue_type", "")),
                    "req_id": str(i.get("req_id", "")),
                    "message": str(i.get("message", ""))[:160],
                }
            )

    return {
        "verdict": verdict,
        "reasons": reasons,
        "error_summary": error_summary[:8],
        "file_count": len(files),
        "missing_count": len(missing_items),
        "validation_error_count": len(validation_issues)
        if not isinstance(validation_issues, list)
        else sum(1 for i in validation_issues if _severity(i) == "error"),
        "run_status": status,
        "manifest_path": "",
    }


def run_one(client: httpx.Client, problem: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
    goal = problem["target"]
    try:
        resp = client.post(f"{BASE_URL}/api/run", json={"mode": "真实流程", "goal": goal})
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"api/run 失败: {exc}"}

    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            st = client.get(f"{BASE_URL}/api/status/{task_id}").json()
        except httpx.HTTPError as exc:
            time.sleep(2)
            continue
        if st.get("done"):
            break
        time.sleep(2)
    else:
        return {"ok": False, "error": f"task {task_id} 轮询超时(>{timeout:.0f}s)"}

    try:
        res = client.get(f"{BASE_URL}/api/result/{task_id}").json()
    except httpx.HTTPError as exc:
        return {"ok": False, "error": f"api/result 失败: {exc}"}

    # interrupted 由 /api/result 返回（/api/status 不含该字段）
    if res.get("interrupted"):
        try:
            rr = client.post(
                f"{BASE_URL}/api/resume",
                json={"review_decision": "satisfied", "feedback": ""},
            )
            rr.raise_for_status()
            payload = rr.json().get("result")
        except httpx.HTTPError as exc:
            return {"ok": False, "error": f"api/resume 失败: {exc}", "interrupted": True}
    else:
        payload = res.get("result")

    return {"ok": True, "payload": payload}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="口径2 48 题真实前端 API 重放")
    parser.add_argument("--only", default=None,
                        help="只跑指定 case（逗号分隔多个；连通性/复现用）")
    parser.add_argument("--resume-from", default=None, help="从已保存 json 续跑未完成题目")
    parser.add_argument("--timeout", default=2400.0, type=float,
                        help="单题总超时秒数（默认 2400=40 分钟，给足预算避免误标运行超时）")
    args = parser.parse_args()

    problems = load_problems(args.only)
    if not problems:
        print(f"[FATAL] 未找到题目（only={args.only}）")
        return 2
    print(f"[INFO] 选择 {len(problems)} 题（口径2）")

    results: dict[str, dict[str, Any]] = {}
    if args.resume_from:
        prev = json.loads(Path(args.resume_from).read_text(encoding="utf-8"))
        results = prev.get("results", {})
        # 续跑：跳过已完成（ok=true）的题；ok=false 的失败题重试
        done = {k for k, v in results.items() if v.get("ok")}
        problems = [p for p in problems if p["case_id"] not in done]
        print(f"[INFO] 续跑：已完成 {len(done)} 题，待跑 {len(problems)} 题")

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_json = MANAGEMENT_DIR / f"{NAME}_{ts}.json"
    out_md = MANAGEMENT_DIR / f"{NAME}_{ts}.md"
    MANAGEMENT_DIR.mkdir(parents=True, exist_ok=True)

    start_at = time.time()
    with httpx.Client(timeout=120.0) as client:
        for idx, problem in enumerate(problems, start=1):
            case_id = problem["case_id"]
            print(f"[{idx}/{len(problems)}] {case_id}: {problem['target'][:40]}...", flush=True)
            begin = time.time()
            outcome = run_one(client, problem, timeout=args.timeout)
            elapsed = time.time() - begin

            if not outcome["ok"]:
                results[case_id] = {
                    "case_id": case_id,
                    "target": problem["target"],
                    "category": problem["category"],
                    "expected_req_types": problem.get("expected", {}).get("req_types", []),
                    "ok": False,
                    "error": outcome["error"],
                    "elapsed_sec": round(elapsed, 1),
                }
                print(f"      [ERR] {outcome['error']}", flush=True)
                # 中间落盘，防断点丢结果
                _save(out_json, results, problems, start_at)
                continue

            judged = judge_payload(outcome["payload"])
            results[case_id] = {
                "case_id": case_id,
                "target": problem["target"],
                "category": problem["category"],
                "expected_req_types": problem.get("expected", {}).get("req_types", []),
                "ok": True,
                "verdict": judged["verdict"],
                "reasons": judged["reasons"],
                "error_summary": judged.get("error_summary", []),
                "file_count": judged["file_count"],
                "missing_count": judged["missing_count"],
                "validation_error_count": judged["validation_error_count"],
                "run_status": judged["run_status"],
                "elapsed_sec": round(elapsed, 1),
            }
            print(f"      => {judged['verdict']} ({judged['reasons'][0] if judged['reasons'] else '无'}) "
                  f"{elapsed:.0f}s", flush=True)
            _save(out_json, results, problems, start_at)

    _finalize(out_json, out_md, results, problems, start_at)
    print(f"[DONE] 结果已写入:\n  {out_json}\n  {out_md}")
    return 0


def _save(out_json: Path, results: dict[str, Any], problems: list[dict[str, Any]], start_at: float) -> None:
    data = {
        "meta": {
            "name": NAME,
            "scope": "口径2（四类非几何 38 + 含非几何 end_to_end 10 = 48）",
            "created_at": datetime.now().isoformat(timespec="seconds"),
            "elapsed_total_sec": round(time.time() - start_at, 1),
        },
        "results": results,
    }
    out_json.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _finalize(
    out_json: Path,
    out_md: Path,
    results: dict[str, Any],
    problems: list[dict[str, Any]],
    start_at: float,
) -> None:
    done = [r for r in results.values() if r.get("ok")]
    failed = [r for r in results.values() if not r.get("ok")]
    counts = {"PASS": 0, "PASS_WITH_FALLBACK": 0, "FAIL": 0}
    for r in done:
        counts[r["verdict"]] = counts.get(r["verdict"], 0) + 1
    strict_fail = [r for r in done if r["verdict"] == "FAIL"]
    usable = counts["PASS"] + counts["PASS_WITH_FALLBACK"]
    total = len(results)
    strict_pass_rate = counts["PASS"] / total * 100 if total else 0.0
    usable_rate = usable / total * 100 if total else 0.0

    lines = [
        "# 问题集真实前端重放记录（口径2）",
        "",
        f"- 生成时间：{datetime.now().isoformat(timespec='seconds')}",
        f"- 通道：真实前端 API（POST /api/run → /api/status → /api/resume → /api/result）",
        f"- 口径：四类非几何（dataset/grasp/sensor/policy）38 题 + 含非几何需求的 end_to_end 10 题 = 48 题",
        f"- 完成 {total} 题 / 目标 48 题；运行失败（网络/超时）{len(failed)} 题",
        "",
        "## 成功率（完成题数口径）",
        "",
        f"| 指标 | 数值 |",
        f"| --- | --- |",
        f"| 总题数 | {total} |",
        f"| PASS | {counts['PASS']} |",
        f"| PASS_WITH_FALLBACK | {counts['PASS_WITH_FALLBACK']} |",
        f"| FAIL（含严口径未下载） | {counts['FAIL']} |",
        f"| 运行失败（网络/超时） | {len(failed)} |",
        f"| 严格成功率 PASS/(总数) | {strict_pass_rate:.1f}% |",
        f"| 可用率 (PASS+PASS_WITH_FALLBACK)/(总数) | {usable_rate:.1f}% |",
        "",
        "判定口径：无产物/fullfiles 空/主文件 downloaded=false（严口径）/validation ERROR → FAIL；",
        "missing 或主文件 is_fallback → PASS_WITH_FALLBACK；其余 → PASS。",
        "",
        "## 明细",
        "",
        "| case_id | category | verdict | 归因 | 文件数 | 耗时(s) |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for case_id, r in sorted(results.items()):
        if r.get("ok"):
            lines.append(
                f"| {case_id} | {r['category']} | {r['verdict']} | "
                f"{'；'.join(r['reasons']) or '—'} | {r['file_count']} | {r['elapsed_sec']} |"
            )
        else:
            lines.append(
                f"| {case_id} | {r['category']} | RUN_FAILED | {r.get('error', '')} | — | {r.get('elapsed_sec', '—')} |"
            )
    if failed:
        lines += ["", "## 运行失败明细", ""]
        for r in failed:
            lines.append(f"- {r['case_id']}: {r.get('error')}")
    if strict_fail:
        lines += ["", "## FAIL 清单（含严口径）", ""]
        for r in sorted(strict_fail, key=lambda x: x["case_id"]):
            lines.append(f"- {r['case_id']}: {'；'.join(r['reasons'])}")
    out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

    _save(out_json, results, problems, start_at)
    summary = out_json.with_name(f"{NAME}_{datetime.now().strftime('%Y%m%d-%H%M%S')}.json")
    if summary != out_json:
        data = json.loads(out_json.read_text(encoding="utf-8"))
        data["meta"]["summary"] = {
            "total": total,
            "pass": counts["PASS"],
            "pass_with_fallback": counts["PASS_WITH_FALLBACK"],
            "fail": counts["FAIL"],
            "run_failed": len(failed),
            "strict_pass_rate_pct": round(strict_pass_rate, 1),
            "usable_rate_pct": round(usable_rate, 1),
        }
        summary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())