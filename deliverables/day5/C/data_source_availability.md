# 数据类源可用性汇总（Day5 C，Day3 口径）

> 角色：C｜日期：2026-08-15
> 口径：**Day3 口径**——C 数据源类 = 7 类需求类型（paper/code/dataset/grasp/sim_config/policy/sensor）对应的全部源，共 **11 源**：arxiv / github / huggingface / zenodo / paperswithcode / graspnet / dexgrasp / ieee / ycb / mujoco / isaac
> 依据：探活重跑（`data/probe_adapters_results.json`，2026-08-15）+ `records/` 62 case 执行观察（retrieve 命中源/质量/降级标记）
> 说明：本材料为 Day5 C 清尾交付，供 Day6 统计与 Day8 验收引用；按 Day3 口径将 mujoco/isaac（SIM_CONFIG 类源）计入 C 汇总。D 的格式/仿真类剩余源（franka/robotiq/allegro/google_scanned）不在本材料范围。

## 一、汇总矩阵（11 源 × 构造/检索/下载 × 通过/失败/跳过）

| # | 源 | 构造 | 检索 | 下载 | 探活证据（fetch） | 结论 |
|---|---|---|---|---|---|---|
| 1 | arxiv | ✅ 通过 | ✅ 通过 | ✅ 通过 | 2.89s / json / 6.0MB | 可用（无 Key） |
| 2 | github | ✅ 通过 | ✅ 通过 | ✅ 通过 | 1.12s / markdown / 14KB | 可用（可选 token） |
| 3 | huggingface | ✅ 通过 | ✅ 通过 | ✅ 通过 | 2.61s / json / 1.8KB | 可用（镜像 hf-mirror） |
| 4 | zenodo | ✅ 通过 | ✅ 通过 | ✅ 通过 | 1.31s / json / 5.2KB | 可用（无 Key） |
| 5 | paperswithcode | ✅ 通过 | ✅ 通过 | ✅ 通过 | 11.04s / json / 502B | 可用（search 慢 12s） |
| 6 | graspnet | ✅ 通过 | ✅ 通过 | ⚠️ 降级 | 2.11s / json / 455B | 降级可用（元数据） |
| 7 | dexgrasp | ✅ 通过 | ✅ 通过 | ✅ 通过 | 0.97s / json / 455B | 可用（GRASP 真实 npy 可达） |
| 8 | ieee | ✅ 通过 | ⛔ 跳过 | ⛔ 跳过 | 无 Key | blocked-by-user（P7_ENV） |
| 9 | ycb | ✅ 通过 | ✅ 通过 | ✅ 通过 | 2.22s / obj / 1.4MB | 可用（mesh real） |
| 10 | mujoco | ✅ 通过 | ✅ 通过 | ✅ 通过 | 20.73s / xml / 19KB | 可用（menagerie 真实场景） |
| 11 | isaac | ✅ 通过 | ✅ 通过 | ⚠️ 降级 | 1.14s / python / 5.2KB | 降级可用（最小 MJCF） |

> 构造/检索/下载三态口径：通过 = 探活 OK 且执行观察有成功命中；跳过 = 因环境缺失（无 API Key）主动跳过；降级 = 命中但仅元数据/结构化表示/最小配置，非原始数据文件。

## 二、records/ 执行观察（62 case 中 11 源命中明细）

| 源 | 命中条数 | fallback | real | 命中需求类型 | 产出格式 |
|---|---|---|---|---|---|
| arxiv | 10 | 10 | 0 | paper / dataset | json（metadata 降级）|
| github | 14 | 13 | 1 | code / robot_urdf / policy_model / sensor_data / sim_config | urdf / markdown / json / mjcf |
| huggingface | 12 | 12 | 0 | grasp / dataset / policy_model | CanonicalGrasp / json / markdown |
| zenodo | 8 | 8 | 0 | dataset / sensor_data | json（metadata 降级）|
| paperswithcode | 0 | — | — | — | records 中无直接命中（经 arxiv 兜底）|
| graspnet | 5 | 5 | 0 | grasp | CanonicalGrasp / json |
| dexgrasp | 0 | — | — | — | records 中无直接命中（经 huggingface 兜底）|
| ieee | 0 | — | — | — | records 中无直接命中（经 arxiv 兜底，blocked）|
| ycb | 6 | 4 | 2 | mesh | obj / stl |
| mujoco | 6 | 0 | 6 | sim_config | xml（真实场景，全部 real）|
| isaac | 2 | 2 | 0 | sim_config | mjcf（最小 MJCF 降级）|

> 说明：paperswithcode / dexgrasp / ieee 三源在 records/ 的 retrieve 中**未作为命中源记录**——实际执行时由兜底源命中（paperswithcode→arxiv、dexgrasp→huggingface、ieee→arxiv）。探活显示三源构造/检索可用（ieee 检索因无 Key 跳过），执行观察按命中源归因。**real 列口径：按 `is_fallback=False`（非降级命中）统计**，与 quality=real 不同——如 ms_003 的 isaac、ss_graspnet_001 的 huggingface 虽 quality=real 但 is_fallback=True，归入 fallback。mujoco 命中 6 条全部非降级（menagerie 场景 XML），是数据类源中 real 命中率最高的源。kinova（ms_003 命中 1 条 fallback）属 D 格式/仿真类源（robot_urdf 类），不在本表范围。

## 三、GRASP 专项（探活）

| 源 | 物体 | fetch | 格式 | 大小 | 真实 grasp | 结论 |
|---|---|---|---|---|---|---|
| dexgrasp | banana | OK 3.13s | npy | 174KB | ✅ 是 | 真实抓取文件可达 |
| graspnet | banana | OK 2.58s | json | 567B | ❌ 否 | 元数据/降级（tar 死路径）|
| ycb | banana | OK 10.81s | obj | 1.4MB | ❌ 否 | 元数据/降级（非 grasp 格式）|

> 真实 grasp 源 1/3（dexgrasp）；graspnet/ycb 需显式降级（对应 PASS_WITH_FALLBACK 判定）。

## 四、每源可用性结论（11 源）

| 源 | 可用性等级 | 可命中需求类型 | 质量档 | 降级/兜底路径 | 遗留问题 |
|---|---|---|---|---|---|
| arxiv | ✅ 可用 | PAPER / DATASET | fallback | PDF 超阈值 → metadata JSON | 大 PDF 下载慢 |
| github | ✅ 可用 | CODE / ROBOT_URDF / POLICY_MODEL / SENSOR_DATA / SIM_CONFIG | fallback 为主（real 仅 ss_github_001） | 非 .urdf → git/trees 定位；README 兜底 | 无 token 限流风险 |
| huggingface | ✅ 可用 | GRASP / DATASET / POLICY_MODEL | fallback（无 real 命中） | model_info 404 → config → metadata | 单仓库大文件下载 |
| zenodo | ✅ 可用 | DATASET / SENSOR_DATA | fallback | 非时序数据 → 元数据降级 | 记录粒度差异 |
| paperswithcode | ✅ 可用（探活） | PAPER / CODE | fallback | OpenAlex 接口 | search 慢（12s）；执行多经 arxiv 兜底 |
| graspnet | ⚠️ 降级可用 | GRASP / DATASET | fallback | tar 死路径 → 元数据 | 需真实数据目录 |
| dexgrasp | ✅ 可用 | GRASP | real | 元数据降级（部分物体） | 物体覆盖有限 |
| ieee | ⛔ blocked | PAPER | — | arxiv 兜底 | 无 API Key（P7_ENV）|
| ycb | ✅ 可用 | MESH / GRASP / DATASET | real / fallback | grasp 非格式 → 元数据 | 需真实 grasp 数据 |
| mujoco | ✅ 可用 | SIM_CONFIG | real | menagerie 真实场景（xml） | 大场景 fetch 慢（20.7s）|
| isaac | ⚠️ 降级可用 | SIM_CONFIG | fallback | 最小 MJCF | 无真实 Isaac 资产 |

## 五、遗留问题与建议（提交 A/F）

1. **ieee**：无 API Key，blocked-by-user（P7_ENV）；实际经 arxiv 兜底转 PASS_WITH_FALLBACK，如实记录。
2. **graspnet / ycb（GRASP）**：无真实 grasp 文件（graspnet json 元数据 / ycb obj 非 grasp 格式），仅 dexgrasp 可出真实 npy；建议补本地数据集目录或接受降级口径。
3. **paperswithcode / dexgrasp**：records/ 中无直接命中记录（分别经 arxiv / huggingface 兜底），建议核对 retriever 候选源优先级与注入逻辑，确认是否为执行期随机性。
4. **huggingface**：12 条命中全部 `is_fallback=True`，无 real 命中。其中 ss_graspnet_001 的 dataset 条目 quality=real 但 is_fallback=True（status=error），quality 与降级标记口径需统一。
5. **isaac**：无真实 Isaac Sim 资产，仅最小 MJCF fallback；2 条命中全部 `is_fallback=True`（ms_003、ms_006），其中 ms_003 的 quality=real 但实际为降级命中，已复核标记为 fallback。
