"""逐个探活 15 个 Adapter 的 search/fetch（C 角色多场景测试）。

策略：
- search(): 用真实查询词，每调用限定 25s 超时
- fetch(): 用 mock item_id 或 search 返回的首条 ID，限定 30s 超时
  - 优先用 search 返回的真实 item_id（更具代表性）
  - search 失败时回退到预设 mock item_id
- fetch 选择小文件目标（README/config.json/URDF/XML），避免下载大 PDF/数据集
- 输出: 表格 + JSON 证据文件，供汇总

注意: IEEE_API_KEY 未配置，IEEE 仅探测构造与 key 检查。
"""

# ── 环境变量必须在 import rdi 之前设置（settings 是模块级单例） ──
import asyncio
import json
import os
import socket
import time
from dataclasses import asdict, dataclass
from typing import Any

# 国内用户：huggingface.co 不可达时切换 hf-mirror.com 镜像
if not os.environ.get("HUGGINGFACE_API_URL"):
    try:
        socket.create_connection(("huggingface.co", 443), timeout=3)
    except OSError:
        os.environ["HUGGINGFACE_API_URL"] = "https://hf-mirror.com/api"
        print("[INFO] huggingface.co 不可达，自动切换 hf-mirror.com 镜像")

from rdi.adapters import get_adapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource


@dataclass
class ProbeResult:
    """单个 Adapter 探活结果。"""

    source: str
    adapter_class: str
    construct_ok: bool
    construct_error: str = ""
    search_ok: bool = False
    search_error: str = ""
    search_latency_s: float = 0.0
    search_results_count: int = 0
    search_first_item_id: str = ""
    fetch_ok: bool = False
    fetch_error: str = ""
    fetch_latency_s: float = 0.0
    fetch_size_bytes: int = 0
    fetch_format: str = ""
    fetch_item_id_used: str = ""
    fetch_url: str = ""
    notes: str = ""


# ─── 探测用例配置 ───
# 每条: (DataSource, 搜索词, fetch mock_item_id, 备注)
# mock_item_id 仅在 search 失败时用作 fallback
PROBE_CASES: list[tuple[DataSource, str, str, str]] = [
    (DataSource.ARXIV, "robot grasping", "2104.02271", "XML API, no key"),
    (DataSource.GITHUB, "franka ros python", "numpy/numpy", "JSON API, optional token"),
    (DataSource.HUGGINGFACE, "robot grasping", "bert-base-uncased", "JSON API, may use mirror"),
    (DataSource.ZENODO, "robot grasp dataset", "search_first", "JSON API, no key"),
    (DataSource.PAPERSWITHCODE, "robot grasping", "search_first", "REST API（C12 跳过网页抓取）"),
    (DataSource.DEXGRASP, "dexgrasp", "search_first", "HF datasets API + 列文件树"),
    (DataSource.GOOGLE_SCANNED, "Mug", "search_first", "Gazebo Fuel API（C5 修 .zip 下载）"),
    (
        DataSource.GRASPNET,
        "graspnet",
        "DravenALG/GraspNet-1Billion",
        "C3 改真实 HF repo + 列文件树",
    ),
    (DataSource.YCB, "mug", "025_mug", "C4 改 ai-habitat/ycb + 列文件树"),
    (DataSource.FRANKA, "panda", "panda", "C6 改 .urdf.xacro 路径"),
    (DataSource.ALLEGRO, "allegro", "allegro_hand_v4", "C7 改 pal-robotics 仓库"),
    (DataSource.ROBOTIQ, "2f", "robotiq_2f_85", "C8 改 ros-industrial-attic + 路径映射"),
    (DataSource.MUJOCO, "aloha", "aloha", "C9/C10 改 mujoco_menagerie 真实场景"),
    (DataSource.ISAAC, "franka", "franka", "C11 改 IsaacLab Python 资产配置"),
    (DataSource.IEEE, "robot grasping", "", "需 IEEE_API_KEY，未配置"),
]

SEARCH_TIMEOUT_S = 25.0
FETCH_TIMEOUT_S = 30.0

# ─── GRASP 专项探测配置（第三次联调新增） ───
# 每条: (DataSource, 搜索词, mock_item_id, object_name)
# - 对 GraspNet/DexGrasp 以 req_type=GRASP + object_name="banana" fetch，
#   检查是否返回真实 grasp 文件（.npz/.pkl）而非 metadata JSON
# - YCB 的 fetch 无 object_name 参数，直接以物体 id "banana" 作为 item_id
GRASP_PROBE_CASES: list[tuple[DataSource, str, str, str | None]] = [
    (DataSource.GRASPNET, "graspnet", "DravenALG/GraspNet-1Billion", "banana"),
    (DataSource.DEXGRASP, "dexgrasp", "search_first", "banana"),
    (DataSource.YCB, "banana", "banana", None),
]

# 真实 grasp 文件的 format 白名单（metadata JSON 降级不在此列）
# npy：DexGraspNet 官方 data/dataset/ 单物体 grasp 文件（raw 兜底路径）
REAL_GRASP_FORMATS: set[str] = {"npz", "pkl", "mat", "npy"}


@dataclass
class GraspProbeResult:
    """GRASP 类型专项探活结果。"""

    source: str
    item_id: str
    object_name: str
    fetch_ok: bool = False
    fetch_error: str = ""
    fetch_latency_s: float = 0.0
    fetch_size_bytes: int = 0
    fetch_format: str = ""
    is_real_grasp: bool = False
    notes: str = ""


async def probe_grasp(
    source: DataSource,
    query: str,
    mock_item_id: str,
    object_name: str | None,
) -> GraspProbeResult:
    """按 GRASP 类型探测单个 Adapter 是否返回真实 grasp 文件。"""
    result = GraspProbeResult(
        source=source.value,
        item_id="",
        object_name=object_name or "",
    )
    try:
        adapter = get_adapter(source)
    except Exception as e:
        result.fetch_error = f"构造失败: {type(e).__name__}: {e}"
        return result

    # 优先用 search 返回的真实 item_id，失败回退 mock_item_id
    item_id = mock_item_id
    try:
        results = await asyncio.wait_for(adapter.search(query), timeout=SEARCH_TIMEOUT_S)
        if results:
            item_id = results[0].item_id
    except Exception:
        pass
    if item_id == "search_first":
        result.fetch_error = "search 失败，无法获取真实 item_id"
        result.item_id = item_id
        return result
    result.item_id = item_id

    t0 = time.time()
    try:
        kwargs: dict[str, Any] = {"req_type": DataReqType.GRASP}
        if object_name:
            kwargs["object_name"] = object_name
        raw = await asyncio.wait_for(adapter.fetch(item_id, **kwargs), timeout=FETCH_TIMEOUT_S)
        result.fetch_ok = True
        result.fetch_latency_s = round(time.time() - t0, 2)
        result.fetch_size_bytes = raw.size_bytes
        result.fetch_format = raw.format
        result.is_real_grasp = raw.format in REAL_GRASP_FORMATS
        if not result.is_real_grasp:
            result.notes = f"格式 {raw.format} 为降级/元数据，非真实 grasp 文件"
    except TimeoutError:
        result.fetch_error = f"超时（>{FETCH_TIMEOUT_S}s）"
        result.fetch_latency_s = round(time.time() - t0, 2)
    except AdapterError as e:
        result.fetch_error = f"AdapterError: {e.message[:200]}"
        result.fetch_latency_s = round(time.time() - t0, 2)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        status = getattr(e, "status", None)
        if status:
            msg += f" [HTTP {status}]"
        result.fetch_error = msg[:300]
        result.fetch_latency_s = round(time.time() - t0, 2)
    return result


def format_grasp_table(results: list[GraspProbeResult]) -> str:
    """生成 GRASP 探测 Markdown 表格。"""
    lines = [
        "| # | 源 | item_id | 物体 | fetch | 格式 | 大小 | 真实grasp | 延迟 | 错误/备注 |",
        "|---|-----|---------|------|-------|------|------|-----------|------|----------|",
    ]
    for i, r in enumerate(results, 1):
        err = r.fetch_error or r.notes or "—"
        size = f"{r.fetch_size_bytes}B" if r.fetch_ok else "—"
        real = "是" if r.is_real_grasp else "否"
        lines.append(
            f"| {i} | {r.source} | {r.item_id} | {r.object_name} | "
            f"{'OK' if r.fetch_ok else 'FAIL'} | {r.fetch_format} | {size} | {real} | "
            f"{r.fetch_latency_s}s | {err[:80]} |"
        )
    return "\n".join(lines)


async def probe_one(
    source: DataSource,
    query: str,
    mock_item_id: str,
    notes: str,
) -> ProbeResult:
    """探测单个 Adapter。"""
    result = ProbeResult(
        source=source.value,
        adapter_class="",
        construct_ok=False,
        notes=notes,
    )

    # 1. 构造
    t0 = time.time()
    try:
        adapter = get_adapter(source)
        result.adapter_class = type(adapter).__name__
        result.construct_ok = True
    except Exception as e:
        result.adapter_class = source.value
        result.construct_error = f"{type(e).__name__}: {e}"
        return result

    # 2. search
    if source == DataSource.IEEE:
        result.search_error = "跳过（IEEE_API_KEY 未配置）"
        result.notes = "P2 优先级；待申请 Key 后单独验证"
        return result

    t0 = time.time()
    try:
        results = await asyncio.wait_for(adapter.search(query), timeout=SEARCH_TIMEOUT_S)
        result.search_ok = True
        result.search_latency_s = round(time.time() - t0, 2)
        result.search_results_count = len(results)
        if results:
            result.search_first_item_id = results[0].item_id
    except TimeoutError:
        result.search_error = f"超时（>{SEARCH_TIMEOUT_S}s）"
        result.search_latency_s = round(time.time() - t0, 2)
    except AdapterError as e:
        result.search_error = f"AdapterError: {e.message[:200]}"
        result.search_latency_s = round(time.time() - t0, 2)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        # aiohttp.ClientResponseError 等带 status 属性
        status = getattr(e, "status", None) or getattr(
            getattr(e, "args", [None])[0], "status", None
        )
        if status:
            msg += f" [HTTP {status}]"
        result.search_error = msg[:300]
        result.search_latency_s = round(time.time() - t0, 2)

    # 3. fetch
    # 优先用 search 返回的首条 ID，否则用 mock_item_id
    fetch_id = result.search_first_item_id or mock_item_id
    if fetch_id == "search_first":
        # 仅在 search 成功时才能 fetch；search 失败时跳过
        if not result.search_ok:
            result.fetch_error = "search 失败，无法获取真实 item_id"
            return result
        # 此时 fetch_id 已被 result.search_first_item_id 覆盖
        fetch_id = result.search_first_item_id

    if not fetch_id:
        result.fetch_error = "无可用 item_id（mock 也未配置）"
        return result

    result.fetch_item_id_used = fetch_id
    t0 = time.time()
    try:
        raw = await asyncio.wait_for(adapter.fetch(fetch_id), timeout=FETCH_TIMEOUT_S)
        result.fetch_ok = True
        result.fetch_latency_s = round(time.time() - t0, 2)
        result.fetch_size_bytes = raw.size_bytes
        result.fetch_format = raw.format
        result.fetch_url = raw.url
    except TimeoutError:
        result.fetch_error = f"超时（>{FETCH_TIMEOUT_S}s）"
        result.fetch_latency_s = round(time.time() - t0, 2)
    except AdapterError as e:
        result.fetch_error = f"AdapterError: {e.message[:200]}"
        result.fetch_latency_s = round(time.time() - t0, 2)
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        status = getattr(e, "status", None)
        if status:
            msg += f" [HTTP {status}]"
        result.fetch_error = msg[:300]
        result.fetch_latency_s = round(time.time() - t0, 2)

    return result


def format_table(results: list[ProbeResult]) -> str:
    """生成 Markdown 表格。"""
    lines = [
        "| # | Adapter | 构造 | search | search延迟 | 结果数 | fetch | fetch延迟 | 大小 | 错误/备注 |",
        "|---|---------|------|--------|-----------|--------|-------|----------|------|----------|",
    ]
    for i, r in enumerate(results, 1):
        construct = "OK" if r.construct_ok else f"FAIL: {r.construct_error[:30]}"
        search = "OK" if r.search_ok else "FAIL"
        fetch = "OK" if r.fetch_ok else "FAIL"
        err_parts = []
        if r.search_error:
            err_parts.append(f"search: {r.search_error[:80]}")
        if r.fetch_error:
            err_parts.append(f"fetch: {r.fetch_error[:80]}")
        if not err_parts and r.notes:
            err_parts.append(r.notes[:80])
        err_str = " / ".join(err_parts) if err_parts else "—"
        size = f"{r.fetch_size_bytes}B" if r.fetch_ok else "—"
        lines.append(
            f"| {i} | {r.adapter_class} | {construct} | {search} | "
            f"{r.search_latency_s}s | {r.search_results_count} | {fetch} | "
            f"{r.fetch_latency_s}s | {size} | {err_str} |"
        )
    return "\n".join(lines)


async def main() -> None:
    print(f"[probe] 开始探活 {len(PROBE_CASES)} 个 Adapter...")
    print(f"[probe] SEARCH_TIMEOUT={SEARCH_TIMEOUT_S}s, FETCH_TIMEOUT={FETCH_TIMEOUT_S}s")
    print("=" * 80)

    results: list[ProbeResult] = []
    for source, query, mock_id, notes in PROBE_CASES:
        print(f"\n>>> {source.value} ({notes})")
        r = await probe_one(source, query, mock_id, notes)
        results.append(r)
        # 实时打印
        print(f"  construct: {'OK' if r.construct_ok else 'FAIL'}")
        print(
            f"  search: {'OK' if r.search_ok else 'FAIL'} "
            f"({r.search_latency_s}s, {r.search_results_count} results) "
            f"err={r.search_error or '—'}"
        )
        print(
            f"  fetch: {'OK' if r.fetch_ok else 'FAIL'} "
            f"({r.fetch_latency_s}s, {r.fetch_size_bytes}B) "
            f"id={r.fetch_item_id_used} err={r.fetch_error or '—'}"
        )

    print("\n" + "=" * 80)
    print("[probe] 全部完成。汇总表：\n")
    print(format_table(results))

    # ── GRASP 专项探测（第三次联调新增） ──
    print("\n" + "=" * 80)
    print(f"[probe] GRASP 专项探测 {len(GRASP_PROBE_CASES)} 个源（req_type=GRASP）...")
    grasp_results: list[GraspProbeResult] = []
    for source, query, mock_id, object_name in GRASP_PROBE_CASES:
        print(f"\n>>> {source.value} (GRASP, object={object_name or 'N/A'})")
        r = await probe_grasp(source, query, mock_id, object_name)
        grasp_results.append(r)
        print(
            f"  fetch: {'OK' if r.fetch_ok else 'FAIL'} "
            f"({r.fetch_latency_s}s, {r.fetch_size_bytes}B, format={r.fetch_format}) "
            f"id={r.item_id} real_grasp={'是' if r.is_real_grasp else '否'} "
            f"err={r.fetch_error or r.notes or '—'}"
        )
    real_count = sum(1 for r in grasp_results if r.is_real_grasp)
    print("\n[probe] GRASP 探测汇总：\n")
    print(format_grasp_table(grasp_results))
    print(f"\n[probe] 真实 grasp 文件源数量: {real_count}/{len(grasp_results)}")

    # 写 JSON 证据文件
    out_path = "data/probe_adapters_results.json"
    os.makedirs("data", exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "probe_results": [asdict(r) for r in results],
                "grasp_probe_results": [asdict(r) for r in grasp_results],
                "real_grasp_count": real_count,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )
    print(f"\n[probe] JSON 证据已写入: {out_path}")


if __name__ == "__main__":
    asyncio.run(main())
