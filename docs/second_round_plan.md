# 二轮测试执行指导（Round 2 Plan）

> 状态：已审定 · 待执行
> 依据：一轮测试经验（`deliverables/`、`records/`）+ 本轮已确认的执行决策
> 关联：`problem_set/problem_set.json`（v1.1，共 122 题）、`scripts/manage_test_records.py`

***

## 1. 背景与目标

首轮（Round 1）在 `feat/arch-langgraph` 分支完成了 63 题的执行与收敛（43 单元 86% 首败 → 0 FAIL），并沉淀了 8 处代码修复与一套 `PASS / PASS_WITH_FALLBACK / FAIL` 判定契约。

**二轮目标**：

1. **扩展覆盖**：题库由 63 题 → **122 题**（新增 59 题，覆盖 kinova 源、mujoco sim\_config、sensor\_data/code/policy\_model 需求类型、多源 8→15）
2. **全量摸底**：重跑一轮 63 题回归 + 新 59 题，计算二轮成功率
3. **先测后修**：先全量摸底取得真实 FAIL 清单，再聚类根因、逐个修复
4. **简化验收**：相比一轮每题 8 张截图，二轮收敛为「package 目录系统资源管理器全屏 1 张 + 前端 explorer 1 张 + provenance 运行日志长截图 1 张」

***

## 2. 范围与题库规模

| 轮次     | 单源      | 多源     | 小计      |
| ------ | ------- | ------ | ------- |
| 一轮（回归） | 55      | 8      | 63      |
| 二轮新增   | 52      | 7      | 59      |
| **合计** | **107** | **15** | **122** |

二轮新增扩展方向：

- **补源**：kinova（5 题，robot\_urdf）
- **补需求类型**：sensor\_data（5）、code（5）、policy\_model（4）
- **重平衡**：mujoco sim\_config 0→4
- **多源**：8 → 15（+7，含端到端代码+权重、传感器+代码组合）

> 注：新增题全部限定在 SkillRegistry 已实现的 9 种 req\_type 内。`camera_calib / teaching_trajectory / robot_config / benchmark_task` 四个 req\_type 虽然枚举中存在，但**无对应 Skill 实现，未纳入题库**，留作后续调研方向。

***

## 3. 执行顺序（先全量再修）

```
阶段 1  全量摸底    122 题全部执行一遍，记录原始 verdict（组员执行，产 reports/records）
阶段 2  聚类根因    组长 B 通读全员报告，对 FAIL 做根因聚类（P3_SOURCE/P4_FORMAT/P2_RETRIEVE/…）
阶段 3  分组修复    组长 B 一人执行，同类一次修；每处修复必须带单元测试
阶段 4  回归验证    组长 B 每修一批重跑受影响题 + 全量单元测试；绿了进下一批
阶段 5  出口验收    算成功率、达标线、`manage_test_records` 校验
```

**明确承担的风险**：本方案采用「先全量再修」，已确认放弃「先基线打通」（补 ms\_008、清遗留三件事、回归护栏）。这意味着首轮摸底大概率出现高 FAIL 率（可复现一轮 86% 首败的返工），为既定取舍。

***

## 4. 执行人分配（59 新题）

- **按题量均分**：59 / 5 ≈ 12 题/人，由 A/C/D/E/F 五名执行人轮转分配
- **多源题也均分**：ms\_009 \~ ms\_015 共 7 题并入轮转，不单独指定人
- 分配表落地到 `records/_management/assignments.csv`

***

## 5. 验收口径（二轮简化版）

### 5.1 证据采集

二轮截图统一为**三部分**（不再按 parse/retrieve/validate/package 四阶段分别截图）：

| 证据项                                                         | 数量/方式                  | 目的                                                 |
| ----------------------------------------------------------- | ---------------------- | -------------------------------------------------- |
| **系统资源管理器**（Windows 打开 `data/output_packages/package-xxx/`） | **全屏截图 1 张**（文件多则分屏截全） | 证明 package 文件夹下所有文件真实落盘                            |
| **前端资源管理器界面**（`explorer` 面板，数据包文件树）                         | **全屏截图 1 张**           | 前端视角的数据包目录/结构展示                                    |
| **前端运行日志 provenance**（`log` 面板）                             | **长截图 1 张**（滚动全量）      | 展示 run\_graph 运行日志、检索调用链溯源（provenance）与 llm\_usage |
| manifest / record.json                                      | 结构化落盘                  | 权威证据，脚本可校验                                         |

每题 **3 张**截图（系统资源管理器 1 + 前端 explorer 1 + provenance 长截图 1）；不再逐数据包文件截图（一轮的 4 阶段 ×2 态 = 8 张 → 二轮收敛为 3 张）。

### 5.2 判定分级

沿用一轮契约：

- `PASS`：real 数据，完整匹配
- `PASS_WITH_FALLBACK`：降级数据，`is_fallback=true` 显式标记
- `FAIL`：未能产出 / 数据不可用

### 5.3 兜底规则

若执行环境无法启动无头浏览器（无法前端截图），改用「结果页 DOM 导出 + 关键字段断言」兜底，仅对真需演示的题保留截图。

***

## 6. 成功率计算

分四层统计，不混为一谈：

1. **总成功率** = (PASS + PASS\_WITH\_FALLBACK) / 执行单元数
2. **分层分布**：按 source、category、priority、P0 达标线
3. **归因分类**：区分「系统问题 FAIL」vs「环境/数据不可控」（后者不计入修复责任，单列说明）
4. **回归对比**：一轮 63 题在二轮代码下的重跑结果 vs 一轮记录

***

## 7. 落地步骤（执行清单）

- [ ] 生成 59 新题分配表 → 写入 `assignments.csv`
- [ ] 逐个 `init-record` 生成 59 个新题记录目录骨架
- [ ] 起草二轮执行脚本（批量调度 + package 目录系统资源管理器截图 + 前端 explorer 截图 + provenance 日志长截图 + manifest 落盘）——按需重写，不依赖一轮已删临时脚本
- [ ] 组员执行全量摸底 122 题 → 二轮全量完成后向组长 B 提交报告
- [ ] 组长 B 通读全员报告 → 聚类根因 → 分组修复（带单测）→ 回归
- [ ] 组长 B 出口验收：成功率门槛 + `manage_test_records` 校验收口

***

## 8. 已确认决策清单（供追溯）

| 决策点     | 结论                                                          |
| ------- | ----------------------------------------------------------- |
| 题库规模    | 63 → 122（新增 59）                                             |
| 执行顺序    | **先全量再修**（放弃基线打通，接受高首败返工）                                   |
| 新题分配    | 按题量均分，多源也均分（不指定）                                            |
| 数据包文件验证 | 系统资源管理器截 package 目录全屏 1 张 + manifest 证明落盘                   |
| 前端验证    | 前端资源管理器面板全屏 1 张 + provenance 运行日志长截图 1 张                    |
| 记录/验收   | 简化版，复用 `manage_test_records.py`                             |
| 成功率     | 分层统计 + 环境/系统归因分离                                            |
| 标准做法    | 人工 SOP 文档（追加于本文件第 9 节）                                      |
| 执行分支    | **同一分支** **`feat/integration-v3`** **+ 分阶段**（摸底只跑不改 → 集中修复） |

***

## 9. 单题标准操作 SOP（人工执行）

> 适用：每名执行人（A/C/D/E/F）领取一道 case 后，按此 6 步标准动作执行。
> 依据：一轮真实链路（见 `records/ss_mujoco_001/record.json` 等）。二轮相比一轮的简化见 Step 5 截图口径。

### Step 0 · 准备

- [ ] 确认自己的执行人号与题单（`assignments_overview.md `）

### Step 1 · 录入输入并执行

- [ ] 把题目的 `target` 作为真实 `input` 输入前端，跑通 `run_graph`（**真实流程，非 mock**）

### Step 2 · 核对解析（parse\_goal）

- [ ] 比对 LLM 解析出的 `req_list` 与题设 `expected.req_types`
- [ ] 记录 `vs_expected` = match / partial / mismatch；partial/mismatch 必须写 `note` 说明多/缺需求原因
- [ ] 写入 `observations.parse_goal`

### Step 3 · 检索（retrieve）

- [ ] 对每个 req 记录：source、status(success/missing/error)、elapsed、format、quality、is\_fallback、data\_url
- [ ] **现场判定数据真伪与降级**：real/fallback/unknown、`is_fallback=true` 是否显式标记
- [ ] 下载的每个数据包文件落盘保存

### Step 4 · 校验与打包（validate + package）

- [ ] 校验：errors/warnings、`runtime_check`（URDF 用 yourdfpy、mesh 用 trimesh、mjcf 用 mujoco.mj\_step）
- [ ] 打包：manifest 生成、status(complete/partial/missing)、file\_count、`fallback_explicit`
- [ ] **二轮截图（在 Step 4 完成后统一采集）**：
  - [ ] **系统资源管理器**：组员记得留意 `data/output_packages/package-<时间戳>/` ，并执行截图记录每个文件内容，确认落包情况和内容。（二进制文件内容可以不作为截图目标）
  - [ ] 前端「**资源管理器**」面板（`explorer` 文件树）打开数据包 → **全屏截图 1 张**
  - [ ] 前端「**日志**」面板（`log`，provenance 运行日志 + llm\_usage）滚动到底 → **长截图 1 张**

### Step 5 · 判定（verdict）

- [ ] 按契约判定 `PASS` / `PASS_WITH_FALLBACK` / `FAIL`
- [ ] FAIL 必填 `failure_category`（P3\_SOURCE/P4\_FORMAT/P2\_RETRIEVE/…）+ `failure_reason`
- [ ] 填全 `record.json`

### Step 6 · 归档与复核

- [ ] 截图归档到 `screenshots/`
- [ ] 提交 reviewer 复核（填 `reviewer` / `reviewed_at`）

### 二轮截图口径（相对一轮的简化）

| 环节                         | 一轮                                  | 二轮                                                      |
| -------------------------- | ----------------------------------- | ------------------------------------------------------- |
| 前端截图                       | 中间态+最终态 × 4 步 = 8 张                 | **前端 explorer 全屏 1 张 + provenance 运行日志长截图 1 张** = 2 张   |
| 数据包文件                      | 部分截图                                | **系统资源管理器截 package 目录全屏 1 张** + manifest 证明落盘（不再逐文件截图）  |
| parse/retrieve/validate 记录 | 全量填                                 | **不变**（判定依据，不能省）                                        |
| 截图归档                       | `screenshots/` 分 intermediate/final | `screenshots/`（3 张：系统资源管理器 + `explorer` + `provenance`） |

> 截图登记进 `record.json` 的 `screenshots[]`，每项含 `file` + `desc`（如"package-dir-full"、"explorer-panel"、"provenance-log"）。长截图建议滚动全量，避免截断。

### 失败收集（FAIL 必做，字段驱动，不写独立报告）

FAIL 时组员只需在 `record.json` 填好 3 个字段（工具强制校验，非 FAIL 不得填）：

| 字段                 | 说明                                                                                                               | 必填 |
| ------------------ | ---------------------------------------------------------------------------------------------------------------- | -- |
| `verdict`          | `= FAIL`                                                                                                         | ✅  |
| `failure_category` | 从枚举选：`P1_PARSE / P2_RETRIEVE / P3_SOURCE / P4_FORMAT / P5_LLM / P6_VALIDATE / P7_PACKAGE / P8_OTHER`——这是后续聚类的关键词 | ✅  |
| `failure_reason`   | 一句根因（如"IEEE 401 无 key"、"URDF 解析失败"、"超时 60s 降级"）                                                                  | ✅  |

***

## 10. 执行分支与并发协调

### 10.1 分支策略

- **统一在当前** **`feat/integration-v3`** **分支执行**，不各开新分支、不建 worktree
- **摸底阶段代码冻结**：只跑不改（产 records），确保 5 人执行的是同一份代码基线，成功率可比
- **修复阶段**：组员不再碰代码；组长 **B** 通读全员报告后在 `feat/integration-v3` 集中修复

### 10.2 职责与协作（关键：执行 / 修复分离）

**组员（A/C/D/E/F）+ 组长（B）角色分离**，避免执行与修复互相干扰：

- **组员**：只负责**执行摸底 + 采集证据 + 写记录**，不负责修代码。
  - 执行记录写入统一目录 `robot-data-integrator/records/`（按 case 建档 `records/<case_id>/`）
  - **摸底阶段不修改任何** **`src/`、`tests/`、`pyproject.toml`** **代码文件**——所有人共享只读代码基线
- **报告提交**：**二轮全量测试完成后**，每名组员向组长提交自己的执行记录报告（报告内容统一按会议交代的模板/口径，此处不重复展开）
- **组长（B）**：**通读所有人报告** → 汇总摸底 FAIL 清单 → 聚类根因 → **由组长 B 一人执行全部修复**（带单测）→ 回归

### 10.3 冲突说明

- **摸底阶段**：几乎无冲突——组员只写各自的 `records/<case_id>/`，代码（src/tests/pyproject.toml）全员只读
- **修复阶段**：只有组长一人改代码，无并发写竞争；统一在 `feat/integration-v3` 上按"一次修复批次一个提交"推进
- 判定/归因（Step 5）不依赖前端并发写，可各自独立完成；记录与修复天然分离（组员写 records，组长改 src/tests）

### 10.4 一轮经验回用

- 一轮也采用同分支按 case 分流执行（records 中 A/C/D/E/F 各自建 case 目录），二轮沿用同一套即可
- 避免重蹈 worktree 缺依赖的坑：同分支同环境即可，无需额外隔离

