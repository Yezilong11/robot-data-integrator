"""汇总 22 FAIL 重跑证据，判定 verdict。"""
import json
from pathlib import Path

TMP = Path(r"d:\tiaozhanbei\robot-data-integrator\scripts\_tmp_day3r")
ORDER = ["ss_huggingface_002","ss_huggingface_005","ss_paperswithcode_002","ss_github_002",
         "ss_zenodo_002","ss_zenodo_004","ss_graspnet_002","ss_mujoco_001","ss_dexgrasp_001",
         "ss_dexgrasp_002","ss_dexgrasp_003","ss_ycb_001","ss_ycb_002","ss_ycb_004",
         "ss_mujoco_002","ss_isaac_001","ss_dexgrasp_004","ss_dexgrasp_005","ss_isaac_002",
         "ss_ieee_001","ss_ieee_002","ss_ieee_003","ms_004"]

for cid in ORDER:
    p = TMP / f"{cid}.json"
    if not p.exists():
        print(f"{cid}: NO EVIDENCE")
        continue
    ev = json.loads(p.read_text(encoding="utf-8"))
    steps = ev.get("steps", {})
    mf = steps.get("manifest") or {}
    files = mf.get("files", [])
    missing = mf.get("missing_items", [])
    fb = any(f.get("is_fallback") for f in files)
    status = mf.get("package_info", {}).get("status")
    miss_reasons = [m.get("reason", "")[:90] for m in missing]
    file_fmts = [f.get("format") for f in files]
    print(f"{cid}: status={status} files={len(files)}{file_fmts} missing={len(missing)}{miss_reasons} fallback={fb} final={steps.get('final_status','')!r}")
