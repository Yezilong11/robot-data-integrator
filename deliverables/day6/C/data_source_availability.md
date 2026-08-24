# 数据源可用性汇总表（Day6 C 定稿）

> 角色：C（数据工程师）｜定稿日期：2026-08-19
> 状态：**定稿**（由 `deliverables/day5/C/data_source_availability.md` 迭代；供 F 统计与 A 终审引用）
> 口径：**Day3 口径**——C 数据源类 = 7 类需求类型（paper/code/dataset/grasp/sim_config/policy_model/sensor_data）对应的全部源，共 **11 源**：arxiv / github / huggingface / zenodo / paperswithcode / graspnet / dexgrasp / ieee / ycb / mujoco / isaac
> 依据：① 探活：`data/probe_adapters_results.json`（2026-08-15 重跑），基线 `records/_probe/probe_20260812.json`（2026-08-12）；② 执行观察：**冻结 `records/` 63 case**（2026-08-18 A 复核后，`_management/quality_report.json` 快照 21:36）
> 说明：D 的格式/仿真类源（franka/robotiq/allegro/google_scanned/kinova）不在本表范围；mujoco/isaac 按 Day3 口径计入 C（SIM_CONFIG 类源）。

## 〇、核对说明（统计数字与记录一致）

执行观察计数已用脚本对冻结 63 个 `records/<case_id>/record.json` 的 `observations.retrieve[]` 逐条程序化核对。核对口径：

- **命中** = 该源的 retrieve 条目 `status ∈ {success, error}` 且可追溯（success 为正常命中；error 条目均带 `fallback_reason`/`is_fallback=true`，属显式降级命中）；
- **real/fallback** 按 `is_fallback` 统计（`is_fallback=false` → real；`true` → fallback）；
- **ms_008**（FAIL/P2_RETRIEVE）仅贡献 3 条 `status=missing`（allegro/robotiq/kinova，有源但未收录 Franka Panda），**无新增命中**。

核对结果：下表"二、执行观察"各源计数与冻结记录完全一致，与 day5 版（62 case）无出入。

---

## 一、汇总矩阵（11 源 × 构造/检索/下载 × 通过/失败/跳过）

| # | 源 | 构造 | 检索 | 下载 | 探活证据（fetch，08-15 重跑） | 结论 |
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
> 与 08-12 基线对比：8 源 fetch 代码缺陷（dexgrasp/graspnet/ycb/franka/allegro/robotiq/mujoco/isaac）与 HF 单仓库 404 均已修复；**当前唯一 fetch 阻塞源为 ieee（无 API Key，blocked-by-user）**。

## 二、records/ 执行观察（冻结 63 case 中 11 源命中明细，程序化核对一致）

| 源 | 命中条数 | fallback | real | 命中需求类型 | 产出格式 |
|---|---|---|---|---|---|
| arxiv | 10 | 10 | 0 | paper / dataset | json（metadata 降级）|
| github | 14 | 13 | 1 | code / robot_urdf / policy_model / sensor_data / sim_config | urdf / markdown / json / mjcf |
| huggingface | 12 | 12 | 0 | grasp / dataset / policy_model | CanonicalGrasp / json / markdown |
| zenodo | 8 | 8 | 0 | dataset / sensor_data | json（metadata 降级）|
| paperswithcode | 0 | — | — | — | 无直接命中（经 arxiv 兜底）|
| graspnet | 5 | 5 | 0 | grasp | CanonicalGrasp / json |
| dexgrasp | 0 | — | — | — | 无直接命中（经 huggingface 兜底）|
| ieee | 0 | — | — | — | 无直接命中（经 arxiv 兜底，blocked）|
| ycb | 6 | 4 | 2 | mesh | obj / stl |
| mujoco | 6 | 0 | 6 | sim_config | xml（真实场景，全部 real）|
| isaac | 2 | 2 | 0 | sim_config | mjcf（最小 MJCF 降级）|

> 口径说明：paperswithcode / dexgrasp / ieee 三源在 records/ 的 retrieve 中**未作为命中源记录**——实际执行由兜底源命中（paperswithcode→arxiv、dexgrasp→huggingface、ieee→arxiv）。**real 列按 `is_fallback=false` 统计**，与 quality=real 不同——如 ss_graspnet_001 的 huggingface 条目虽 quality=real 但 is_fallback=True（源偏移兜底），归入 fallback。mujoco 命中 6 条全部非降级（menagerie 场景 XML），是数据类源中 real 命中率最高的源。kinova（ms_003 命中 1 条）属 D 格式/仿真类源，不在本表范围；ms_008 的 3 条 missing 属 D 类源白名单覆盖率限制，无命中。

## 三、GRASP 专项（探活）

| 源 | 物体 | fetch | 格式 | 大小 | 真实 grasp | 结论 |
|---|---|---|---|---|---|---|
| dexgrasp | banana | OK 3.13s | npy | 174KB | ✅ 是 | 真实抓取文件可达 |
| graspnet | banana | OK 2.58s | json | 567B | ❌ 否 | 元数据/降级（tar 死路径）|
| ycb | banana | OK 10.81s | obj | 1.4MB | ❌ 否 | 元数据/降级（非 grasp 格式）|

> 真实 grasp 源 1/3（dexgrasp）；graspnet/ycb 需显式降级（对应 PASS_WITH_FALLBACK 判定，与冻结记录一致：ss_graspnet_002、ss_ycb_004/005 均 PWF）。

## 四、每源可用性结论（11 源）

| 源 | 可用性等级 | 可命中需求类型 | 质量档 | 降级/兜底路径 | 遗留问题 |
|---|---|---|---|---|---|
| arxiv | ✅ 可用 | PAPER / DATASET | fallback | PDF 超阈值 → metadata JSON | 大 PDF 下载慢 |
| github | ✅ 可用 | CODE / ROBOT_URDF / POLICY_MODEL / SENSOR_DATA / SIM_CONFIG | fallback 为主（real 仅 ss_github_001） | 非 .urdf → git/trees 定位；README 兜底 | 无 token 限流风险 |
| huggingface | ✅ 可用 | GRASP / DATASET / POLICY_MODEL | fallback（无 real 命中） | model_info 404 → config → metadata | 单仓库大文件下载 |
| zenodo | ✅ 可用 | DATASET / SENSOR_DATA | fallback | 非时序数据 → 元数据降级 | 记录粒度差异 |
| paperswithcode | ✅ 可用（探活） | PAPER / CODE | fallback | OpenAlex 接口 | search 慢（12s）；执行多经 arxiv 兜底 |
| graspnet | ⚠️ 降级可用 | GRASP / DATASET | fallback | tar 死路径 → 元数据 | 需真实数据目录 |
| dexgrasp | ✅ 可用 | GRASP | real | 元数据降级（部分物体） | 物体覆盖有限（6 物体）|
| ieee | ⛔ blocked | PAPER | — | arxiv 兜底 | 无 API Key（P7_ENV）|
| ycb | ✅ 可用 | MESH / GRASP / DATASET | real / fallback | grasp 非格式 → 元数据 | 需真实 grasp 数据 |
| mujoco | ✅ 可用 | SIM_CONFIG | real | menagerie 真实场景（xml） | 大场景 fetch 慢（20.7s）|
| isaac | ⚠️ 降级可用 | SIM_CONFIG | fallback | 最小 MJCF | 无真实 Isaac 资产 |

## 五、遗留问题与建议（提交 A/F）

1. **ieee**：无 API Key，blocked-by-user（P7_ENV）；实际经 arxiv 兜底转 PASS_WITH_FALLBACK，如实记录（ss_ieee_001 已复核）。
2. **graspnet / ycb（GRASP）**：无真实 grasp 文件（graspnet json 元数据 / ycb obj 非 grasp 格式），仅 dexgrasp 可出真实 npy；建议补本地数据集目录或接受降级口径（R1/R2）。
3. **paperswithcode / dexgrasp**：records/ 中无直接命中记录（分别经 arxiv / huggingface 兜底），需核对 retriever 候选源优先级与注入逻辑，确认是否为执行期随机性（对应 `P2P3归因清单.md` §4）。
4. **huggingface**：12 条命中全部 `is_fallback=true`，无 real 命中。其中 ss_graspnet_001 的 dataset 条目 quality=real 但 is_fallback=True（源偏移），quality 与降级标记口径需统一（见 `验收核对_数据源类.md` §3）。
5. **isaac**：无真实 Isaac Sim 资产，仅最小 MJCF fallback；2 条命中全部 `is_fallback=true`（ms_003、ms_006），其中 ms_003 的 quality=real 但实际为降级命中（源偏移），已复核标记为 fallback。

## 六、提交说明

- 本表为 C 数据源类**定稿**，提交 F（并入统计与《改进建议清单》）、抄送 A（终审抽样比对）。
- 与 F 统计核对点：F 的 `day6_statistics.md`（14:52 快照）将 ms_008 记为 P7_ENV，但冻结记录（21:36 快照）为 **P2_RETRIEVE**，请 F 以 `records/_management/quality_report.json` 为准刷新统计叙述。
