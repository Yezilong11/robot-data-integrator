# Day 5｜D（机器人工程师）清尾补测方案

> 分支：`feat/arch-langgraph`　执行日期：2026-08-16
> 依据：`Day5_执行截止与补测缓冲.md`（D 任务）+ `问题集构建策略.md`（§5 记录模板/§5.4 截图/§5.5 判定、§6.3 D 职责）
> 问题集：`problem_set/problem_set.json`　进度表：`records/_management/progress.csv`
> 交付目录：`deliverables/day5/D/`

---

## 1. 任务目标（Day5 D 两项 + 策略 §6.3 D 职责）

| # | 任务 | 对应策略条目 |
| - | ---- | ---------- |
| 1 | **清尾补测**格式/仿真类遗漏 case，补充可加载性验证结论 | §6.3.2 / §6.3.3 / §6.3.5 |
| 2 | **整理 P4_FORMAT / P5_RUNTIME 失败清单**（每条含 case_id、现象、初步定位） | §6.3.4 |
| 3 | 数据包可加载性逐类验证（URDF→yourdfpy `load_meshes=True`、Mesh→trimesh、MJCF→`mujoco.mj_step`） | §6.3.3 |
| 4 | 核验数据包结构（`robots/objects/grasps/sim_config/` 与 `manifest.json` 一致） | §6.3.5 |

## 2. 现状盘点（重要）

### 2.1 progress.csv 中 D 认领 case 的执行缺口

D 认领 18 个 case（ycb×5、google_scanned×3、franka×3、robotiq×3、allegro×3、mujoco×5、isaac×2、ms_003），其中：

| 状态 | 数量 | 明细 |
| ---- | --- | ---- |
| 已判定（D 或 C 代执行） | 5 | ss_ycb_001(PASS)、ss_mujoco_001(PASS)、ss_mujoco_002/003/004/005、ss_isaac_001/002（后 6 个为 C 代执行已判定，不属 D 清尾范围） |
| **未执行（D 清尾对象）** | **13** | **ss_franka×3、ss_robotiq×3、ss_allegro×3、ss_google_scanned×3、ms_003** |

### 2.2 13 个 case 的历史产物（关键事实）

13 个 case 在 day3/day4 阶段**已实际执行并修复过**，交付物位于（但 **未同步到 `records/`**，progress.csv 仍显示「未执行」）：

- `deliverables/day3/D/`：ss_robotiq×3、ss_allegro×3、ss_google_scanned×3、ms_005（含 record.json + intermediate/final 截图）
- `deliverables/day4/D/`：ss_franka×3、ms_003（含 record.json + 截图）

**注意**：历史 record.json 多数为**修复前判定**（如 ms_003=FAIL/P2_RETRIEVE、ss_franka_002/003=PASS_WITH_FALLBACK、ss_robotiq_001=FAIL），且修复后重测多为脚本执行（`data/_rerun_day4.py`），截图仍对应修复前界面。Day5 清尾必须**以当前（已修复）代码重新走真实前端流程执行**，产出最终判定，避免记录与代码状态不符。

### 2.3 F 统计门槛联动

- F 当前统计：63 题 / 45 已判定 / 18 未执行 / **P0 可用 7/11（目标 ≥8）** / `reviewed=0`。
- D 的 2 个 **P0** 未执行题：**ss_franka_001、ss_robotiq_001** —— 补测通过后 P0 可用 → 9/11，满足 A 冻结门槛「P0 可用 ≥8/11」。
- 13 个 case 补测后：`all_cases_executed` 缺口从 18 降至 5（ms_001/002/005/006/008 属 A/C/F），`reviewed` 仍为 0（需 F 复核，不在 D 职责）。

## 3. 执行方案（四阶段）

### 阶段一：清尾补测 13 个 case（真实前端流程）

**原则**：每 case 走完整真实流程（Gradio localhost:7860 → 输入 → 各阶段 → human_review 中断 → resume 打包），截图满足 §5.4（intermediate + final 各 4 张：01_parse_goal / 02_retrieve / 03_validate / 04_package；FAIL 必截 05_error）。判定按 §5.5 三档。

**执行顺序（P0 → P1 → P2，LLM 统一 qwen-plus）**：

| 优先级 | case_id | 类型 | 预期命中源 | 预期判定 |
| ---- | ---- | ---- | ---- | ---- |
| P0 | ss_franka_001 | robot_urdf | franka | PASS |
| P0 | ss_robotiq_001 | robot_urdf | robotiq | PASS |
| P1 | ss_franka_002 / 003 | robot_urdf | franka（fallback 路径含 github） | PASS（19 文件） |
| P1 | ss_allegro_001 / 002 / 003 | robot_urdf | allegro | PASS |
| P1 | ss_google_scanned_001 / 002 / 003 | mesh | google_scanned | PASS_WITH_FALLBACK（大体积 003 走超时降级路径） |
| P1 | ss_robotiq_002 / 003 | robot_urdf | robotiq | PASS |
| P1 | ms_003 | 多源 end_to_end | kinova + google_scanned + graspnet + isaac | PASS（req_000 命中 kinova，12 文件） |
| P2 | — | — | — | — |

**产出**：
1. `records/<case_id>/record.json`（严格按 §5.2 模板，`input` 字段写实际输入原文、`executor=D`、`reviewer` 留待 F、`llm_model=qwen-plus`、`review_decision=satisfied`、`package.dir` 记录真实输出包路径）
2. `records/<case_id>/screenshots/{intermediate,final}/01~04.png`（完整长图拼接，参照 day3/day4 截图标准）
3. 复用 `data/_rerun_day4.py` 的自动化模式做**首次试跑/失败排查**（不计入记录），最终以真实前端流程截图定稿。

### 阶段二：可加载性验证结论（§6.3.3）

对阶段一产出的全部数据包，按格式逐类验证并汇总：

| 格式 | 工具 | 通过标准 |
| ---- | ---- | ---- |
| URDF | `yourdfpy`（`load_meshes=True`） | 模型结构 + 全部 mesh 引用可解析（无 `Unable to resolve filename`） |
| Mesh（obj/stl） | `trimesh` | 可加载、is_watertight 或面数>0、体积>0（视物体类型） |
| MJCF / sim_config | `mujoco.mj_loadModel` + `mj_step` | 加载无 ERROR、可推进一步仿真 |

产出 `deliverables/day5/D/可加载性验证结论.md`：逐 case 表（case_id → 包路径 → URDF/Mesh/MJCF 各项 passed/failed + 异常摘要）+ 结论（哪些验证不过、根因、是否已修复）。

### 阶段三：P4_FORMAT / P5_RUNTIME 失败清单（§6.3.4）

**数据来源**：① 全部 `records/*/record.json` 中 `failure_category` 为 P4/P5 或 `validate.runtime_check != passed` 的条目；② 阶段一补测中出现的 P4/P5；③ 历史修复记录（day3/day4 README、`sim_config_runtime_check_review.md`）。

**清单模板**（每条一行）：

```
| case_id | req_id | 失败码 | 现象 | 初步定位 | 状态 |
```

**已知 P4/P5 候选（历史）**：
- ss_franka_002/003 → P5_RUNTIME：`package://meshes/...` 11 处无法解析（网格未打包）——已修复（GitHubAdapter 资产跟随），重测 19 文件 LOAD_OK
- ms_003 req_003 → P4_FORMAT：python 场景落盘 `.xml`（格式错配）——已修复（`_ext_for_raw_format` python→.py）
- ms_003 场景资源引用名与落盘名不匹配 → P5_RUNTIME 隐患——已修复（资源名回写一致性）
- 历史 robotiq/allegro/xacro 相关问题（day3 修复集，如 xacro→urdf 展开）——需从 day3 交付物回查归档

产出 `deliverables/day5/D/P4_P5失败清单.md`。

### 阶段四：记录同步与交付

1. 将 13 个 case 的 `record.json` + `screenshots/` 落入 `records/<case_id>/`（与 F 的 `records/` 结构一致，供 F 校验与冻结）。
2. 更新 `records/_management/progress.csv` 对应 13 行：`executor=D`、`status=已判定`、`verdict=<实际>`、`failure_category`、`executed_at`、`screenshot_count`、`completeness_pct`（留 `reviewed` 空给 F）。
3. 交付 `deliverables/day5/D/`：`README.md`（索引+结果总览）、`可加载性验证结论.md`、`P4_P5失败清单.md`。

## 4. 交付物结构（目标）

```
deliverables/day5/D/
├── README.md                     # 索引：补测总览、判定汇总、与 A/F 对接说明
├── 可加载性验证结论.md             # §3 阶段二产物
└── P4_P5失败清单.md               # §3 阶段三产物
```

## 5. 风险与注意事项

1. **截图与判定一致性**：必须以当前代码的真实前端流程截图；不得复用修复前截图冒充最终判定。
2. **LLM 非确定性**：parse_goal 关键词每次可能不同（如 ms_003 曾出现 "URDF" 独立关键词误命中 Allegro，已修复但需留意），每 case 以实际 `input` 记录，判定以最终产物为准。
3. **ms_003 耗时**：kinova 下载 ~28s + 预算 36s，整 case ~108s；执行注意超时预算与 Hermes 动态优先级导致的源顺序变化。
4. **ss_google_scanned_003** 为"大体积物体超时/失败降级"验证题：预期走显式降级（PASS_WITH_FALLBACK，需 manifest 有 `is_fallback` 记录），不得无标记静默降级（否则 FAIL）。
5. **GRASP 空壳**：ms_003 req_002 历史为 json 元数据（60%/0.6），非真实 NPZ——如实记录为 fallback，作为残余风险在 README 说明。
6. **F 冻结联动**：冻结由 A 批准；D 只负责补测与记录同步，`reviewed` 填充与冻结批准属 F/A 环节。
7. 历史 day3/day4 交付物**保留不改**，仅作为证据与本次 records/ 同步的来源对照。

## 6. 与 A/F 的对接点

| 对接人 | 内容 | 期望输出 |
| ---- | ---- | ---- |
| F | 13 个 case 补测记录入 `records/` + progress.csv 更新 | F 全量校验（JSON 合法/判定一致/截图齐备） |
| F | P4/P5 失败清单 | F 并入失败原因统计（当前仅 P2_RETRIEVE(1)） |
| A | 补测完成确认 + P0 缺口关闭说明（7/11→9/11） | A 终验执行完整性 |
