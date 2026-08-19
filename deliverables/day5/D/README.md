# Day 5｜D（机器人工程师）清尾补测方案与执行记录

> 分支：`feat/arch-langgraph`
> 方案制定：2026-08-16（依据 `docs/problem_set/Day5_执行截止与补测缓冲.md` + `docs/problem_set/问题集构建策略.md`）
> **执行完成：2026-08-17（13 个 case 全部通过真实前端流程补测并同步 records/；可加载性结论与 P4/P5 清单已交付）**
> 问题集：`problem_set/problem_set.json`　进度表：`records/_management/progress.csv`（已更新）
> 交付目录：`deliverables/day5/D/`（README、可加载性验证结论.md、P4_P5失败清单.md 三份均就绪）

---

## 0. 执行状态总览（2026-08-17）

| 阶段 | 内容 | 状态 |
| ---- | ---- | ---- |
| 阶段一 | 13 个 case 清尾补测（真实前端流程 + 完整页面截图） | ✅ **已完成**（13/13 通过，0 FAIL） |
| 阶段二 | 可加载性验证结论（`可加载性验证结论.md`） | ✅ **已完成**（13+1 包实际加载验证全通过） |
| 阶段三 | P4/P5 失败清单（`P4_P5失败清单.md`） | ✅ **已完成**（历史 9 例 + 1 例残余） |
| 阶段四-1 | record.json + observe.json + screenshots 同步至 `records/<case_id>/` | ✅ 已完成（observe.json 缺口已于 2026-08-17 补齐） |
| 阶段四-2 | progress.csv 更新 13 行（executor=D、已判定、verdict） | ✅ 已完成（2026-08-17T17:46:07） |
| 阶段四-3 | 交付 README + 结论 + 清单 | ✅ **全部完成** |

**最终判定：13/13 全部通过，无 FAIL。records/ 冻结口径为 9 PASS + 4 PASS_WITH_FALLBACK（google_scanned×3、ms_003 经 A 合规化转 PWF；deliverables 口径为 10 PASS + 3 PWF，差异见 §2.2，以 records/ 为准）。P0 可用 11/11（目标 ≥8）已达成。**

## 1. 任务目标（Day5 D 两项 + 策略 §6.3 D 职责）

| # | 任务 | 对应策略条目 | 状态 |
| - | ---- | ---------- | ---- |
| 1 | **清尾补测**格式/仿真类遗漏 case，补充可加载性验证结论 | §6.3.2 / §6.3.3 / §6.3.5 | ✅ 补测完成；`可加载性验证结论.md` 已产出（13+1 包全通过） |
| 2 | **整理 P4_FORMAT / P5_RUNTIME 失败清单**（每条含 case_id、现象、初步定位） | §6.3.4 | ✅ `P4_P5失败清单.md` 已产出（历史 9 例 + 1 例残余） |
| 3 | 数据包可加载性逐类验证（URDF→yourdfpy、Mesh→trimesh、MJCF→mujoco.mj_step） | §6.3.3 | ✅ 已逐包实际执行并汇总（见 §3.2 / 结论文档） |
| 4 | 核验数据包结构（与 manifest.json 一致） | §6.3.5 | ✅ 补测中已核验 |

## 2. 现状盘点（2026-08-17 更新）

### 2.1 13 个 case 已全部补测完成（原方案盘点已过时）

原方案（2026-08-16）中「13 个 case 未执行、历史 record 多为修复前判定、截图对应修复前界面」的判断已不再成立：**2026-08-17 已用当前（已修复）代码对 day3/day4 全部 13 个 case 逐一走真实前端流程重测**（Gradio localhost:7860 → 输入 → 各阶段 → human_review 中断 → satisfied → resume 打包），判定、截图均对应最新代码与最新界面，并已覆盖写回 `deliverables/day3|4/D/` 与 `records/`。

### 2.2 补测判定汇总（13/13 通过）

| case_id | 优先级 | 命中源 | verdict | package_id | 落盘文件 | validation_issues(error) | 可加载性 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| ss_franka_001 | P0 | franka | **PASS** | package-20260817-113850 | 19（URDF+18 OBJ） | 0 | URDF 13/12 + mesh 18/18 |
| ss_franka_002 | P1 | franka（含 github fallback） | **PASS** | package-20260817-115803 | 19 | 0 | URDF 13/12 + mesh 18/18 |
| ss_franka_003 | P2 | franka | **PASS** | package-20260817-120921 | 19 | 0 | URDF 13/12 + mesh 18/18 |
| ss_robotiq_001 | P0 | robotiq | **PASS** | package-20260817-124542 | 11（URDF+10 mesh） | 0 | URDF 11/10 + mesh 10/10 |
| ss_robotiq_002 | P1 | robotiq | **PASS** | package-20260817-131814 | 11 | 0 | URDF 11/10 + mesh 10/10 |
| ss_robotiq_003 | P2 | robotiq | **PASS** | package-20260817-133551 | 11 | 0 | URDF 11/10 + mesh 10/10 |
| ss_allegro_001 | P1 | allegro | **PASS** | package-20260817-075635 | 12 | 0 | URDF+11 mesh |
| ss_allegro_002 | P1 | allegro | **PASS** | package-20260817-080156 | 12 | 0 | URDF+11 mesh |
| ss_allegro_003 | P2 | allegro | **PASS** | package-20260817-080707 | 12 | 0 | URDF+11 mesh |
| ss_google_scanned_001 | P1 | google_scanned | **PASS_WITH_FALLBACK** | package-20260817-081226 | 1 | 0 | mesh 可加载（watertight） |
| ss_google_scanned_002 | P1 | google_scanned | **PASS_WITH_FALLBACK** | package-20260817-081600 | 1 | 0 | mesh 可加载 |
| ss_google_scanned_003 | P2 | google_scanned | **PASS_WITH_FALLBACK** | package-20260817-083252 | 1 | 0 | mesh 可加载 |
| ms_003 | P1 | kinova+google_scanned+graspnet+isaac | **PASS_WITH_FALLBACK** | package-20260817-122845 | 12 | 0（7 条 WARNING） | URDF+mesh 全可加载；sim_config passed |

> 说明：ss_google_scanned×3 与 ms_003 在 `deliverables/` 与 `records/` 两处判定口径可能不同（如 google_scanned 系列 deliverables 记为 PASS、records/ 经 A 合规化记为 PASS_WITH_FALLBACK，见 §2.3）。**records/ 为 A/F 冻结口径，以 records/ 为准。**

### 2.3 A 合规化修订（待 D 复核）

2026-08-17 角色 A 对已入库记录做了合规化修订，记录内标注「待 D 复核」：

- google_scanned 系列：期望格式 OBJ/GLB/PLY、实际落盘 STL → `is_fallback=true` + `fallback_reason` + verdict 改为 **PASS_WITH_FALLBACK**（口径 §3.3）。
- 其他字段合规化（如 `req_list` 小写、`r[0].req_type` 修正）同批标注待复核。

**待办（2026-08-17 更新）**：经 D 核对，A 的合规化修订与实测基本一致，予以确认；**按用户指示，两处保持原样不改**——① allegro×3 的 `parse_goal.requirements[0].req_type` 仍为大写 `ROBOT_URDF`；② franka×3 的 notes 合规化标注文本含 ms_003 修改项（复制粘贴笔误，字段本身已正确）。最终口径确认与「待复核」标注移除移交 F/A 冻结环节处理。

### 2.4 records/ 同步（已补齐）

| case_id | record.json | observe.json | screenshots |
| ---- | ---- | ---- | ---- |
| ss_robotiq×3 / ss_allegro×3 / ss_google_scanned×3（9 个） | ✅ | ✅ | ✅ 8/8（robotiq_003 为 4/8） |
| ss_franka_001/002/003 | ✅ | ✅（2026-08-17 补齐） | ✅ 8/8 |
| ms_003 | ✅ | ✅（2026-08-17 补齐） | ✅ 8/8 |

> **截图缺口（唯一残留）：ss_robotiq_003 仅 4/8**（最终态 02_retrieve / 03_validate / 04_package、中间态 03_validate 未完成——浏览器一次性捕获失败，按指示不再重试，已在 record.json 与 day3 README 中说明）。

### 2.5 F 统计门槛联动（已达成）

| 指标 | 原方案预期 | 当前实际（2026-08-17T17:46:07） |
| ---- | ---- | ---- |
| 已执行 / 已判定 | 45 / 45 → 补测后 ↑ | **62 / 62**（63 题，ms_008 未执行，正式分配 executor=F） |
| 0 判定 | 7/11 → 预期 9/11 | **P0 可用 11/11（≥8 达成）** ✅ |
| FAIL 数 | — | **0** |
| reviewed | 0 | 13/13（**2026-08-17 23:17 由 A 全库复核补齐，reviewer=A**；非 D 职责） |
| all_cases_executed | 18→5 | false（ms_008 未执行，正式分配 executor=F；A 曾代跑未成功） |

## 3. 执行记录

### 3.1 阶段一：13 个 case 真实前端流程补测（已完成）

- 执行时间：2026-08-17 07:56 – 13:35（allegro/gs → franka/ms_003 → robotiq）。
- 每 case 均走完整真实流程，截图按 §5.4（intermediate + final 各 4 张，滚动分块拼接完整页面）。
- 补测中发现并修复最后一个阻塞缺陷：**robotiq xacro 展开器参数代入 bug**（`_eval_xacro_expr` ast 白名单不含宏参数，`${reflect * -0.0127}` 求值返回空串 → `<origin>` xyz/rpy 退化为 2 个数值 → yourdfpy 解析失败）。修复：`_eval_xacro_expr(expr, scope)` 先整词代入宏参数实参再求值。该修复已随代码入库（工作树干净）。
- 补测过程记录见各 case 的 `deliverables/day3|4/D/<case_id>/record.json`（notes 含新旧对比）。

### 3.2 阶段二：可加载性验证（已完成，正式文档已产出）

对 13 个补测数据包 + 补充 ms_005，实际执行加载验证（脚本 `data/_verify_loadability.py`，结果 JSON `data/_loadability_results.json`，不入库），汇总见 **`可加载性验证结论.md`**：

- URDF：`yourdfpy.URDF.load(load_meshes=True)` 全部通过（franka 13/12、robotiq 11/10、allegro 23/22、ms_003 kortex 11/10；google_scanned 为纯 mesh 题无 URDF）。
- Mesh：`trimesh.load` 全部通过（franka 18/18 OBJ、robotiq 10/10、allegro 11/11、google_scanned 1/1 STL、ms_003 9/9、ms_005 87/87）。
- MJCF：13 个补测包内无 MJCF 资产（ms_003 sim_config 为 Isaac Python `req_003.py`，静态核验随包交付）；MuJoCo 运行时验证由 **ms_005**（day3）覆盖：`sim_config/panda.xml`、`req_002.xml` 加载 + `mj_step` 通过（nq=9/nv=9）。
- **结论：全部可加载、可运行，无验证失败项。**

### 3.3 阶段四-2：progress.csv 更新（已完成）

13 行均已更新：`executor=D`、`status=已判定`、`verdict=<实际>`、`failure_category`（空，均无 FAIL）、`executed_at=2026-08-17Txx:xx:xx`、`screenshot_count`（robotiq_003=4，其余 8）、`completeness_pct=100.0`、`updated_at=2026-08-17T17:46:07+08:00`；`reviewed` 留空待 F。

## 4. 交付物结构（已完成）

```
deliverables/day5/D/
├── README.md                     # ✅ 索引（方案 + 执行记录 + 待办）
├── 可加载性验证结论.md             # ✅ 阶段二产物（13+1 包实际加载验证）
└── P4_P5失败清单.md               # ✅ 阶段三产物（历史 9 例 + 1 例残余）
```

## 5. 剩余待办与风险

### 5.1 待办清单（执行后剩余）

1. **可加载性验证结论.md** —— ✅ 已产出。
2. **P4_P5失败清单.md** —— ✅ 已产出。
3. **observe.json 同步**（franka×3、ms_003）—— ✅ 已补齐（2026-08-17）。
4. **A 合规化修订确认** —— 已核对基本一致；**两处（allegro req_type、franka 标注文本）按用户指示保持原样**；「待复核」标注移除与最终口径确认移交 F/A 冻结环节。
5. `reviewed` 填充与冻结批准属 F/A 环节（D 不处理）。

### 5.2 剩余风险（对应正式清单见 `P4_P5失败清单.md`）

| case_id | 风险 | 说明 |
| ---- | ---- | ---- |
| ms_003 | GRASP req_002 空壳（残余） | GraspNet 仅 json 元数据（60%/0.6），非真实 NPZ 姿态；已显式 fallback 记录，不阻断 PWF 判定，建议后续补样本 |

### 5.3 风险提示

1. **截图缺口（ss_robotiq_003 4/8）**：按用户指示一次性捕获失败不重试；缺口已记录于 `records/ss_robotiq_003/record.json` 与 day3 README。
2. **records/ 与 deliverables/ 判定口径差异**（google_scanned 系列 PASS vs PASS_WITH_FALLBACK）：以 records/（A 合规化后）为冻结口径，待 D 复核确认。
3. **ms_003 残余**：GRASP req_002 空壳（json 元数据），不阻断 PASS_WITH_FALLBACK 判定，如实记录。
4. **LLM 非确定性**：parse_goal 关键词每次可能不同，判定以最终产物为准（records/ 已按实际 input 记录）。
5. **reviewed**：本 README 交付时点 reviewed 为 0；2026-08-17 23:17 A 已全库复核补齐（reviewer=A），属时间先后，非 D 职责。

## 6. 与 A/F 的对接点

| 对接人 | 内容 | 期望输出 |
| ---- | ---- | ---- |
| F | 13 个 case 补测记录已入 `records/`（record+observe+screenshots）+ progress.csv 已更新（判定一致） | F 全量校验（JSON 合法/判定一致/截图齐备）并填充 reviewed |
| F | **P4/P5 失败清单已交付**（`P4_P5失败清单.md`：历史 9 例 + 1 例残余，均已修复或显式 fallback） | F 并入失败原因统计 |
| A | P0 缺口已关闭：**11/11（≥8）达成** | A 终验执行完整性；合规化修订最终口径确认（两处保持原样，见 §2.3） |
| F | ms_008 仍未执行（正式分配 executor=F，progress 显示未执行；A 曾代跑未成功） | F 执行 ms_008 后由 A 复核 |
