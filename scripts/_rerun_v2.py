"""重跑 3 个仍失败 case：huggingface_002/005、github_002（枚举比较修复后验证）。"""
import asyncio, json, sys, time
from datetime import datetime
from pathlib import Path
from playwright.async_api import async_playwright

FRONTEND = "http://127.0.0.1:7860"
ROOT = Path(__file__).resolve().parents[1]
DELIVER = ROOT / "deliverables" / "day3" / "C"
TMP = ROOT / "scripts" / "_tmp_day3r"

CASES = [
    ("ss_huggingface_002", "检索 ACT 机器人操作策略"),
]
TABS = {"目标输入": "01_parse_goal.png", "进度展示": "02_retrieve.png",
        "校验与缺失项": "03_validate.png", "数据包审查": "04_package.png"}
INTERRUPT_MSG = "已生成中间结果"
NO_PENDING_MSG = "没有待继续的运行"


async def go_tab(page, name):
    await page.get_by_role("tab", name=name, exact=True).click()


async def wait_status(page, predicate, timeout_s=900.0):
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
    ev = {"case_id": cid, "input": goal, "executed_at": datetime.now().isoformat(timespec="seconds"), "steps": {}}
    await go_tab(page, "目标输入"); await page.wait_for_timeout(400)
    await page.locator("label").filter(has_text="真实流程").first.click()
    await page.wait_for_timeout(400)
    await page.get_by_label("实验目标").fill(goal)
    await page.wait_for_timeout(300)
    await page.get_by_role("button", name="运行", exact=True).click()
    status = await wait_status(page, lambda s: INTERRUPT_MSG in s)
    ev["steps"]["interrupt_reached"] = INTERRUPT_MSG in status
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
            (TMP / f"v2_{cid}.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
            mf = ev["steps"].get("manifest") or {}
            print(f"  {cid}: pkg={mf.get('package_info', {}).get('status')} files={len(mf.get('files', []))} "
                  f"missing={len(mf.get('missing_items', []))} final={ev['steps'].get('final_status','')!r}", flush=True)
            await go_tab(page, "目标输入"); await page.wait_for_timeout(400)
        await browser.close()
    print("V2 DONE")


if __name__ == "__main__":
    asyncio.run(main())
