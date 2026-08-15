"""重跑 Day3-C 的 22 个 FAIL case（修复后验证 PASS 化）。

沿用已验证前端真实流程：运行 → 中断 → 截中间态 → 继续运行 → 截最终态。
证据 JSON 写入 scripts/_tmp_day3r/；截图覆盖 deliverables/day3/C/<case>/screenshots/。
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright

FRONTEND = "http://127.0.0.1:7860"
ROOT = Path(__file__).resolve().parents[1]
DELIVER = ROOT / "deliverables" / "day3" / "C"
TMP = ROOT / "scripts" / "_tmp_day3r"

# 22 个 FAIL case（按计划顺序；ieee 3 题豁免为 P7_ENV，paperswithcode_002 一并重跑观察）
CASES = [
    ("ss_huggingface_002", "检索 ACT 机器人操作策略"),
    ("ss_huggingface_005", "检索灵巧操作策略权重"),
    ("ss_paperswithcode_002", "检索 grasp detection 论文及其代码"),
    ("ss_github_002", "检索 GitHub 上的 Franka Panda URDF 模型"),
    ("ss_zenodo_002", "检索机械臂关节数据"),
    ("ss_zenodo_004", "检索机械臂力觉传感器数据"),
    ("ss_graspnet_002", "获取 banana 的单个 grasp 文件"),
    ("ss_mujoco_001", "检索 mujoco_menagerie 中 franka 的真实场景"),
    ("ss_dexgrasp_001", "获取 banana 的 DexGrasp 抓取文件"),
    ("ss_dexgrasp_002", "获取 apple 的 DexGrasp 抓取文件"),
    ("ss_dexgrasp_003", "获取 mug 的 DexGrasp 抓取文件"),
    ("ss_ycb_001", "获取 banana 的 grasp 数据"),
    ("ss_ycb_002", "获取 mug 的 grasp 数据"),
    ("ss_ycb_004", "获取 banana 的 mesh 模型"),
    ("ss_mujoco_002", "检索 mujoco_menagerie 中 aloha 的真实场景"),
    ("ss_isaac_001", "获取 Franka 的 Isaac Sim 场景配置"),
    ("ss_dexgrasp_004", "获取 bottle 的 DexGrasp 抓取文件"),
    ("ss_dexgrasp_005", "获取 scissors 的 DexGrasp 抓取文件"),
    ("ss_isaac_002", "获取 UR5 的 Isaac Sim 场景配置"),
    ("ss_ieee_001", "检索 robot grasping 的论文"),
    ("ss_ieee_002", "检索 dexterous manipulation 论文"),
    ("ss_ieee_003", "检索机械臂抓取论文"),
    ("ms_004", "UR5 with Robotiq 2F-85 grasps YCB apple"),
]

TABS = {"目标输入": "01_parse_goal.png", "进度展示": "02_retrieve.png",
        "校验与缺失项": "03_validate.png", "数据包审查": "04_package.png"}
INTERRUPT_MSG = "已生成中间结果"
NO_PENDING_MSG = "没有待继续的运行"


async def go_tab(page, name):
    await page.get_by_role("tab", name=name, exact=True).click()


async def wait_status(page, predicate, timeout_s=600.0):
    deadline = time.monotonic() + timeout_s
    last = ""
    while time.monotonic() < deadline:
        try:
            last = await page.get_by_label("状态").input_value()
        except Exception:
            last = ""
        if predicate(last):
            return last
        await page.wait_for_timeout(1500)
    return last


async def run_one(page, cid, goal, case_dir):
    inter = case_dir / "screenshots" / "intermediate"
    final = case_dir / "screenshots" / "final"
    inter.mkdir(parents=True, exist_ok=True)
    final.mkdir(parents=True, exist_ok=True)
    ev = {"case_id": cid, "input": goal, "executed_at": datetime.now().isoformat(timespec="seconds"),
          "steps": {}}
    await go_tab(page, "目标输入"); await page.wait_for_timeout(400)
    await page.locator("label").filter(has_text="真实流程").first.click()
    await page.wait_for_timeout(400)
    await page.get_by_label("实验目标").fill(goal)
    await page.wait_for_timeout(300)
    await page.get_by_role("button", name="运行", exact=True).click()
    status = await wait_status(page, lambda s: INTERRUPT_MSG in s)
    ev["steps"]["interrupt_reached"] = INTERRUPT_MSG in status
    ev["steps"]["interrupt_status"] = status
    for tab, fn in TABS.items():
        await go_tab(page, tab); await page.wait_for_timeout(450)
        await page.screenshot(path=str(inter / fn), full_page=True)
    await go_tab(page, "目标输入"); await page.wait_for_timeout(400)
    await page.get_by_role("button", name="继续运行", exact=True).click(force=True)
    await page.wait_for_timeout(400)
    status = await wait_status(page, lambda s: (s and INTERRUPT_MSG not in s and NO_PENDING_MSG not in s))
    ev["steps"]["final_status"] = status
    for tab, fn in TABS.items():
        await go_tab(page, tab); await page.wait_for_timeout(450)
        await page.screenshot(path=str(final / fn), full_page=True)
    await go_tab(page, "数据包审查"); await page.wait_for_timeout(300)
    try:
        txt = await page.get_by_label("manifest").input_value()
        ev["steps"]["manifest"] = json.loads(txt) if txt.strip() else None
    except Exception as exc:
        ev["steps"]["manifest_error"] = str(exc)
    return ev


async def main():
    TMP.mkdir(parents=True, exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=True)
        page = await browser.new_page(viewport={"width": 1440, "height": 900})
        await page.goto(FRONTEND, wait_until="domcontentloaded", timeout=60000)
        await page.wait_for_timeout(1500)
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 前端已加载", flush=True)
        for cid, goal in CASES:
            t0 = time.monotonic()
            print(f"[{datetime.now().strftime('%H:%M:%S')}] === {cid} ===", flush=True)
            try:
                ev = await run_one(page, cid, goal, DELIVER / cid)
            except Exception as exc:
                ev = {"case_id": cid, "input": goal, "error": str(exc), "steps": {}}
                print(f"  ERROR: {exc}", flush=True)
            ev["elapsed_s"] = round(time.monotonic() - t0)
            (TMP / f"{cid}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
            mf = ev["steps"].get("manifest") or {}
            print(f"  {cid}: pkg={mf.get('package_info', {}).get('status')} "
                  f"files={len(mf.get('files', []))} missing={len(mf.get('missing_items', []))} "
                  f"elapsed={ev['elapsed_s']}s", flush=True)
            await go_tab(page, "目标输入"); await page.wait_for_timeout(400)
        await browser.close()
    print("RERUN DONE")


if __name__ == "__main__":
    asyncio.run(main())
