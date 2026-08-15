# 数据源可用性初稿（Day4 C）

> 角色：C｜日期：2026-08-15｜依据：探活重跑（`scripts/_probe_adapters.py`，证据 `data/probe_adapters_results.json`）+ Day2/3 执行观察（47 case，含 Day3-C 43 执行单元）
> 说明：本稿为初稿，供 Day6 汇总与 Day8 验收引用；最终可用性结论由 F/A 复核。

## 一、探活汇总（2026-08-15 重跑，与 08-12 基线对比）

| # | 源 | construct | search | fetch | 基线（08-12）fetch | 本次备注 |
|---|---|---|---|---|---|---|
| 1 | arxiv | OK | OK 1.5s/10 | OK 2.9s/6.0MB | OK | XML API，无 Key |
| 2 | github | OK | OK 2.6s/21 | OK 1.1s/14KB | OK | JSON API，可选 token |
| 3 | huggingface | OK | OK 0.9s/3 | OK 2.6s/1.8KB | **FAIL(404)** | req_type 感知修复后 fetch 转 OK |
| 4 | zenodo | OK | OK 3.6s/25 | OK 1.3s/5.2KB | OK | JSON API，无 Key |
| 5 | paperswithcode | OK | OK 12.1s/10 | OK 11.0s/502B | OK | REST API |
| 6 | dexgrasp | OK | OK 0.9s/2 | OK 1.0s/455B | **FAIL(AttributeError)** | 修复后 fetch OK |
| 7 | google_scanned | OK | OK 1.7s/5 | OK 5.5s/975KB | OK | Gazebo Fuel |
| 8 | graspnet | OK | OK 1.3s/2 | OK 2.1s/455B | **FAIL(AttributeError)** | 修复后 fetch OK（元数据） |
| 9 | ycb | OK | OK 8.0s/1 | OK 2.2s/1.5MB | **FAIL(AttributeError)** | 修复后 fetch OK |
| 10 | franka | OK | OK 5.8s/2 | OK 7.9s/11KB | **FAIL(AttributeError)** | 修复后 fetch OK（panda.urdf） |
| 11 | allegro | OK | OK 7.6s/4 | OK 6.9s/16.8KB | **FAIL(AttributeError)** | 修复后 fetch OK |
| 12 | robotiq | OK | OK 2.3s/2 | OK 2.0s/267B | **FAIL(AttributeError)** | 修复后 fetch OK |
| 13 | mujoco | OK | OK 1.4s/1 | OK 20.7s/19KB | **FAIL(AttributeError)** | 修复后 fetch OK（menagerie） |
| 14 | isaac | OK | OK 6.6s/1 | OK 1.1s/5.2KB | **FAIL(AttributeError)** | 修复后 fetch OK（最小 MJCF） |
| 15 | ieee | OK | **FAIL（无 API Key）** | **FAIL** | FAIL | blocked-by-user（P7_ENV） |

> **核心结论**：8 源 fetch 代码缺陷（dexgrasp/graspnet/ycb/franka/allegro/robotiq/mujoco/isaac 缺 `local_dataset_root`/`_local_raw`）与 HF 单仓库 404 均已在 Day3 修复中解决；**当前唯一 fetch 阻塞源为 ieee（无 API Key，blocked-by-user）**。

## 二、GRASP 专项探测（req_type=GRASP）

| 源 | 物体 | fetch | 格式 | 大小 | 真实 grasp | 结论 |
|---|---|---|---|---|---|---|
| dexgrasp | banana | OK 3.1s | npy | 174KB | **是** | 真实抓取文件可达 |
| graspnet | banana | OK 2.6s | json | 567B | 否 | 元数据/降级（tar 死路径） |
| ycb | banana | OK 10.8s | obj | 1.4MB | 否 | 元数据/降级（非 grasp 格式） |

> 真实 grasp 源 1/3（dexgrasp）；graspnet/ycb 仍需显式降级（对应 Day3 PASS_WITH_FALLBACK 判定）。

## 三、执行观察（Day2/3 47 case）

| 源 | 执行 case 数 | 质量分布 | is_fallback | 命中需求类型（format 观察） |
|---|---|---|---|---|
| arxiv / arxiv.org | 12 | fallback 7 / unknown 5 | 12 | PAPER（json metadata 降级） |
| github / raw.githubusercontent | 19 | real 139 / fallback 5 / unknown 4 | 6 | CODE / ROBOT_URDF / DATASET（urdf/markdown） |
| huggingface / hf-mirror | 13 | fallback 11 / real 2 | 11 | POLICY_MODEL / DATASET / CODE（json） |
| zenodo / zenodo.org | 9 | fallback 7 / real 1 / unknown 1 | 7 | DATASET / SENSOR_DATA（json） |
| fuel | 2 | fallback 2 | 2 | MESH（obj/stl） |
| ycb | 1 | real 1 | 0 | MESH（real 命中） |

> 注：`raw.githubusercontent` 计数含多需求 case 的多文件（每文件一条 retrieve 观察），real 高发源于 github raw 直链下载成功。

## 四、每源可用性结论（15 源）

| 源 | 可用性等级 | 可命中需求类型 | 质量档 | 降级/兜底路径 | 遗留问题 |
|---|---|---|---|---|---|
| arxiv | ✅ 可用 | PAPER | real/fallback | PDF 超阈值 → metadata JSON | 大 PDF 下载慢 |
| github | ✅ 可用 | CODE/ROBOT_URDF/DATASET/POLICY/SENSOR | real/fallback | 非 .urdf → git/trees 定位；README 兜底 | 无 token 限流风险 |
| huggingface | ✅ 可用 | POLICY_MODEL/DATASET/CODE | real/fallback | model_info 404 → config → metadata | 单仓库大文件下载 |
| zenodo | ✅ 可用 | DATASET/SENSOR_DATA | real/fallback | 非时序数据 → 元数据降级 | 记录粒度差异 |
| paperswithcode | ✅ 可用 | PAPER/CODE | fallback | OpenAlex 接口 | search 慢（12s） |
| google_scanned | ✅ 可用 | MESH | real | .zip 已修 | 大物体下载超时 |
| dexgrasp | ✅ 可用 | GRASP | real | 元数据降级（部分物体） | 物体覆盖有限 |
| graspnet | ⚠️ 降级可用 | GRASP/DATASET | fallback | tar 死路径 → 元数据 | 需真实数据目录 |
| ycb | ⚠️ 降级可用 | GRASP/MESH/DATASET | real/fallback | grasp 非格式 → 元数据 | 需真实 grasp 数据 |
| franka | ✅ 可用 | ROBOT_URDF | real/fallback | — | — |
| allegro | ✅ 可用 | ROBOT_URDF | real/fallback | — | — |
| robotiq | ✅ 可用 | ROBOT_URDF | real/fallback | — | 单文件 267B 偏小 |
| mujoco | ✅ 可用 | SIM_CONFIG | real/fallback | menagerie 真实场景 | 大场景 fetch 慢（20s） |
| isaac | ⚠️ 降级可用 | SIM_CONFIG | fallback | 最小 MJCF | 无真实 Isaac 资产 |
| ieee | ⛔ blocked | PAPER | — | arxiv 兜底 | 无 API Key（P7_ENV） |

## 五、遗留问题与建议（提交 A/F）

1. **ieee**：无 API Key，blocked-by-user（P7_ENV）；实际经 arxiv 兜底转 PASS_WITH_FALLBACK，如实记录。
2. **graspnet/ycb（GRASP）**：无真实 grasp 文件（graspnet json 元数据 / ycb obj 非 grasp 格式），仅 dexgrasp 可出真实 npy；建议 Day5+ 补本地数据集目录或接受降级口径。
3. **isaac**：无真实 Isaac Sim 资产，仅最小 MJCF fallback。
4. **paperswithcode**：search 延迟偏高（12s），多需求场景注意超时预算。
5. **ms_005 观察**：franka/ycb 题设源未直接命中（github/fuel 兜底），与探活"franka fetch OK"存在差异——需核对 retriever 的源优先级与候选源注入逻辑。
