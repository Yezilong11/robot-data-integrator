"""汇总 v2/v3 重跑证据判定。"""
import json
from pathlib import Path

TMP = Path(r"d:\tiaozhanbei\robot-data-integrator\scripts\_tmp_day3r")
for cid in ["v2_ss_huggingface_002", "v2_ss_huggingface_005"]:
    p = TMP / f"{cid}.json"
    if not p.exists():
        print(f"{cid}: NO EVIDENCE")
        continue
    ev = json.loads(p.read_text(encoding="utf-8"))
    mf = ev.get("steps", {}).get("manifest") or {}
    files = mf.get("files", [])
    missing = mf.get("missing_items", [])
    fb = any(f.get("is_fallback") for f in files)
    miss_reasons = [m.get("reason", "")[:100] for m in missing]
    file_fmts = [f.get("format") for f in files]
    print(f"{cid}: status={mf.get('package_info',{}).get('status')} files={len(files)}{file_fmts} "
          f"missing={len(missing)}{miss_reasons} fallback={fb}")
