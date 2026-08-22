# -*- coding: utf-8 -*-
"""临时分析：两轮测试 FAIL 明细，聚焦 retrieval/source 拿不到数据的原因。"""
import csv, json, os, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REC = os.path.join(ROOT, "records")

rows = list(csv.DictReader(open(os.path.join(REC, "_management", "progress.csv"), encoding="utf-8-sig")))
fails = [r for r in rows if r["verdict"] == "FAIL"]
print("FAIL 总数", len(fails), "| round1", sum(1 for r in fails if r["round"] == "1"),
      "| round2", sum(1 for r in fails if r["round"] == "2"))

print("\n== 按 failure_category ==")
print(dict(collections.Counter(r["failure_category"] for r in fails)))

print("\n== 按 source ==")
print(dict(collections.Counter(r["sources"].split("|")[0] if r["sources"] else "?" for r in fails)))

print("\n== 按 source x category ==")
sc = collections.Counter((r["sources"].split("|")[0] if r["sources"] else "?", r["failure_category"]) for r in fails)
for k, v in sorted(sc.items()):
    print(f"  {k[0]:<15} {k[1]:<15} {v}")

# 提取 record.json 中 retrieve/parse/validate 的 error 原文
print("\n== FAIL 记录内 error 原因摘要 ==")
for r in fails:
    case = r["case_id"]
    p = os.path.join(REC, case, "record.json")
    if not os.path.exists(p):
        continue
    rec = json.load(open(p, encoding="utf-8"))
    errs = []
    for key in ("retrieve", "parse_goal", "validate"):
        v = rec.get(key)
        if isinstance(v, dict):
            if v.get("error"):
                errs.append(f"{key}: {str(v['error'])[:110]}")
            elif isinstance(v.get("items"), list):
                for it in v["items"]:
                    if isinstance(it, dict) and it.get("error"):
                        errs.append(f"{key}: {str(it['error'])[:110]}")
        elif isinstance(v, list):
            for it in v:
                if isinstance(it, dict) and it.get("error"):
                    errs.append(f"{key}: {str(it['error'])[:110]}")
    result = rec.get("result")
    if isinstance(result, dict) and result.get("error"):
        errs.append(f"result: {str(result['error'])[:110]}")
    print(f"\n[{case}] r{r['round']} {r['failure_category']} {r['sources'].split('|')[0]} :: {r['target'][:40]}")
    for e in errs[:6]:
        print("   ", e)