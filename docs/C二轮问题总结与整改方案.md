# C 角色二轮测试问题总结与整改方案（提交组长 B）

> 提交人：C｜时间：2026-08-21
> 范围：C 二轮 12 题摸底执行（`assignment_overview.md` C 二轮清单 + `second_round_plan.md` 口径）
> 配套：`r2_c_summary.md`（判定/统计/证据）、`records/<case_id>/`（记录+截图）、`_rerun_c_round2_progress.jsonl`
> 执行模型：qwen-plus（2026-08-21 换新 key 后服务端真实流程逐题运行；早间记录批次为 qwen-turbo，见 2.2）

---

## 1. 执行总览

| 项 | 值 |
|---|---|
| 执行题数 | 12 |
| 判定 | PASS 1 / PASS_WITH_FALLBACK 7 / FAIL 4（可用率 66.7%） |
| 记录/截图 | 12 份 record.json + 截图齐全（12 题均 5 张：01/02/03 数据包文件内容 + 04/05 前端面板） |
| 结构校验 | 12 份二轮记录 `validate-records` 0 ERROR（仅 4 条 §2.4 放行类 WARNING） |

FAIL 4 题：`ss_graspnet_004`、`ss_graspnet_005`、`ss_google_scanned_005`、`ss_zenodo_006`（均多次运行复现，非偶发）。

> 说明：本次为 2026-08-21 晚间重跑结果（服务端真实流程 + 记录与前端运行包严格对应）。相比早间记录：`ss_zenodo_006` 由 PASS 改为 FAIL（见 A4）、`ss_allegro_006` 由 PASS 改为 PWF（github 兜底）。

---

## 2. 问题清单

### A. 数据/检索类 FAIL（3 题，需组长 B 聚类修复）

**A1. ss_graspnet_004（P1_PARSE）— 核心需求解析偏移**
- 现象：题面「我要做抓取规划，帮我找 GraspNet 数据集的抓取标签」，LLM（qwen-plus/qwen-turbo）均稳定解析为 `dataset`，题设预期 `grasp`；检索仅拿到 GraspNet 说明文档（markdown），非结构化抓取标签 → 包虽 complete 但核心需求未命中，判 FAIL。
- 根因：题面同时含「数据集」（DATASET 强词）与「抓取标签」（无 GRASP 强词命中，「抓取姿态」等强词不覆盖）；归一化逻辑 `_normalize_datareq` 无法把 dataset 纠正为 grasp。
- 建议：① 组长 B 评估题面歧义（是否「抓取标签」应视为 grasp 语义）；② 或在 `parse_goal.py` 强词表为 GRASP 增加「抓取标签」「抓取规划」等词并调整优先级。

**A2. ss_graspnet_005（P3_SOURCE）— 数据集摘要 0 文件落包**
- 现象：`dataset` 需求检索成功（命中 github 源 DatasetSummary），但 Skill 未产出可落盘项 → 0 文件、包 missing，判 FAIL。qwen-plus 首跑曾 PASS（命中 graspnet 源），qwen-turbo 两轮均 FAIL（命中 github 源）——结果随候选源顺序/查询词波动。
- 根因：同一题在不同运行下命中不同候选源，github 源返回的 DatasetSummary 无法被 DatasetSkill 消费成包内文件。
- 建议：复核 graspnet 数据源可达性与 DatasetSkill 对 github 摘要的消费分支；稳定候选源排序或对不可消费格式显式降级。

**A3. ss_google_scanned_005（P3_SOURCE）— mesh 检索持续未命中**
- 现象：mesh 需求多次运行一致未命中杯 mesh（google_scanned/ycb 均未产出），包 0 文件，判 FAIL；同源 `ss_mesh_gso_001`（香蕉）经 ycb 兜底降级可用。
- 根因：google_scanned 适配器对 cup 类查询未命中真实 mesh（候选源 ycb/graspnet 又「未收录」），与香蕉的成功路径不一致。
- 建议：复核 google_scanned 对 cup 类物体的搜索/文件名匹配逻辑（对照 kettle/banana 命中路径）。

**A4. ss_zenodo_006（P4_FORMAT）— dataset 命中 markdown 格式不可消费**
- 现象：题面「帮我找 Zenodo 上机器人抓取数据集（中文描述）」，dataset 需求 8/8 次命中 github 源 README（markdown），DatasetSkill 不支持该格式 → 0 文件落包，判 FAIL。原早间 qwen-turbo 运行命中 zenodo json（record 22036612）为 PASS，换 qwen-plus/关键词后检索结果偏移至 github 源。
- 根因：与 A2 同类——github 源返回的 README/摘要无法被 DatasetSkill 消费成包内文件；候选源排序/查询词随模型波动。
- 建议：与 A2 合并处理——复核候选源排序稳定性 + DatasetSkill 对 github 摘要（markdown）的消费分支或显式降级。

### B. LLM 依赖问题（环境/兼容性，影响执行而非记录）

**B1. qwen-plus 免费配额耗尽（403 AllocationQuota.FreeTierOnly）**
- 现象：12 题执行中途 qwen-plus 全部 403，parse 降级 → 空需求 FAIL。
- 处置：改用 qwen-turbo 完成记录执行；用户 2026-08-21 提供新 API key 后 qwen-plus/turbo/max 均恢复。

**B2. qwen-max 结构化输出不兼容（LLMParseError）**
- 现象：qwen-max 的 `_GoalParsingResult` 中 `keywords`/`fallback_sources` 输出为**逗号分隔字符串**而非 JSON 数组，pydantic 校验失败 → parse_goal 降级 → 12 题全 FAIL。
- 根因：`LLMClient.call_structured` 对模型输出的「字段应为数组却给字符串」无容错；不同模型的结构化输出风格不一致。
- 建议：组长 B 评估在 `intelligence/client.py`（或 parse_goal 的 `_GoalParsingResult` 前处理）增加「字符串→数组」归一化，避免依赖单一模型的输出风格（本轮被迫锁 qwen-turbo）。

### C. 验收/截图口径问题（二轮执行中发现）

**C1. 截图采集口径（与 second_round_plan Step 4「截图记录每个文件内容」一致）**
- second_round_plan §9 Step 4 要求"执行截图记录每个文件内容，确认落包情况和内容"；据此落地为 **5 张/题**：① manifest.json 内容 ② provenance.log 内容 ③ 主数据文件内容（FAIL 无主文件为 4 张并注明）④ 前端 explorer 面板 ⑤ 前端 provenance 日志面板长截图（仅日志区、滚动全量多张拼接）。12 份记录 `screenshots[]` 已按此登记，不构成偏离。
- 方法说明：文件内容图因环境沙箱限制 Win11 记事本无法打开，改为 System.Drawing 等宽字体**全文渲染完整长图**（内容等价）；二进制主文件（如 mesh STL）渲染二进制说明图。

**C2. failure_category 枚举（以 second_round_plan.md 为准）**
- 按 second_round_plan §9 枚举：`P1_PARSE / P2_RETRIEVE / P3_SOURCE / P4_FORMAT / P5_LLM / P6_VALIDATE / P7_PACKAGE / P8_OTHER`。本轮 3 个 FAIL 使用 P1_PARSE（ss_graspnet_004）、P3_SOURCE（ss_graspnet_005、ss_google_scanned_005），两枚举下取值一致，无冲突。
- 提示：`manage_test_records.py` 脚本内枚举仍为旧版（P5_RUNTIME/P6_FRONTEND/P7_ENV），与计划不一致；记录/文档以计划为准，建议组长 B 同步脚本枚举，避免后续 FAIL 采用 P5_LLM 等时被脚本误拒。

### D. 台账/校验工具问题

**D1. progress.csv 扩容导致一轮/二轮判定失效**
- `manage_test_records.py all` 会把二轮记录并入 progress.csv（63 → 75 行）；执行脚本原以「不在 progress.csv」判二轮，扩容后二轮筛选返回空。已改为「一轮集合取 git HEAD 的 63 行台账 + 日期兜底」修复。
- 建议：台账文件增加轮次字段（如 `round` 列），避免依赖记录内容反推。

**D2. full-repo 校验暴露一轮记录既有问题（非二轮引入）**
- `manage_test_records.py all` 报告部分**一轮**记录存在校验错误且未复核（截图 0 张、issue_count 5~11）：`ss_ycb_001`（FAIL）、`ss_ycb_002`（FAIL）、`ss_ycb_003`（PWF）、`ss_robotiq_002/003`（已判定）等（executed_at 2026-08-20，git 状态显示未被本轮修改）。
- 建议：组长 B 安排对应执行人（D）补正这些记录，并复核。

### E. 记录数据质量（沿用一轮已修复的映射口径，二轮保持）

- retrieve.format 取 RawData 原始格式；quality 降级记 `fallback`、成功记 `real`；核心需求命中非题设源显式置 `is_fallback=true + fallback_reason`（源偏移）；`package.fallback_explicit` 合并检索级降级。二轮 12 题全部按此口径填写，结构校验 0 ERROR。

---

## 3. 整改方案（按优先级，建议组长 B 执行/分派）

| 优先级 | 问题 | 整改动作 | 验证方式 |
|---|---|---|---|
| P0 | A1 ss_graspnet_004 解析偏移 | 评估题面口径；GRASP 强词补「抓取标签/抓取规划」或调整归一化优先级 | 重跑 ss_graspnet_004 判 PASS/PWF |
| P0 | A2/A4 0 文件落包（ss_graspnet_005、ss_zenodo_006） | 复核候选源可达性/排序稳定性 + DatasetSkill 对 github README/摘要（markdown）的消费分支；不可消费格式显式降级 | 重跑 ss_graspnet_005、ss_zenodo_006 判 PASS/PWF |
| P0 | A3 ss_google_scanned_005 检索未命中 | 复核 google_scanned cup 匹配逻辑（对照 kettle/banana 成功路径） | 重跑 ss_google_scanned_005 判 PASS/PWF |
| P0 | B2 qwen-max 结构化输出不兼容 | `intelligence/client.py` 或 parse_goal 前处理：字符串列表 → 数组归一化 + 单测 | 全量单元测试 + qwen-max 冒烟 1 题 |
| P1 | B1 配额依赖 | 统一 API key 管理/配额告警；记录 env.llm_model 如实标注 | — |
| P1 | C2 枚举统一 | failure_category 以 second_round_plan 枚举为准；同步 `manage_test_records.py` 的 ALLOWED_FAILURE_CATEGORIES（P5_LLM/P6_VALIDATE/P7_PACKAGE） | `manage_test_records.py all` 校验通过 |
| P1 | D1 台账轮次字段 | progress.csv/assignments.csv 增加 `round` 字段，脚本按字段筛选 | 一轮/二轮筛选各自返回正确题数 |
| P2 | D2 一轮记录既有错误 | 分派 D 补正 ss_ycb_001/002/003、ss_robotiq_002/003 等记录并复核 | `manage_test_records.py all` 0 ERROR |
| P2 | C1 截图规范沉淀 | 把 5 张/题截图口径与「全文渲染长图」方案写进 second_round_plan SOP | 文档评审 |

---

## 4. 给组长 B 的行动清单

1. 聚类 A1~A4 四个 FAIL，按上表 P0 项在 `feat/integration-v3` 上修复（每处带单测），修复后重跑 4 题回归。
2. 评估 B2（LLM 结构化输出容错）——直接影响后续换模型/多模型执行，建议优先。
3. 以 second_round_plan 枚举为准，同步 `manage_test_records.py` 的 failure_category 枚举（P5_LLM/P6_VALIDATE/P7_PACKAGE）。
4. 安排 D2 一轮记录补正（涉及执行人 D），并复核。
5. 回归后按 second_round_plan §6 分层统计总成功率，与一轮 63 题回归结果对比，出具出口验收。

---

## 5. 与 second_round_plan.md 对照（合规性）

| second_round_plan 要求 | 本报告/记录状态 |
|---|---|
| §9 Step 4 截图记录每个文件内容 + explorer 面板 + provenance 长截图 | ✅ 5 张/题（manifest / provenance.log / 主数据文件内容 + explorer + provenance 日志面板长截图），FAIL 题 03 为"无主文件 FAIL 说明"图 |
| §5.2 判定分级 PASS/PASS_WITH_FALLBACK/FAIL | ✅ 12 题齐全（1/7/4） |
| §6.1 总成功率 = (PASS+PWF)/执行单元数 | ✅ 66.7%（8/12） |
| §6.2 分层分布（source/category/priority/P0） | ✅ 见 r2_c_summary §3（仅二轮 12 题；一轮 63 题已由 C 此前完成） |
| §6.3 归因分类（系统问题 vs 环境/数据不可控） | ✅ A 类=系统 FAIL（4 题）、B 类=环境/依赖（配额、模型兼容） |
| §9 失败收集三字段（verdict/failure_category/failure_reason） | ✅ 枚举以 second_round_plan 为准（P1_PARSE/P3_SOURCE 等），原因已填 |
| §10.2 组员只摸底不修代码 / 记录写入 robot-data-integrator/records | ✅ 记录/截图/统计就位，修复方案交组长 B 执行 |
| §7 二轮执行脚本 / init-record 骨架 | ✅ 执行脚本 rerun_c_round2.py 已产出；记录由脚本直接生成 |

**范围说明**：本轮仅执行 C 二轮 12 题（一轮 63 题回归已由 C 在此前完成），本报告只汇总二轮统计与问题，不重复一轮回归数据。

> 附：C 侧已完成的交付（记录/截图/进度日志/统计摘要）见 `r2_c_summary.md`，可随时提供明细。
