# Day 6｜F 汇总统计、复盘归因与交付收尾

> 统计快照：`2026-08-19T15:11:12+08:00`
>
> 权威来源：`records/_management/quality_report.json`（`strict_mode=true`）、`records/_management/progress.csv`、63 个 `records/<case_id>/record.json`。
>
> 本文件执行 Day6 计划中 F 的统计、质量核查、归因汇总和交付核对；Day7/Day8 已按 `Day6_汇总统计.md` 压缩合并，不再另建正式的 day7/day8 结论。

## 1. 结论先行

- 问题集共 **63 题**：55 道单源题、8 道多源题，P0 共 11 道。
- 63/63 已执行、已判定、已复核；全部记录由 A 完成最终复核。
- 判定为 PASS 14、PASS_WITH_FALLBACK 48、FAIL 1；可用包为 62/63，整体可用率 **98.41%**。
- P0 可用 11/11，超过验收线 8/11；记录完整率、截图合规率均 100%，记录校验 ERROR 为 0。
- 唯一 FAIL 是 `ms_008` 的 **P2_RETRIEVE**。正式记录已经过 3 轮真实前端检索、5 张截图取证，并由 A 于 2026-08-18 21:36 复核。

## 2. 统计口径

1. PASS 率、降级率、失败率的分母是全部已判定 case（63）。
2. 可用率按 `(PASS + PASS_WITH_FALLBACK) / 总题数` 计算；显式降级包算可用，静默降级才算 FAIL。
3. 语言、source、req_type 是按问题集题设维度分组。多源 case 会在每个题设 source/req_type 组中重复计数，分组计数不能相加回 63。
4. C 的 11 源执行观察表是实际 `observations.retrieve[]` 命中统计，和本文件的题设 source 维度不是同一个分母，详见 [C 定稿](../C/data_source_availability.md)。
5. 降级判定以 `verdict` 和记录中的 `is_fallback`/`fallback_reason`/`fallback_explicit` 为准；`quality=real` 在少数源偏移记录中与 `is_fallback=true` 并存，不能单独作为判定依据。

## 3. 总体指标

| 指标 | 结果 |
|---|---:|
| 问题集总数 | 63 |
| 单源 / 多源 | 55 / 8 |
| P0 题数 | 11 |
| 已执行 / 已判定 / 已复核 | 63 / 63 / 63 |
| PASS | 14（22.22%） |
| PASS_WITH_FALLBACK | 48（76.19%） |
| FAIL | 1（1.59%） |
| 可用包（PASS + PWF） | 62/63（98.41%） |
| 记录平均完整率 | 100.0% |
| 记录完整率 ≥90% | 63/63（100.0%） |
| 截图合规率 | 63/63（100.0%） |
| 截图引用 / 实际图片 | 489 / 489 |
| 记录校验 ERROR | 0 |
| P0 可用数据包 | 11/11（目标至少 8/11） |

截图分布为 8 张 × 59 个 case、4 张 × 3 个 case（`ss_robotiq_003`、`ms_006`、`ms_007`）、5 张 × 1 个 case（`ms_008`）。FAIL case 额外包含 `05_error.png`。

## 4. 分维度统计

### 4.1 按语言

| 语言 | case 数 | PASS | PWF | FAIL | 可用率 |
|---|---:|---:|---:|---:|---:|
| EN | 29 | 1 | 27 | 1 | 96.55% |
| ZH | 34 | 13 | 21 | 0 | 100.00% |
| MIX | 0 | 0 | 0 | 0 | N/A（题库无 MIX） |

### 4.2 按题设 source

| source | case 数 | PASS | PWF | FAIL | 可用率 |
|---|---:|---:|---:|---:|---:|
| allegro | 3 | 3 | 0 | 0 | 100.00% |
| arxiv | 5 | 0 | 5 | 0 | 100.00% |
| dexgrasp | 6 | 0 | 6 | 0 | 100.00% |
| franka | 8 | 3 | 4 | 1 | 87.50% |
| github | 8 | 1 | 6 | 1 | 87.50% |
| google_scanned | 3 | 0 | 3 | 0 | 100.00% |
| graspnet | 3 | 0 | 3 | 0 | 100.00% |
| huggingface | 5 | 0 | 5 | 0 | 100.00% |
| ieee | 1 | 0 | 1 | 0 | 100.00% |
| isaac | 3 | 0 | 3 | 0 | 100.00% |
| mujoco | 9 | 3 | 5 | 1 | 88.89% |
| paperswithcode | 3 | 0 | 3 | 0 | 100.00% |
| robotiq | 4 | 3 | 1 | 0 | 100.00% |
| ycb | 11 | 1 | 10 | 0 | 100.00% |
| zenodo | 5 | 0 | 5 | 0 | 100.00% |

低于 100% 的题设 source 只有 `franka`、`github`、`mujoco`，三者的失败均由 `ms_008` 的多源题覆盖造成；这不等同于这些 Adapter 的单源可用性失败。

### 4.3 按需求类型

| req_type | case 数 | PASS | PWF | FAIL | 可用率 |
|---|---:|---:|---:|---:|---:|
| code | 3 | 1 | 2 | 0 | 100.00% |
| dataset | 7 | 0 | 7 | 0 | 100.00% |
| grasp | 13 | 0 | 13 | 0 | 100.00% |
| mesh | 13 | 1 | 12 | 0 | 100.00% |
| paper | 9 | 0 | 9 | 0 | 100.00% |
| policy_model | 3 | 0 | 3 | 0 | 100.00% |
| robot_urdf | 17 | 9 | 7 | 1 | 94.12% |
| sensor_data | 3 | 0 | 3 | 0 | 100.00% |
| sim_config | 11 | 3 | 8 | 0 | 100.00% |

`robot_urdf` 是唯一未达到 100% 可用率的需求类型，唯一失败仍为 `ms_008`。

### 4.4 按 LLM 模型

| 模型 | case 数 | 占比 | 备注 |
|---|---:|---:|---|
| qwen-plus | 61 | 96.8% | 覆盖全部单源题和 6 道多源题 |
| qwen3.7-plus | 2 | 3.2% | 仅 `ms_001` / `ms_002`，样本量不均，不做效果比较 |

## 5. 失败 TOP3 与 case 归因

当前 FAIL 只有 1 条，因此 TOP3 如实只有 TOP1，不能补造不存在的 P3/P4/P5 失败。

| 排名 | 分类码 | 数量 | 占 FAIL | 占全库 | case |
|---:|---|---:|---:|---:|---|
| 1 | P2_RETRIEVE | 1 | 100.00% | 1.59% | `ms_008` |

### `ms_008` 最终归因

- 输入：`只要 Franka Panda 的 URDF`；执行人：`F+A`；模型：`qwen-plus`。
- `parse_goal` 正确识别了 `robot_urdf`，但 LLM 将候选 fallback 源选成 `allegro` / `robotiq` / `kinova`，没有遵守题设的 `franka` / `mujoco` / `github` 约束。
- 3 轮检索均为 `missing`：这些源有 Adapter，但目录中没有 Franka Panda URDF；校验报 1 个错误，最终包 `failed` 且 0 文件。
- 真实前端流程走完 human_review 并保留 5 张截图，FAIL 分类为 P2_RETRIEVE；A 已复核。相同输入的脚本探针曾通过 GitHub 兜底，但不能覆盖真实前端失败结论。
- 定性：目标解析的候选源约束不足和 LLM 随机性共同导致的检索失败，不是 C 汇总中的源可用性 FAIL，也不是旧记录中的 P7_ENV。

## 6. PASS_WITH_FALLBACK 归因汇总

48 条 PWF 均有显式降级证据；F 对 63 条原始记录逐条检查，未发现“PWF 但没有 fallback 证据”的记录。领域定稿材料提供了以下根因分组：

| 领域 | 主要根因 | 代表 case / 证据 | 后续方向 |
|---|---|---|---|
| C：数据源 | GraspNet 大 tar 无单文件、DexGrasp 物体覆盖有限、HuggingFace 只能拿 metadata、Isaac 无真实资产、IEEE 无 Key 后走 arXiv 兜底 | `ss_graspnet_002`、`ss_dexgrasp_002/005`、`ms_003`、`ss_ieee_001`；见 [C P2/P3 归因](../C/P2P3归因清单.md) | 本地数据挂载、真实直链、候选源优先级和相关性治理 |
| D：格式/运行时 | 历史 xacro、mesh 跟随抓取、资源引用和场景扩展问题已修复；残余是 `ms_003` 的 grasp 只有元数据 | 13 个清尾包 + `ms_005` 加载验证全通过；见 [D 可加载性结论](../../day5/D/可加载性验证结论.md) | 真实 NPZ/姿态样本和跨包加载回归 |
| E：流程/环境 | 未观察到当前 P6_FRONTEND FAIL；全部记录使用真实流程，模型以 qwen-plus 为主 | [E 环境汇总](../../day5/E/环境信息汇总.md) | 增加同输入重复运行和 interrupt/resume 回归 |

## 7. 记录质量问题

质量报告共 52 条 WARNING，全部为已知放行项；记录校验 ERROR 为 0。

| 类型 | 数量 | 处理结论 |
|---|---:|---|
| `package.dir` / `manifest_path` 跨机器绝对路径 | 28 | 数据包被各执行机本地化且不入库；不阻断本次记录验收，但下一轮应改为相对路径或可复核归档引用 |
| 显式格式降级 | 11 | 已写明 fallback 原因并由纪要 §2.4 放行 |
| 显式质量降级 | 7 | 已写明 fallback 原因；下一轮统一 `quality` 与 `is_fallback` 定义 |
| 题设外补充需求 | 6 | 属于多需求解析的补充项，记录为 WARNING，不影响核心需求判定 |
| 记录校验 ERROR | 0 | 无需阻断交付 |

其他审计注意事项：

- `problem_set` 校验另有 1 条 WARNING：代码注册了 `kinova`，正式题库没有对应题目；这不是记录错误，但下一轮应补题或明确覆盖边界。
- `assignments.csv` 原计划由 F 复核 62 条、A 复核 `ms_008`；实际为 A 统一复核 63 条。记录中的 `reviewer=A`、`reviewed_at` 已齐全，应在项目审计中视为 A 授权覆盖，并同步任务分配语义。
- 题库的 63 题、55/8、11 个 P0 是当前正式口径；早期的 65 题/57 单源和 Day5 旧快照不再作为统计来源。

## 8. P0/P1/P2 改进建议

完整清单见 [改进建议清单.md](改进建议清单.md)。当前 F 提交的是复盘初稿，优先级需由 A 在复盘会上最终裁定。

| 优先级 | 目标模块 | 建议 |
|---|---|---|
| P0 | `parse_goal` node / prompt | 为厂商 `robot_urdf` 增加确定性候选源规则（Franka 至少 `franka → github`），将题设 source 注入约束，并增加 `ms_008` 同输入回归测试 |
| P1 | `adapters/registry.py`、`retrieve_data` node | 固化候选源优先级与 provenance；修正 Zenodo 相关性、PapersWithCode/DexGrasp 兜底偏移，避免“有源但未收录”被错误选中 |
| P1 | Adapter / settings | GraspNet 本地解压或小样本入口、HuggingFace 真实直链、DexGrasp 物体覆盖、MuJoCo 按源自适应 timeout、IEEE Key 状态显式化 |
| P1 | `skills/registry.py`、manifest | 统一 `data_source_quality`、`is_fallback`、`fallback_reason` 和包级 `fallback_explicit` 的语义，补充源偏移回归校验 |
| P1 | `assemble` / package manifest | 将跨机绝对路径替换为相对路径或内容哈希引用，并提供包证据归档方式 |
| P2 | records/schema 与文档 | 清理历史 Day8 命名、补 reviewer 授权字段、把题设 source 维度与实际 retrieve 维度分开展示 |
| P2 | 下一轮问题集 | 增加同输入多次运行、真实 GraspNet NPZ、DexGrasp 未覆盖物体、源偏移和大型 MJCF 资产等边界题 |

## 9. 交付与验收

- [x] `problem_set/problem_set.json` 存在，63 个 `case_id` 唯一，问题集/分配校验无 ERROR。
- [x] `records/` 有 63 个正式 case，每个都有 `record.json`；截图引用与实际图片 489/489 匹配。
- [x] 全部 63 条已执行、已判定、已复核；FAIL 有报错证据。
- [x] P0 可用 11/11，记录完整率和截图合规率 100%，校验 ERROR 0。
- [x] `_management/progress.csv`、`quality_report.json`、`statistics_summary.md` 已按 2026-08-19 严格快照刷新。
- [x] C/D/E 定稿材料已纳入本报告引用；F 的原始 case 明细见 [case_statistics.csv](case_statistics.csv)。
- [ ] A 对本报告的改进优先级和冻结后变更完成最终签字（交付前最后人工动作）。

推荐复核命令（Windows）：

```powershell
.\.venv\Scripts\python.exe scripts\manage_test_records.py validate-problems
.\.venv\Scripts\python.exe scripts\manage_test_records.py validate-records
.\.venv\Scripts\python.exe scripts\manage_test_records.py all --strict
```

`uv run` 在本机因 uv cache 目录权限/已存在冲突无法初始化，因此本次验证使用仓库 `.venv`；脚本本身的校验结果为问题集 1 条 WARNING、记录 52 条 WARNING、0 ERROR，严格验收项全部通过。

## 10. 旧快照更正

`deliverables/day6/F/day6_statistics.md` 原版本（2026-08-18 14:52）和 `deliverables/day5/F/day5_freeze_report.md`、`deliverables/day5/E/环境信息汇总.md` 中的 `ms_008=P7_ENV`、未复核、3 张截图叙述已经过期。2026-08-18 21:36 的提交 `641f4c6` 用真实前端 3 轮检索结果替换了旧记录，正式结论为 `FAIL/P2_RETRIEVE`、5 张截图、A 已复核；本文件及 2026-08-19 严格统计均以新记录为准。
