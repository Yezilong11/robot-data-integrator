# Robot Data Integrator — 第三次联调技术指导文档

> 版本：1.0
> 编制日期：2026-08-08
> 目标读者：A/B/C/D/E/F 六位角色
> 依据：
> - [第二次联调报告](../../docs/second_integration_report.md)
> - [第二次联调技术指导](./second-integration-technical-guide.md)
> - [项目人员分工与技能要求](file:///E:/智囊腾析微/项目人员分工与技能要求.md)

---

## 1. 文档目的

本文档是第三次联调（以下简称「三联」）的**执行级技术指导书**，回答三个问题：

1. **要解决什么问题**：从「能生成真实文件」到「研究人员能日常拿来准备实验」之间的关键差距。
2. **要怎么做**：每个角色需要修改哪些文件、采用什么技术方案、按什么顺序推进。
3. **怎么分工协作**：A/B/C/D/E/F 各自的职责边界、交付物、验收标准。

三联的北极星指标：

> **输入任意常见机器人操作目标（中英文、多种机器人/物体/仿真器组合），系统自动生成结构化的实验数据包，其中 grasp 数据来自真实数据集或高质量备选源，sim_config 能在 MuJoCo 中直接加载并运行至少一步仿真，用户可通过 human_review 闭环修正结果。**

---

## 2. 当前状态与关键差距

### 2.1 二联已具备的基础

- 中文自然语言目标端到端可用，能生成 `URDF + mesh + MJCF XML + grasp JSON` 四类文件。
- 生成数据包样例：`data/output_packages/package-20260808-181854/`，无 validation ERROR。
- 测试：`393 passed / 1 skipped / 9 deselected`；lint/format 全绿。
- Adapter 多 token 搜索、`SimConfigSkill` 最小 MJCF fallback、`GraspSkill` metadata fallback 已实现。

### 2.2 核心差距：从「能跑通」到「日常可用」

| 维度 | 当前状态 | 日常可用要求 | 差距 |
|---|---|---|---|
| **grasp 真实性** | synthetic / metadata JSON 降级 | 来自真实数据集（GraspNet / DexGrasp / YCB-Video）的 `.npz`/`.pkl` | 无真实抓取姿态，无法验证规划 |
| **sim_config 真实性** | 多为基于 URDF/mesh 的最小 MJCF fallback | 能命中 `mujoco_menagerie` 真实场景，或生成包含相机/地面/灯光的完整场景 | 复杂实验场景需手动补全 |
| **LLM 目标解析稳定性** | 特定中文句式可用，换表述/换组合可能失败 | 覆盖 10+ 常见机器人/物体/仿真器组合，错误率 < 10% | 鲁棒性不足 |
| **human_review 闭环** | 占位节点，不触发重检索 | `revised`/`unsatisfied` 能回到 `retrieve_data` 重新生成数据包 | 用户无法修正结果 |
| **数据包组织** | 扁平 `files/` 目录 | 按 `robots/`、`objects/`、`grasps/`、`sim_config/` 结构化 | 不便于直接使用 |
| **真实可运行性验证** | 仅解析文件格式 | MuJoCo 加载场景并运行一步仿真 | 未验证运行时正确性 |
| **源选择智能化** | 按 fallback_sources 固定顺序 | Hermes 根据历史成功率动态推荐源 | 失败后需人工干预 |
| **前端体验** | 只展示最终结果 | 展示每个 DataReq 的阶段、成功/失败、原因 | 调试困难 |

---

## 3. 三联总体目标

1. **P0：真实 grasp 数据路径** — 实现 GraspNet / DexGrasp / YCB-Video 单个抓取文件下载与解析，建立本地缓存。
2. **P0：LLM 目标解析稳定化** — 结构化输出 + 规则后处理 + 多组合覆盖测试。
3. **P0：human_review 真实闭环** — `revised`/`unsatisfied` 触发 LangGraph 循环重检索。
4. **P1：数据包目录结构化** — 按类型组织输出目录。
5. **P1：真实可运行性验证** — MuJoCo 加载并运行一步仿真。
6. **P1：Hermes 源选择优化** — 基于历史成功率动态排序 Adapter。
7. **P2：前端进度可视化** — 展示阶段、状态、失败原因。

---

## 4. 角色分工与执行地图

角色定义沿用 [项目人员分工与技能要求](file:///E:/智囊腾析微/项目人员分工与技能要求.md)。

---

### A — 架构师 / 技术负责人

**三联核心职责**：定义「日常可用」的验收标准；主持联调节奏；决策 grasp/sim_config 真实数据路径取舍。

#### 任务 A1：定义三联数据包规范与验收标准

**要解决的问题**：当前数据包目录扁平，且未明确「真实可运行」的判定标准。

**怎么做**：

1. 在 [`src/rdi/models/manifest.py`](../../src/rdi/models/manifest.py) 中扩展 `PackageManifest`，增加：
   - `runtime_check` 字段：记录是否通过 MuJoCo 一步仿真；
   - `data_source_quality` 字段：标注每个文件是 `real` / `synthetic` / `fallback`；
   - `revision_history` 字段：记录 human_review 触发的版本关联。
2. 与 E 一起确定输出目录结构规范：
   ```text
   package-<ts>/
   ├── robots/
   ├── objects/
   ├── grasps/
   ├── sim_config/
   ├── policies/
   ├── scripts/
   ├── manifest.json
   └── provenance.log
   ```
3. 在 [`src/rdi/graph/builder.py`](../../src/rdi/graph/builder.py) 中设计 human_review 循环边，确保不破坏现有节点接口。

**验收标准**：

- [ ] `PackageManifest` 扩展不破坏现有 393 个测试；
- [ ] 输出目录结构规范文档化到本技术指导；
- [ ] human_review 循环边设计通过集成测试。

#### 任务 A2：主持联调站会与最终验收

**怎么做**：

1. 每日 15 分钟同步：各角色汇报进度与阻塞。
2. 每周五集成回归：合并到 `dev`，跑 `pytest` + `scripts/_probe_adapters.py` + 端到端 demo。
3. 最终验收：用 5 个不同目标（中英文混合、不同机器人/物体/仿真器）跑通全流程，无 ERROR。

**交付物**：

- [ ] 每周会议纪要；
- [ ] 最终 `docs/third_integration_report.md` 统稿。

---

### B — AI 工程师 / 大模型与智能体

**三联核心职责**：让 `parse_goal` 对常见机器人操作目标稳定产出正确的 `DataReq`。

#### 任务 B1：结构化输出与规则后处理

**要解决的问题**：LLM 输出格式不稳定，不同目标表述导致 `DataReq` 类型错误。

**怎么做**：

1. 修改 [`src/rdi/intelligence/prompts/goal_parsing.py`](../../src/rdi/intelligence/prompts/goal_parsing.py)：
   - 明确要求 LLM 输出 JSON 数组，每个元素包含 `req_type`、`description`、`keywords`、`fallback_sources`；
   - 增加 10+ few-shot 示例，覆盖：Franka/Kinova/UR5 × YCB/EGAD/ModelNet × MuJoCo/Isaac/PyBullet。
2. 修改 [`src/rdi/graph/nodes/parse_goal.py`](../../src/rdi/graph/nodes/parse_goal.py)：
   - 在 LLM 输出后增加 `_normalize_datareq()` 规则后处理：
     - 若 `description` 含 "URDF" / "robot" / "机器人" → 强制 `ROBOT_URDF`；
     - 若含 "mesh" / "3D model" / "模型" / "物体" → 强制 `MESH`；
     - 若含 "grasp" / "抓取" / "抓取姿态" → 强制 `GRASP`；
     - 若含 "MuJoCo" / "Isaac" / "仿真" / "simulation" → 强制 `SIM_CONFIG`。
   - 对无法识别的需求，标记为 `UNKNOWN` 并记录 warning。
3. 增加单元测试覆盖 10+ 目标表述。

**验收标准**：

- [ ] 10 个常见组合中至少 9 个正确产出四类 `DataReq`；
- [ ] 规则后处理单元测试覆盖所有强制映射分支。

#### 任务 B2：查询关键词压缩与缓存

**要解决的问题**：LLM 生成的 `description` 太长，直接当搜索词命中率低。

**怎么做**：

1. 在 [`src/rdi/graph/nodes/retrieve_data.py`](../../src/rdi/graph/nodes/retrieve_data.py) 中实现 `query_compress()`：
   - 调用 LLM 把 `description` 压缩为 1-3 个英文关键词；
   - 若 LLM 不可用，使用规则分词降级（保留英文词、去掉停用词）。
2. 缓存压缩结果到 `state.query_cache`，键为 `description` 的 hash。

**验收标准**：

- [ ] 压缩后关键词平均长度 ≤ 30 字符；
- [ ] 相同目标不重复调用 LLM 压缩。

#### 任务 B3：human_review 反馈理解与目标修正

**怎么做**：

1. 修改 [`src/rdi/graph/nodes/human_review.py`](../../src/rdi/graph/nodes/human_review.py)：
   - 当 `review_decision == "revised"` 时，调用 LLM 把用户反馈转换为新的目标描述或关键词修正；
   - 当 `review_decision == "unsatisfied"` 时，生成更具体的检索建议（如更换数据源）。
2. 与 A 配合定义循环状态字段 `state.user_feedback` 和 `state.revised_goal`。

**验收标准**：

- [ ] 单元测试覆盖 "revised" 和 "unsatisfied" 两种反馈的 LLM 转换结果；
- [ ] 转换后的目标能被 `parse_goal` 重新解析。

---

### C — 数据工程师 / 数据源对接

**三联核心职责**：补齐真实 grasp 数据路径；提升 sim_config 真实场景命中率。

#### 任务 C1：真实 Grasp 数据路径

**要解决的问题**：当前 grasp 是 synthetic / metadata 降级，无真实抓取姿态。

**怎么做（按优先级）**：

1. **GraspNet 单个 `.npz` 下载**：
   - 修改 [`src/rdi/adapters/graspnet.py`](../../src/rdi/adapters/graspnet.py)；
   - 实现 `list_files(item_id)` 列出数据集内文件树；
   - 根据 `object_name` 定位 `grasp_label/` 下对应 object 的 `.npz`；
   - 增加本地缓存：下载后存到 `data/cache/graspnet/`，后续优先从缓存读取。
2. **DexGrasp 单个 `.pkl` 下载**：
   - 修改 [`src/rdi/adapters/dexgrasp.py`](../../src/rdi/adapters/dexgrasp.py)；
   - 类似 GraspNet，定位单个 `.pkl` 并缓存。
3. **YCB-Video grasp 标注备选源**：
   - 新增或复用 YCB 相关路径，尝试获取 `.mat` / `.json` 抓取标注；
   - 作为 GraspNet/DexGrasp 失败时的 fallback。
4. 修改 [`src/rdi/skills/grasp_parse.py`](../../src/rdi/skills/grasp_parse.py)：
   - 支持真实 `.npz` / `.pkl` 解析，输出 `CanonicalGrasp` 列表；
   - 保留 synthetic fallback，但在 `validation_issues` 中标注 `data_source_quality`。

**验收标准**：

- [ ] `scripts/_probe_adapters.py` 中 GraspNet/DexGrasp/YCB-Video 至少一个能返回单个真实 grasp 文件；
- [ ] 该文件可被 `GraspSkill` 解析，且 `data_source_quality="real"`；
- [ ] 本地缓存机制有单元测试。

#### 任务 C2：真实 SimConfig 场景命中率

**要解决的问题**：当前 sim_config 多为最小 MJCF fallback。

**怎么做**：

1. 扩展 [`src/rdi/adapters/mujoco.py`](../../src/rdi/adapters/mujoco.py) fallback 列表：
   - 增加更多 `mujoco_menagerie` 真实场景（如 `franka_emika_panda/scene.xml`、`unitree_go2/scene.xml` 等）；
   - 每条记录标注适用机器人/物体关键词，便于 token 匹配。
2. 修改 [`src/rdi/adapters/isaac.py`](../../src/rdi/adapters/isaac.py)：
   - 增加 Isaac Sim 官方场景到 MJCF/USD 的映射，或返回明确提示说明 Isaac 需单独处理。
3. 与 D 配合：当命中真实 MuJoCo XML 时，Skill 直接返回 XML bytes；未命中时才走最小 MJCF fallback。

**验收标准**：

- [ ] 输入 "Franka Panda in MuJoCo" 时，`MuJoCoAdapter` 能返回真实 `scene.xml`；
- [ ] 未命中真实场景时，最小 MJCF fallback 仍能生成可用 XML。

#### 任务 C3：数据源本地缓存

**怎么做**：

1. 在 [`src/rdi/adapters/base.py`](../../src/rdi/adapters/base.py) 中增加 `BaseAdapter.get_cache_path(item_id)` 和 `BaseAdapter.is_cached(item_id)`；
2. 各 Adapter `fetch()` 优先检查缓存，命中则直接返回；
3. 缓存目录统一放在 `data/cache/<source>/`。

**验收标准**：

- [ ] 至少 Franka、YCB、GraspNet 三个 Adapter 使用统一缓存；
- [ ] 缓存命中时不触发网络请求（可用 mock 测试验证）。

---

### D — 机器人数据工程师 / 格式处理专家

**三联核心职责**：结构化输出目录；实现真实可运行性验证；强化 Skill 对真实 grasp/sim_config 的处理。

#### 任务 D1：数据包目录结构化

**要解决的问题**：当前输出是扁平 `files/` 目录。

**怎么做**：

1. 修改 [`src/rdi/graph/nodes/assemble.py`](../../src/rdi/graph/nodes/assemble.py)：
   - 根据 `ParsedItem.req_type` 映射到子目录：
     - `ROBOT_URDF` → `robots/`
     - `MESH` → `objects/`
     - `GRASP` → `grasps/`
     - `SIM_CONFIG` → `sim_config/`
     - `POLICY_MODEL` → `policies/`
     - `CODE` / `DATASET` / `PAPER` → `resources/`
   - 保持 `req_id` 作为文件名前缀，避免冲突。
2. 同步修改 `manifest.json` 中 `files[].path` 为相对子目录路径。

**验收标准**：

- [ ] 端到端 demo 生成的数据包包含 `robots/`、`objects/`、`grasps/`、`sim_config/`；
- [ ] `manifest.json` 中路径与新目录结构一致。

#### 任务 D2：真实可运行性验证

**要解决的问题**：当前 `validate` 只检查文件能否解析，不检查能否运行。

**怎么做**：

1. 修改 [`src/rdi/graph/nodes/validate.py`](../../src/rdi/graph/nodes/validate.py)：
   - 对 `SIM_CONFIG`（MJCF XML）增加 MuJoCo 加载测试：
     ```python
     import mujoco
     model = mujoco.MjModel.from_xml_string(xml_bytes)
     data = mujoco.MjData(model)
     mujoco.mj_step(model, data)
     ```
   - 对 `ROBOT_URDF` 增加 `yourdfpy` 或 `urdfpy` 解析并检查关节数量；
   - 对 `MESH` 增加 `trimesh.load` 并检查 faces > 0；
   - 对 `GRASP` 检查真实 `.npz`/`.pkl` 字段。
2. 运行时验证结果写入 `validation_issues` 和 `runtime_check`。

**验收标准**：

- [ ] MuJoCo 能加载 sim_config 并运行一步 `mj_step`；
- [ ] 验证失败项 severity 为 ERROR；
- [ ] 新增集成测试覆盖运行时验证。

#### 任务 D3：强化 GraspSkill 真实数据解析

**怎么做**：

1. 修改 [`src/rdi/skills/grasp_parse.py`](../../src/rdi/skills/grasp_parse.py)：
   - 支持 `.npz` 解析：读取 `points`、`scores`、`translations`、`rotations` 等字段；
   - 支持 `.pkl` 解析：兼容 DexGrasp 格式；
   - 统一转换为 `CanonicalGrasp` 列表；
   - 在 `StandardResult.metadata` 中标注 `data_source_quality`。
2. 新增单元测试：
   - 使用 `tests/unit/skills/sample_data/` 中的 sample `.npz` / `.pkl`；
   - 覆盖真实数据路径和 synthetic fallback 路径。

**验收标准**：

- [ ] `.npz` 和 `.pkl` 都能被解析为 `CanonicalGrasp`；
- [ ] synthetic fallback 仍保留且可测试。

#### 任务 D4：强化 SimConfigSkill 真实场景处理

**怎么做**：

1. 修改 [`src/rdi/skills/sim_config.py`](../../src/rdi/skills/sim_config.py)：
   - 当 Adapter 返回真实 MuJoCo XML 时，直接返回 XML bytes；
   - 当需要 fallback 时，生成包含相机、地面、灯光的最小 MJCF（而不仅是机器人+物体）；
   - 支持从 XML 中自动提取机器人/物体引用。
2. 新增单元测试：
   - 真实 XML 路径；
   - minimal MJCF fallback 路径；
   - MuJoCo 可加载性验证。

**验收标准**：

- [ ] 真实 XML 和 minimal MJCF 都能被 MuJoCo 加载；
- [ ] fallback 场景包含地面和相机。

---

### E — 产品工程师 / 集成与交互

**三联核心职责**：实现 human_review 真实闭环；前端进度可视化；数据包目录组织落地。

#### 任务 E1：human_review 真实闭环

**要解决的问题**：当前 `human_review` 是占位节点。

**怎么做**：

1. 修改 [`src/rdi/graph/nodes/human_review.py`](../../src/rdi/graph/nodes/human_review.py)：
   - 当 `review_decision == "satisfied"` → 返回 `END`；
   - 当 `review_decision == "revised"` 或 `"unsatisfied"` → 把用户反馈写入 `state.user_feedback`，调用 B 的反馈修正逻辑，返回状态使 LangGraph 回到 `parse_goal` 或 `retrieve_data`。
2. 与 A 配合在 [`src/rdi/graph/builder.py`](../../src/rdi/graph/builder.py) 中增加条件边：
   - `human_review` → `parse_goal`（revise）
   - `human_review` → `retrieve_data`（unsatisfied，更激进重检索）
   - `human_review` → `END`（satisfied）
3. 在 `manifest.json` 中记录 `revision_history`。

**验收标准**：

- [ ] 用户选择 "revised" 后，系统生成新数据包且 `manifest.json` 中有版本关联；
- [ ] 单元测试覆盖三种 decision 分支。

#### 任务 E2：前端进度与错误可视化

**要解决的问题**：前端只展示最终结果。

**怎么做**：

1. 修改 [`src/rdi/frontend/app.py`](../../src/rdi/frontend/app.py)：
   - 在「真实流程」模式下，实时展示 `state.provenance`；
   - 用表格展示每个 `DataReq` 的状态：解析中 / 检索中 / 成功 / 失败 / 降级；
   - 失败项展示原因和 fallback 来源；
   - 展示最终数据包目录结构和 `validation_issues`。
2. 可选：增加「重新检索」按钮，触发 human_review 循环。

**验收标准**：

- [ ] 前端能看到每个 DataReq 的实时阶段；
- [ ] 失败项有明确原因；
- [ ] 最终数据包文件列表与磁盘一致。

#### 任务 E3：数据包目录组织验收

**怎么做**：

1. 与 D 配合确认目录结构；
2. 在前端展示中按 `robots/`、`objects/`、`grasps/`、`sim_config/` 分组文件；
3. 提供一个「下载数据包」按钮，打包整个目录为 zip。

**验收标准**：

- [ ] 前端展示的分组目录与实际磁盘一致；
- [ ] 下载的 zip 包含完整数据包。

---

### F — 质量工程师 / 持续学习与测试

**三联核心职责**：为所有修改编写测试；跑端到端基准测试；维护 Hermes 经验库。

#### 任务 F1：Grasp / SimConfig 真实路径单元测试

**怎么做**：

1. 为 C 修改的 GraspNet / DexGrasp / YCB Adapter 更新 `tests/unit/adapters/test_*.py`：
   - mock 文件树列表；
   - mock 单个 `.npz` / `.pkl` 下载；
   - 验证缓存命中路径。
2. 为 D 修改的 `GraspSkill` / `SimConfigSkill` 更新 `tests/unit/skills/test_*.py`：
   - 使用 sample `.npz` / `.pkl` / XML；
   - 验证 `CanonicalGrasp` 和 MuJoCo 可加载性。

**验收标准**：

- [ ] 新增代码覆盖率 ≥ 80%；
- [ ] 所有单元测试通过。

#### 任务 F2：端到端基准测试

**怎么做**：

1. 在 `tests/integration/test_third_integration.py` 中新增测试：
   - 5 个目标（中英文混合）：
     - "Franka Panda grasps YCB banana in MuJoCo"
     - "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉"
     - "Kinova Gen3 picks up EGAD mug in Isaac Sim"
     - "UR5 with Robotiq 2F-85 grasps YCB apple"
     - "Franka Panda stacks YCB blocks in PyBullet"
   - mock `parse_goal` 和 Adapter，断言最终包包含四类文件且无 ERROR；
   - 断言 `data_source_quality` 中 grasp 和 sim_config 至少一个为 `real`。
2. 每天跑一次真实网络端到端（非 CI），记录成功率和失败原因。

**验收标准**：

- [ ] 集成测试覆盖 5 个目标；
- [ ] 至少 4/5 目标在 mock 环境下全绿。

#### 任务 F3：Hermes 经验库接入

**怎么做**：

1. 修改 [`src/rdi/hermes/strategy.py`](../../src/rdi/hermes/strategy.py)：
   - 统计「源-需求类型-成功/失败」；
   - 根据成功率动态调整 Adapter 排序。
2. 在 [`src/rdi/graph/nodes/retrieve_data.py`](../../src/rdi/graph/nodes/retrieve_data.py) 中接入动态排序。
3. 新增单元测试验证 Hermes 能根据历史统计调整优先级。

**验收标准**：

- [ ] Hermes 能根据历史成功率推荐备选源；
- [ ] 检索失败时自动尝试历史成功率更高的源。

---

## 5. 技术方案取舍与决策记录

| 问题 | 选项 A | 选项 B | 推荐方案 | 决策理由 |
|---|---|---|---|---|
| grasp 真实数据 | GraspNet 单 `.npz` | DexGrasp 单 `.pkl` | **全部实现，GraspNet 优先** | 多源互补，提高命中率 |
| sim_config 真实性 | 扩展 `mujoco_menagerie` fallback 列表 | 生成更完整的 minimal MJCF | **A 优先，B 兜底** | 真实场景优先，fallback 保证可用性 |
| LLM 稳定性 | 增加 prompt few-shot | 规则后处理强制映射 | **两者结合** | prompt 提高质量，规则兜底保证正确性 |
| human_review 循环 | 回到 `parse_goal` | 回到 `retrieve_data` | **revise → parse_goal，unsatisfied → retrieve_data** | 反馈修正目标 vs 直接换源 |
| 输出目录 | 按 `req_type` 分组 | 保持扁平 | **按 req_type 分组** | 研究人员可直接使用 |
| 运行时验证 | MuJoCo `mj_step` | 仅 XML 解析 | **MuJoCo `mj_step`** | 真实可运行性更重要 |
| 缓存策略 | 每个 Adapter 自己管理 | 统一 `BaseAdapter` 缓存 | **统一 BaseAdapter 缓存** | 减少重复实现，便于测试 |

---

## 6. 联调节奏与里程碑

建议按 **2-3 周** 推进。

### Week 1：真实数据路径与 LLM 稳定化（P0 4.1-4.3）

**目标**： grasp 能拿到真实 `.npz`/`.pkl`，LLM 对 10+ 组合稳定产出正确 DataReq。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 定义数据包规范 | 设计结构化 prompt + 后处理 | GraspNet 单 npz 下载 | GraspSkill npz 解析 | — | 准备 sample 数据 |
| Day 3-4 | 评审 Adapter 修改 | 实现规则后处理 | DexGrasp 单 pkl 下载 | SimConfigSkill 真实 XML 路径 | human_review 循环设计 | 编写单元测试 |
| Day 5 | 主持集成回归 | 跑 10 组合测试 | 探活 grasp 源 | 运行时验证骨架 | — | 全量测试 |

**Week 1 验收**：

- [ ] GraspNet/DexGrasp/YCB 至少一个能返回真实 grasp 文件；
- [ ] 10 组合目标中至少 9 个正确解析；
- [ ] `pytest` 全绿。

### Week 2：闭环、结构化与可运行性（P0 4.4 + P1 4.5-4.7）

**目标**： human_review 闭环可用，数据包结构化，MuJoCo 能运行一步仿真。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 设计循环边 | 反馈修正 LLM 调用 | 数据源统一缓存 | 数据包目录结构化 | 前端进度设计 | 集成测试骨架 |
| Day 3-4 | 处理集成问题 | 多目标回归 | 缓存机制落地 | MuJoCo 运行时验证 | human_review 前端接入 | 集成测试完善 |
| Day 5 | 主持集成回归 | LLM 稳定性调优 | 探活+缓存测试 | 可运行性验证 | 前端真实模式联调 | 全量测试 |

**Week 2 验收**：

- [ ] human_review revised/unsatisfied 能触发重检索；
- [ ] 数据包按 `robots/`/`objects/`/`grasps/`/`sim_config/` 组织；
- [ ] MuJoCo 能加载 sim_config 并运行一步 `mj_step`。

### Week 3：优化、Hermes 与验收（P1-P2）

**目标**： Hermes 源选择上线，前端可视化完成，输出三联报告。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 技术债务清理 | prompt 效果验证 | 缓存性能优化 | Skill 性能优化 | 前端进度展示实现 | Hermes 经验录入 |
| Day 3-4 | 文档统稿 | 多目标鲁棒性测试 | 探活结果更新 | 运行时验证完善 | 数据包下载 zip | 端到端基准测试 |
| Day 5 | 最终验收会议 | 5 目标全跑 | 全源探活 | 全量测试 | 前端最终验收 | 输出测试报告 |

**Week 3 验收**：

- [ ] 5 个端到端目标至少 4 个全绿；
- [ ] Hermes 能根据历史成功率推荐源；
- [ ] 输出 `docs/third_integration_report.md`。

---

## 7. 验证方法

### 7.1 日常验证（每个角色每天做）

```bash
# 1. 代码风格与类型检查
uv run ruff check src tests
uv run ruff format --check src tests
uv run mypy src

# 2. 单元测试
uv run pytest

# 3. Adapter 探活
uv run python scripts/_probe_adapters.py
```

### 7.2 每周验证（周五联调日做）

```bash
# 1. 端到端真实目标
cd c:\Users\yzl13\Documents\GitHub\robot-data-integrator
uv run python -m rdi.frontend.app

# 在「实验目标」输入：
# "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉"
# 选择「真实流程」，点击运行。

# 2. 检查输出包
ls data/output_packages/package-<ts>/
# 期望看到 robots/、objects/、grasps/、sim_config/ 目录

# 3. 外部工具验证
cd data/output_packages/package-<ts>/
python - <<'PY'
import trimesh, mujoco, glob, json
print("urdf:", glob.glob("robots/*"))
print("mesh:", glob.glob("objects/*"))
print("grasp:", glob.glob("grasps/*"))
print("sim_config:", glob.glob("sim_config/*"))
with open(glob.glob("sim_config/*")[0], 'rb') as f:
    model = mujoco.MjModel.from_xml_string(f.read())
    data = mujoco.MjData(model)
    mujoco.mj_step(model, data)
    print("MuJoCo step OK")
PY
```

### 7.3 验收清单

- [ ] 输入 5 个不同目标，至少 4 个生成完整数据包；
- [ ] 数据包包含 `robots/`、`objects/`、`grasps/`、`sim_config/` 目录；
- [ ] 至少一个 grasp 文件 `data_source_quality="real"`；
- [ ] 至少一个 sim_config 能完成 MuJoCo `mj_step`；
- [ ] `human_review` revised/unsatisfied 能触发重检索；
- [ ] `pytest` 全绿；
- [ ] `scripts/_probe_adapters.py` 13/15 以上 fetch 成功；
- [ ] 前端能展示进度、失败原因和最终结果。

---

## 8. 风险与应对

| 风险 | 影响 | 责任人 | 应对 |
|---|---|---|---|
| GraspNet 单 `.npz` 路径不稳定或网络不可用 | 无法获取真实 grasp | C / A | 同时实现 DexGrasp、YCB-Video 备选；本地缓存降低重复依赖 |
| LLM 对复杂目标仍不稳定 | DataReq 类型错误 | B / A | 结构化输出 + 强制规则后处理 + 单元测试覆盖 |
| MuJoCo 运行时验证依赖本地安装 | CI 可能无法运行 | D / F | 运行时验证用可选 marker，本地开发必跑 |
| human_review 循环引入状态管理复杂度 | 可能死循环或状态污染 | A / E | 限制最大循环次数（如 3 次），每次循环清空旧 retrieval_results |
| 多角色同时修改 `builder.py` / `state.py` | 集成冲突 | A | 每日站会同步，周五统一合并回归 |
| 前端进度展示性能差 | 用户体验差 | E / A | 后端提供聚合状态接口，避免前端频繁读取完整 state |

---

## 9. 附录：关键文件速查表

| 职责 | 文件路径 |
|---|---|
| Adapter 基类与注册表 | [src/rdi/adapters/base.py](../../src/rdi/adapters/base.py)、[registry.py](../../src/rdi/adapters/registry.py) |
| 关键 Adapter | [graspnet.py](../../src/rdi/adapters/graspnet.py)、[dexgrasp.py](../../src/rdi/adapters/dexgrasp.py)、[ycb.py](../../src/rdi/adapters/ycb.py)、[mujoco.py](../../src/rdi/adapters/mujoco.py)、[isaac.py](../../src/rdi/adapters/isaac.py) |
| Skill 基类与注册表 | [src/rdi/skills/base.py](../../src/rdi/skills/base.py)、[registry.py](../../src/rdi/skills/registry.py) |
| 关键 Skill | [grasp_parse.py](../../src/rdi/skills/grasp_parse.py)、[sim_config.py](../../src/rdi/skills/sim_config.py) |
| 工作流节点 | [parse_goal.py](../../src/rdi/graph/nodes/parse_goal.py)、[retrieve_data.py](../../src/rdi/graph/nodes/retrieve_data.py)、[human_review.py](../../src/rdi/graph/nodes/human_review.py)、[validate.py](../../src/rdi/graph/nodes/validate.py)、[assemble.py](../../src/rdi/graph/nodes/assemble.py) |
| 图构建 | [src/rdi/graph/builder.py](../../src/rdi/graph/builder.py)、[state.py](../../src/rdi/graph/state.py) |
| 数据模型 | [src/rdi/models/common.py](../../src/rdi/models/common.py)、[goal.py](../../src/rdi/models/goal.py)、[retrieval.py](../../src/rdi/models/retrieval.py)、[parsed.py](../../src/rdi/models/parsed.py)、[manifest.py](../../src/rdi/models/manifest.py) |
| Hermes | [src/rdi/hermes/engine.py](../../src/rdi/hermes/engine.py)、[strategy.py](../../src/rdi/hermes/strategy.py)、[experience_db.py](../../src/rdi/hermes/experience_db.py) |
| 前端 | [src/rdi/frontend/app.py](../../src/rdi/frontend/app.py) |
| 探活脚本 | [scripts/_probe_adapters.py](../../scripts/_probe_adapters.py) |
| 测试目录 | [tests/unit/adapters/](../../tests/unit/adapters/)、[tests/unit/skills/](../../tests/unit/skills/)、[tests/integration/](../../tests/integration/) |

---

## 10. 备注

- 三联不追求覆盖所有数据源，只追求「至少一条真实机器人实验数据路径完全可运行」；
- 所有新增功能必须同步更新单元测试，红线不变；
- 遇到网络不可用的数据源，优先实现备选源和本地缓存，不要把时间耗在无法解决的外部环境上；
- 每周五的集成回归必须全员参加，A 负责主持并记录决策。
