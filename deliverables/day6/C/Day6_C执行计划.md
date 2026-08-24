# Day6 C 角色详细执行计划（数据工程师）

> 角色：C｜日期：2026-08-19
> 依据：`docs/process/Day6_汇总统计.md` §C 任务 1–4 + 与 A/F 对接点 + 当日出口标准
> 红线：不超出 Day6 文档 C 职责；`records/` 已冻结（Day5 起改动需 A 批准），C 全程只读 records，仅新增 `deliverables/day6/C/` 产物
> 最终统计口径以 `records/_management/quality_report.json`（快照 2026-08-18 21:36，A 复核后）为准

## 0. 执行前确认（前置事实）

1. **冻结记录基线**：63 case，PASS 14 / PWF 48 / FAIL 1（仅 `records/ms_008/record.json`，`P2_RETRIEVE`）。
2. **口径冲突待提示 F/A**：`deliverables/day6/F/day6_statistics.md`（14:52 快照）把 ms_008 记为 P7_ENV；但 20:00 前端真实流程重跑后 `records/_management/progress.csv` / quality_report（21:36）已更新为 **P2_RETRIEVE**（record.json 与 `docs/process/问题集执行_已知风险.md` R4 一致）。C 归因以 record.json 为准，并在复盘会提示 F 刷新统计叙述。
3. **C 数据源类 11 源**（Day3 口径，mujoco/isaac 计入 C）：arxiv / github / huggingface / zenodo / paperswithcode / graspnet / dexgrasp / ieee / ycb / mujoco / isaac；franka/robotiq/allegro/google_scanned 属 D 格式/仿真类，不在 C 表范围。
4. **底稿**：`deliverables/day5/C/data_source_availability.md` 已是 Day3 口径近定稿，本次做"冻结记录核对 + 定稿"。

---

## 任务 1：提交《数据源可用性汇总表》定稿

**产出**：`deliverables/day6/C/data_source_availability.md`（新文件，从 day5 版迭代）

- [ ] **1.1 执行观察计数核对**：以冻结 records/（63 case）重核 day5 版"二、records/ 执行观察"表（arxiv 10 / github 14 / huggingface 12 / zenodo 8 / graspnet 5 / ycb 6 / mujoco 6 / isaac 2 / paperswithcode·dexgrasp·ieee 0）：
  - ms_008 重跑后无新增命中（3 条 retrieve 为 allegro/robotiq/kinova `status=missing`，不计数）；
  - 表头"62 case"→"63 case"，real/fallback 计数与 `is_fallback` 口径（quality=real 但 is_fallback=True 归 fallback）保持一致。
- [ ] **1.2 探活证据核对**：三态矩阵 fetch 证据（2.89s/6.0MB 等）与 `records/_probe/probe_20260812.json`、08-15 重跑记录一致即可，**不重跑探活**。
- [ ] **1.3 合并口径声明**：文首注明"探活（08-15 重跑）+ 执行观察（08-18 冻结 records/ 63 case）合并，最终以冻结记录为准"。
- [ ] **1.4 三节定稿校对**：GRASP 专项（dexgrasp 真 npy / graspnet·ycb 降级）、每源可用性结论表（11 源质量档与兜底路径）、遗留问题（day5 版 5 条）逐条复核，仅补 ms_008 相关影响说明。
- [ ] **1.5 提交**：交付 F（合并入统计）并抄送 A（供终审抽样比对）。

---

## 任务 2：数据源类 P2_RETRIEVE / P3_SOURCE 逐条归因

**产出**：`deliverables/day6/C/P2P3归因清单.md`（新文件，格式参照 `deliverables/day5/D/P4_P5失败清单.md`：case_id / 分类码 / 现象 / 根因（指向 adapter 或上游限制）/ 证据 / 状态）

每条根因必须落到**具体 adapter / node / settings 或上游限制**：

| # | case_id | 分类码 | 现状 | 根因指向 | 证据 |
|---|---|---|---|---|---|
| 1 | ms_008 | P2_RETRIEVE | **不属数据源类，C 不归因** | 根因在 `src/rdi/graph/nodes/parse_goal.py` fallback_sources 选源随机性（**目标解析域**，R4），非数据源问题；归因清单中仅作 §1 边界说明 | ms_008/record.json + `docs/process/问题集执行_已知风险.md` R4 |
| 2 | ms_005 | P2→PWF | 已解决 | franka 源检索超时（per_req 预算）+ 通用 GitHub 返回 markdown 类型错配被 C4 拦截 → `src/rdi/adapters/github.py` 缺格式预检（已修） | ms_005/record.json notes |
| 3 | ms_003 | P2→PWF | 已解决 | Kinova 无适配器 → 新增 `src/rdi/adapters/kinova.py`（已修） | ms_003/record.json notes |
| 4 | ss_huggingface_001 | P2→PWF | **残余待核** | github 首源超时→源级子预算生效；**命中源偏移**（题设 huggingface 实际命中 zenodo）+ **相关性存疑**（zenodo 返回 deepfakes 数据集）→ retriever 源优先级/注入 + zenodo 检索相关性 | ss_huggingface_001/record.json notes |
| 5 | ss_mujoco_001 | P2→PASS | 已解决 | per_req_timeout=60s 过紧（mujoco 68 mesh 资产串行 ~42s + 并行检索超预算）；180s 重跑通过 → `src/rdi/config/settings.py` 超时预算配置 vs 慢源现实 | ss_mujoco_001/record.json notes |
| 6 | ss_allegro_001~003 | P2→PASS | 已解决 | 通用 GitHubAdapter 返回 markdown 类型错配落盘 0 文件 → 专用 allegro 源命中（已修） | ss_allegro_00X/record.json notes |
| 7 | 上游限制组 | P3_SOURCE | 残余（如实记录） | graspnet tar 死路径（R1）；dexgrasp raw 兜底仅 6 物体、apple/scissors 无单文件（R2）；isaac 无真实资产仅最小 MJCF；huggingface 12 命中全 is_fallback 0 real；ieee 无 Key（P7_ENV）→ arxiv 兜底 | 问题集执行_已知风险.md R1/R2 + day5 可用性表 |
| 8 | paperswithcode / dexgrasp | — | **待核实** | records/ 中无直接命中记录（实际经 arxiv / huggingface 兜底），需核对 retriever 候选源优先级与注入逻辑是否为执行期随机性（day5 遗留问题 3） | day5 可用性表 §五 |

- [ ] **2.1** 逐条填写上表，每条给"根因定性"候选（系统缺陷 / 问题集设计不当 / 环境因素 / 数据源外部限制，供 A 复盘定性）。
- [ ] **2.2** 在 §1 边界说明中引用 ms_008 探针对照（同输入脚本直跑命中 github 兜底 PWF，package-20260818-192816），佐证根因为选源随机性（目标解析域）而非数据源问题。
- [ ] **2.3** 提交 F 并入统计与《改进建议清单》。

---

## 任务 3：复盘发言（数据源可用性趋势）

**产出**：`deliverables/day6/C/复盘发言_数据源趋势.md`（新文件，3–5 分钟口径）

- [ ] **3.1 稳定源**：11 源三态矩阵中构造/检索/下载全通过源（arxiv/github/huggingface/zenodo/dexgrasp）；mujoco 6 条命中全 real，是数据类源 real 命中率最高源。
- [ ] **3.2 需换路径源**：ieee（blocked→arxiv 兜底）、graspnet（tar 死路径→元数据降级）、isaac（→最小 MJCF）、paperswithcode（执行期实际经 arxiv）、ycb/huggingface（GRASP 非格式 / 0 real）。
- [ ] **3.3 趋势结论**：fallback 率 76.2% 构成说明（48 条 PWF 中数据类源显式降级占比）、real 命中集中分布（github/franka/mujoco/ycb）；收敛到"哪些源稳定、哪些源需换路径"→ 供 A 定性。
- [ ] **3.4 提示口径冲突**：F day6_statistics.md 的 ms_008 P7_ENV 已过期（现为 P2_RETRIEVE），请 F 同步统计叙述。

---

## 任务 4：配合 A 验收 + 认领数据源类改进建议

- [ ] **4.1 配合 A 验收数据源条目**（只读核对，不修改记录）：
  - ss_ieee_001 P7_ENV 豁免 + arxiv 兜底记录可追溯；
  - ss_huggingface_001 命中源偏移在 notes 中可追溯；
  - quality 与 is_fallback 口径一致性复核：ss_graspnet_001、ms_003/ms_006（isaac quality=real 但 is_fallback=True）按纪要 §2.1–2.3 口径核准。
- [ ] **4.2 认领数据源类改进建议**（分 P0/P1/P2、指向模块，提交 F 并入《改进建议清单》；数据源类无 P0 必改项，ms_008 教训属目标解析域、不在数据源类范围）：
  - **P1**：retriever 候选源优先级/注入逻辑核对（paperswithcode/dexgrasp 未直接命中）；zenodo 检索相关性；per_req_timeout 预算自适应（mujoco 慢源）；quality 口径定义补充；
  - **P2**：huggingface real 命中率提升（当前 0 real）；graspnet 本地数据目录挂载（R1 升级路径①）；dexgrasp 物体覆盖扩充；github 无 token 限流风险。
- [ ] **4.3 下一轮问题集建议**（数据源类边界场景升级，提交 A 汇总）：graspnet 真实 grasp 单文件题、dexgrasp 覆盖外物体题、huggingface real 直链题。
- [ ] **4.4 复盘会**：C/D/E/F 各自归因后由 A 定性并定 P0/P1/P2，F 记录存档；C 认领数据源类条目进入下一轮。

---

## 当日出口标准映射（C 相关）

- [ ] 数据源可用性表完成 → **任务 1**
- [ ] 复盘完成、C 域所有 FAIL/PWF 有根因 → **任务 2 + 3**
- [ ] 《改进建议清单》定稿素材（C 提交 P0/P1/P2，指向模块）→ **任务 4.2**
- [ ] `problem_set/` + `records/` 交付核对（C 只读配合，不新增改动）→ **任务 4.1**
- [ ] 下一轮问题集建议沉淀 → **任务 4.3**

## 自检（对照 Day6 文档逐条覆盖）

- C 任务 1/2/3/4 → 任务 1/2/3/4 ✅；对接点"C 提交领域汇总材料+根因归因→F"→ 任务 1.5/2.3 ✅；对接点"C 复盘会决议"→ 任务 3/4 ✅；Day5 衔接（records 冻结）→ 全程只读 ✅。
