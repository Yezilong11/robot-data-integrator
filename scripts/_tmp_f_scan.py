"""一次性脚本：扫描 F 二轮 11 题的提交状态与判定。"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RECORDS = ROOT / "records"

f_cases = ["ms_011","ss_allegro_004","ss_dataset_graspnet_001","ss_franka_005",
           "ss_grasp_ycb_001","ss_huggingface_006","ss_ieee_004","ss_isaac_005",
           "ss_mujoco_008","ss_sensor_zenodo_002","ss_ycb_007"]

for c in f_cases:
    p = RECORDS / c / "record.json"
    if not p.exists():
        print(f"{c}: 无 record.json")
        continue
    try:
        rec = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"{c}: 解析失败 {e}")
        continue
    print(f"{c}: executor={rec.get('executor','?')} verdict={rec.get('verdict','?')} "
          f"executed_at={rec.get('executed_at','?')} reviewer={rec.get('reviewer','-')} "
          f"reviewed_at={rec.get('reviewed_at','-')} shots={len(rec.get('screenshots') or [])} "
          f"fail={rec.get('failure_category','')} reason={rec.get('failure_reason','')}")