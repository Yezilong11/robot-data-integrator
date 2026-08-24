# Robot Data Integrator — 第二次联调技术指导文档

> 版本：1.0
> 编制日期：2026-08-07
> 目标读者：A/B/C/D/E/F 六位角色
> 依据：
> - [第一次联调报告](../../docs/first_integration_report.md)
> - [第二次联调计划](../../docs/second_integration_plan.md)
> - [项目人员分工与技能要求](file:///E:/智囊腾析微/项目人员分工与技能要求.md)

---

## 1. 文档目的

本文档是第二次联调（以下简称「二联」）的**执行级技术指导书**，回答三个问题：

1. **要解决什么问题**：从「能跑通论文文本包」到「能产出真实机器人实验数据包」之间的关键差距。
2. **要怎么做**：每个角色需要修改哪些文件、采用什么技术方案、按什么顺序推进。
3. **怎么分工协作**：A/B/C/D/E/F 各自的职责边界、交付物、验收标准。

二联的北极星指标：

> **输入一句自然语言目标（如「用 Franka Panda 夹取 YCB 香蕉，在 MuJoCo 中仿真」），系统自动生成一个 `data/output_packages/package-<ts>/`，其中包含可被 `urdfpy`/`trimesh`/`mujoco` 加载的真实文件，而不是只有论文 PDF 或 README。**

---

## 2. 当前状态与关键差距

### 2.1 已具备的基础

- LangGraph 工作流已打通：`parse_goal` → `retrieve_data` → `parse_convert` → `validate` → `assemble_package` → `human_review`。
- 15 个 Adapter 探活基本可用（13/15 fetch 成功）。
- 7 个 Skill 已覆盖 URDF、Mesh、Grasp、SimConfig、Paper、Policy、Sensor。
- 测试、lint、类型检查均通过。

### 2.2 核心差距：Adapter 与 Skill 的格式契约未对齐

第一次联调只验证了「能下载」，没有验证「下载后能被 Skill 消化」。当前主要阻塞点如下：

| 数据类型 | 候选 Adapter 实际返回 | Skill 期望 | 结果 |
|---|---|---|---|
| `ROBOT_URDF` | Franka/Allegro/Robotiq 返回 `.xacro`；MuJoCo 返回 `.xml`（MJCF）；Isaac 返回 `.py` | 纯 URDF 字节 | URDFSkill 无法解析 xacro（缺 ROS xacro 模块）或 python 文件 |
| `MESH` | YCB 返回 `.glb`；GoogleScanned 超时；GraspNet 返回整个 `.tar` | `stl/obj/ply/dae` 单个 mesh | MeshSkill 不支持 glb，GoogleScanned 不可用，GraspNet 不是单个文件 |
| `GRASP` | GraspNet/DexGrasp 返回整个数据集 tar | `.npz`/`.pkl` 单个抓取文件 | GraspSkill 需要单个 npz/pkl |
| `CODE` / `DATASET` | 有 Adapter（GitHub/HF/Zenodo 等），但 [SkillRegistry 未注册 Skill](../../src/rdi/skills/registry.py#L50-L58) | 对应 Skill | parse_convert 直接记为 MissingItem，根本不会触发 Adapter 调用 |

### 2.3 为什么「CODE/DATASET Skill 缺失」是二联的瓶颈

`parse_goal` 拆解出的 `DataReq` 类型决定后续调用哪个 Adapter 和 Skill。当前 [SkillRegistry._factory](../../src/rdi/skills/registry.py#L50-L58) 只注册了：

```python
ROBOT_URDF → URDFSkill
MESH → MeshSkill
GRASP → GraspSkill
SIM_CONFIG → SimConfigSkill
POLICY_MODEL → PolicyInterfaceSkill
SENSOR_DATA → SensorDataSkill
PAPER → PaperSkill
```

`CODE` 和 `DATASET` 没有对应 Skill。因此即使 LLM 正确识别出「需要下载 Franka URDF」「需要下载 YCB mesh」，由于这些需求在系统中实际被归类为 `CODE`/`DATASET`（因为 LLM 把它们理解为「代码仓库」和「数据集」），`parse_convert` 会立刻返回 `MissingItem`，不会调用 Franka/YCB Adapter。

**二联必须让 LLM 能正确产出 `ROBOT_URDF`/`MESH`/`GRASP`/`SIM_CONFIG` 类型的 DataReq，或者在 `CODE`/`DATASET` 下建立到这些真实数据源的映射。**

---

## 3. 角色分工与执行地图

角色定义沿用 [项目人员分工与技能要求](file:///E:/智囊腾析微/项目人员分工与技能要求.md)。以下是二联期间每个角色的具体任务、技术方案与验收标准。

---

### A — 架构师 / 技术负责人

**二联核心职责**：保证 Adapter-Skill-Workflow 三层接口契约一致；主持联调节奏；决策技术取舍。

#### 任务 A1：明确二联数据流契约

**要解决的问题**：当前 `RawData.format` 与 Skill 的输入格式存在歧义，例如 `format="urdf"` 实际可能是 xacro，`format="glb"` MeshSkill 不支持。

**怎么做**：

1. 在 [src/rdi/models/retrieval.py](../../src/rdi/models/retrieval.py) 的 `RawData` 中增加可选字段 `content_hint: str | None`，用于标注「这个二进制数据的实际语义」（如 `xacro`, `mjcf`, `glb`, `dataset_tar`, `model_info_json`）。不要破坏现有字段。
2. 更新 [src/rdi/graph/nodes/parse_convert.py](../../src/rdi/graph/nodes/parse_convert.py) 的 `_FORMAT_TO_REQ_TYPE` 映射，补充 `glb → MESH`、`python → SIM_CONFIG`、`zip → MESH`（GoogleScanned zip 解压后取 mesh）。
3. 与 D 一起定义「Adapter 失败/降级」到 `MissingItem` 的标准格式，确保 `reason` 字段可被前端和用户理解。

**验收标准**：

- [ ] `RawData` 模型可扩展，不破坏现有 282 个单元测试；
- [ ] `parse_convert` 能正确将 xacro/glb/python/zip 等格式路由到对应 Skill 或给出明确 MissingItem 原因。

#### 任务 A2：主持每日/每周联调站会

**怎么做**：

1. 每天 15 分钟同步：每个角色汇报「昨天完成什么、今天做什么、阻塞在哪」。
2. 每周五下午做集成回归：所有人把当周修改合并到 `main` 或临时联调分支，跑 `pytest` + `scripts/_probe_adapters.py` + `scripts/demo_paper_pipeline.py`。
3. 阻塞决策：当 C 发现某个数据源确实无法在当前网络下使用时，A 拍板是否替换源、降级或延后到第三轮。

**交付物**：

- [ ] 每周联调会议纪要；
- [ ] 最终 `docs/second_integration_report.md` 统稿。

---

### B — AI 工程师 / 大模型与智能体

**二联核心职责**：让 `parse_goal` 能正确识别机器人实验目标并产出可直接映射到真实数据源的 `DataReq`；优化查询关键词。

#### 任务 B1：优化 `parse_goal` 的 DataReq 类型识别

**要解决的问题**：LLM 容易把「Franka URDF」识别为 `CODE`（因为来源是 GitHub），把「YCB mesh」识别为 `DATASET`，导致无 Skill 处理。

**怎么做**：

1. 修改 [src/rdi/intelligence/prompts/goal_parsing.py](../../src/rdi/intelligence/prompts/goal_parsing.py) 中的 `GOAL_PARSING_SYSTEM`，在 schema 说明后增加 few-shot 示例，明确要求：
   - 机器人本体描述文件 → `robot_urdf`
   - 物体三维模型 → `mesh`
   - 抓取姿态数据 → `grasp`
   - 仿真场景配置 → `sim_config`
   - 代码仓库/算法实现 → `code`
   - 数据集/基准 → `dataset`
2. 利用 DataReq 已有的 `fallback_sources` 字段：让 LLM 把最优先的数据源放在第一位，例如 `fallback_sources: ["franka", "github"]`。在 [src/rdi/graph/nodes/retrieve_data.py](../../src/rdi/graph/nodes/retrieve_data.py) 中按 `fallback_sources` 顺序尝试源，而不是按 registry 全局顺序。
3. 在 [src/rdi/graph/nodes/parse_goal.py](../../src/rdi/graph/nodes/parse_goal.py) 中增加后处理：如果 LLM 把 `robot_urdf`/`mesh`/`grasp`/`sim_config` 错误识别为 `code`/`dataset`，根据 `expected_format` 或 `description` 中的关键词强制修正。

**参考文件**：

- Prompt 模板：[src/rdi/intelligence/prompts/goal_parsing.py](../../src/rdi/intelligence/prompts/goal_parsing.py)
- 目标解析逻辑：[src/rdi/graph/nodes/parse_goal.py](../../src/rdi/graph/nodes/parse_goal.py)
- DataReq 模型：[src/rdi/models/goal.py](../../src/rdi/models/goal.py)

**验收标准**：

- [ ] 输入「Franka Panda + YCB banana + MuJoCo」目标，产出的 DataReq 列表中至少包含一个 `ROBOT_URDF`、一个 `MESH`、一个 `SIM_CONFIG`；
- [ ] 不再出现把 URDF/mesh 识别为 `CODE`/`DATASET` 的情况（可用单元测试断言）。

#### 任务 B2：查询关键词压缩

**要解决的问题**：LLM 生成的描述太长，直接当搜索词导致 Adapter 命中率低。

**怎么做**：

1. 在 `retrieve_data` 节点中，对每个 `DataReq` 增加一个 `query_compress()` 步骤，调用 LLM 把 `description` 压缩为 1-3 个关键词。
2. Prompt 示例：
   ```text
   把下面的研究目标描述压缩成适合在数据源搜索的 1-3 个关键词，只返回逗号分隔的列表：
   输入：The Franka Emika Panda 7-DOF collaborative robot arm URDF model
   输出：Franka Panda URDF
   ```
3. 缓存压缩结果到 `state.query_cache`，避免同一目标重复调用 LLM。

**验收标准**：

- [ ] 压缩后关键词平均长度不超过 30 字符；
- [ ] 相同目标下 Adapter search 命中率不低于第一次联调。

#### 任务 B3：Hermes 策略演化（可选，P1）

**怎么做**：

1. 在二联中先让 [src/rdi/hermes/strategy.py](../../src/rdi/hermes/strategy.py) 能记录「源 → 需求类型 → 是否成功」的统计；
2. 当 `retrieve_data` 失败时，Hermes 根据历史统计推荐下一个备选源。

**验收标准**：

- [ ] 有单元测试验证 Hermes 能根据历史成功率调整源优先级。

---

### C — 数据工程师 / 数据源对接

**二联核心职责**：修复 Adapter，让真实 URDF/mesh/grasp/sim_config 能被稳定取回，并且返回 Skill 能消化的格式。

#### 任务 C1：修复真实 URDF 来源

**要解决的问题**：Franka/Allegro/Robotiq 返回 xacro，MuJoCo/Isaac 返回非 URDF。

**怎么做（按优先级）**：

1. **FrankaAdapter 优先修复**（最常用）：
   - 修改 [src/rdi/adapters/franka.py](../../src/rdi/adapters/franka.py)；
   - 路径 B fallback 直接提供已展开纯 URDF 的 raw URL：`https://raw.githubusercontent.com/justagist/panda_simulator/master/panda_description/robots/panda.urdf`（需验证路径是否真实存在）；
   - 如果该 URL 不存在，改为下载整个仓库 zip，解压后找到 `.urdf` 文件读取。
2. **AllegroAdapter / RobotiqAdapter 同步修复**：
   - 同样改为下载仓库并定位已展开 URDF，或提供稳定 raw URL。
3. **MuJoCoAdapter / IsaacSimAdapter 处理**：
   - 对于 `ROBOT_URDF` 类型，这两个源不应作为 URDF 源返回；应把 `SIM_CONFIG` 和 `ROBOT_URDF` 的 registry 映射拆开，或在 Adapter 内根据 `DataReqType` 决定是否返回。
   - 修改 [src/rdi/adapters/registry.py](../../src/rdi/adapters/registry.py) 中 `ROBOT_URDF` 的候选顺序，把 MuJoCo/Isaac 移到 `SIM_CONFIG` 的候选中，或从 `ROBOT_URDF` 中移除。

**验收标准**：

- [ ] `scripts/_probe_adapters.py` 中 Franka/Allegro/Robotiq 至少有一个 `fetch_ok=true` 且返回纯 URDF 字节；
- [ ] 该 URDF 可被 `URDFSkill` 解析（不报错）；
- [ ] 新增/更新对应单元测试。

#### 任务 C2：修复真实 Mesh 来源

**要解决的问题**：YCB 返回 `.glb`、GoogleScanned 超时、GraspNet 返回整个 tar。

**怎么做（按优先级）**：

1. **YCBAdapter 改拉 `.obj` 或 `.stl`**（最快）：
   - 修改 [src/rdi/adapters/ycb.py](../../src/rdi/adapters/ycb.py) 的 fetch 逻辑；
   - `ai-habitat/ycb` 数据集同时提供 `google_16k/textured.obj` 和 `.glb`，把 fetch URL 从 `.glb` 改为 `.obj`；
   - 如果官方路径没有 `.obj`，尝试 `google_16k/nontextured.obj` 或 `tsdf/textured.obj`。
2. **GoogleScannedAdapter 超时修复**：
   - 修改 [src/rdi/adapters/google_scanned.py](../../src/rdi/adapters/google_scanned.py)；
   - 当前下载的是完整 `.zip`（含 model.config + meshes/），体积可能较大；改为只下载 `meshes/` 下的 `.obj`/`.dae` 文件；
   - 如果 Fuel API 单个文件下载仍超时，增加 chunked 下载、超时重试、或换用 jsdelivr 等 CDN 镜像；
   - 若实在无法在当前网络下使用，A 与 E 共同决策：标记为 P2 或提供本地文件上传入口。
3. **GraspNetAdapter 单个 mesh 定位**：
   - 当需求类型为 `MESH` 时，只列 `models/` 或 `mesh/` 目录下的 `.obj`/`.ply` 文件，不要下载整个 `collision_label.tar`。

**验收标准**：

- [ ] `scripts/_probe_adapters.py` 中 YCB/GoogleScanned/GraspNet 至少有一个 `fetch_ok=true` 且返回 MeshSkill 支持的格式；
- [ ] 该 mesh 可被 `trimesh.load` 加载；
- [ ] 新增/更新对应单元测试。

#### 任务 C3：数据集类 Adapter 的 metadata 与单个文件拆分

**要解决的问题**：GraspNet/DexGrasp 返回整个 tar，Skill 无法处理。

**怎么做**：

1. 在 `BaseAdapter` 或具体 Adapter 中增加 `list_files(item_id)` 接口，返回数据集内文件树；
2. `fetch` 根据 `DataReqType` 决定下载策略：
   - `GRASP` → 下载 `grasp_label/` 下对应 object 的 `.npz`；
   - `MESH` → 下载 `models/` 下对应 object 的 `.obj`/`.ply`；
   - `DATASET` → 返回 metadata JSON（描述、下载链接、文件列表），交给 D 的 `DatasetSkill` 处理。

**验收标准**：

- [ ] GraspNet/DexGrasp 在 `GRASP` 类型下能返回单个 npz/pkl；
- [ ] 在 `DATASET` 类型下返回 metadata JSON。

---

### D — 机器人数据工程师 / 格式处理专家

**二联核心职责**：补齐 `CODE`/`DATASET` Skill；强化现有 Skill 对真实数据格式的兼容性；实现深度校验。

#### 任务 D1：实现 `CODE` Skill

**要解决的问题**：`SkillRegistry` 未注册 `CODE` Skill，代码类需求无法落盘。

**怎么做**：

1. 新建 [src/rdi/skills/code_parse.py](../../src/rdi/skills/code_parse.py)；
2. `process(data, fmt, **kwargs)` 支持：
   - `markdown`（GitHub README）：提取标题、依赖、安装说明、文件结构；
   - `json`（HF config）：提取框架、模型类型、任务；
   - `zip`/`tar`（仓库压缩包）：列出文件树，提取 README 和关键代码文件。
3. 输出 `StandardResult`，`canonical_format="CodeRepoSummary"`，`data` 包含：
   ```python
   {
       "repo_url": str,
       "readme_text": str,
       "file_tree": list[str],
       "framework": str | None,
       "installation": str | None,
   }
   ```
4. 在 [src/rdi/skills/registry.py](../../src/rdi/skills/registry.py) 中注册：`DataReqType.CODE → CodeSkill`。

**验收标准**：

- [ ] 输入 GitHub README 或 HF config 能生成 `CodeRepoSummary`；
- [ ] `parse_convert` 对 `CODE` 类型不再返回 MissingItem；
- [ ] 单元测试覆盖 README/markdown 和 JSON 两种路径。

#### 任务 D2：实现 `DATASET` Skill

**要解决的问题**：`SkillRegistry` 未注册 `DATASET` Skill，数据集类需求无法落盘。

**怎么做**：

1. 新建 [src/rdi/skills/dataset_parse.py](../../src/rdi/skills/dataset_parse.py)；
2. `process(data, fmt, **kwargs)` 支持：
   - `json`（Zenodo/HF/GraspNet metadata）：提取标题、描述、下载链接、文件列表、许可证；
   - `tar`/`zip`：列出文件树，提取元数据；
   - 如果 metadata 中包含单个 mesh/grasp 文件链接，可调用 `MeshSkill`/`GraspSkill` 进一步处理。
3. 输出 `StandardResult`，`canonical_format="DatasetSummary"`，`data` 包含：
   ```python
   {
       "title": str,
       "description": str,
       "download_url": str | None,
       "file_tree": list[str],
       "license": str | None,
   }
   ```
4. 在 `SkillRegistry` 中注册：`DataReqType.DATASET → DatasetSkill`。

**验收标准**：

- [ ] 输入 Zenodo/GraspNet metadata JSON 能生成 `DatasetSummary`；
- [ ] `parse_convert` 对 `DATASET` 类型不再返回 MissingItem；
- [ ] 单元测试覆盖 metadata JSON 路径。

#### 任务 D3：强化 URDFSkill 对 xacro 的兼容性

**要解决的问题**：Franka 等 Adapter 返回 xacro，当前 URDFSkill 只有在安装了 ROS `xacro` 模块时才能展开。

**怎么做**：

1. 在 [src/rdi/skills/urdf_convert.py](../../src/rdi/skills/urdf_convert.py) 的 `_handle_xacro` 中，如果 `xacro` 模块不可用，尝试**字符串级简单替换**：
   - 移除 `<xacro:` 标签；
   - 替换 `$(find package_name)` 为占位路径；
   - 给出 warning 说明这是降级处理。
2. 更稳妥的方案是与 C 配合，让 Adapter 直接返回已展开 URDF（推荐）。Skill 侧只做兜底。

**验收标准**：

- [ ] 无 ROS xacro 环境下，Franka xacro 能被解析或给出明确降级原因；
- [ ] 有 ROS xacro 环境下，xacro 正常展开。

#### 任务 D4：强化 MeshSkill 对 glb/zip 的兼容性

**要解决的问题**：YCB 可能继续返回 glb，GoogleScanned 返回 zip。

**怎么做**：

1. 在 [src/rdi/skills/mesh_process.py](../../src/rdi/skills/mesh_process.py) 中增加：
   - `glb` 支持：使用 `trimesh.load(..., force="mesh")`，trimesh 本身支持 glb；
   - `zip` 支持：解压后找到第一个支持的 mesh 文件（stl/obj/ply/dae/glb）处理。
2. 或者与 C 配合，让 Adapter 直接返回单个 obj/stl（推荐）。Skill 侧做兜底。

**验收标准**：

- [ ] MeshSkill 能处理 `glb` 和 `zip` 输入；
- [ ] 新增单元测试用 `tests/unit/skills/sample_data/` 中的 glb/zip 样本。

#### 任务 D5：实现格式深度校验

**要解决的问题**：当前 `validate` 节点只检查空值、完整度、置信度、缺失项，不验证文件能否被外部工具加载。

**怎么做**：

1. 修改 [src/rdi/graph/nodes/validate.py](../../src/rdi/graph/nodes/validate.py)；
2. 对每个 `ParsedItem` 增加「可加载性」检查：
   - `ROBOT_URDF`：用 `urdfpy` 或 `yourdfpy` 解析（优先用项目已用的 lxml 做二次校验）；
   - `MESH`：用 `trimesh.load` 加载，检查 faces > 0；
   - `SIM_CONFIG`：用 `lxml` 解析 XML，或 Python 文件做语法检查（`ast.parse`）；
   - `GRASP`：检查 npz/pkl 中必要字段存在。
3. 校验失败写入 `validation_issues`， severity 为 ERROR。

**验收标准**：

- [ ] `validate` 节点能对 URDF/mesh/sim_config/grasp 做可加载性校验；
- [ ] 校验结果出现在 `manifest.json` 的 `validation_issues` 中；
- [ ] 新增集成测试覆盖校验路径。

---

### E — 产品工程师 / 集成与交互

**二联核心职责**：前端进度展示、human_review 真实闭环、数据包目录组织、联调报告可视化。

#### 任务 E1：前端进度与日志展示（P2）

**要解决的问题**：前端只展示最终结果，用户看不到当前检索哪个源、为什么失败。

**怎么做**：

1. 修改 [src/rdi/frontend/app.py](../../src/rdi/frontend/app.py)；
2. 在「真实流程」模式下，使用 `gr.Textbox` 或 `gr.JSON` 实时展示 `state.provenance` 日志；
3. 增加阶段指示器：解析 → 检索 → 解析转换 → 校验 → 打包 → 审查；
4. 每个 `DataReq` 展示：需求类型、目标 Adapter、成功/失败状态、失败原因。

**验收标准**：

- [ ] 前端能看到每个阶段的进度；
- [ ] 失败项有明确原因展示。

#### 任务 E2：实现 `human_review` 真实闭环

**要解决的问题**：当前 `human_review` 只是占位节点，用户反馈不触发任何重检索。

**怎么做**：

1. 修改 [src/rdi/graph/nodes/human_review.py](../../src/rdi/graph/nodes/human_review.py)；
2. 当 `review_decision == "revised"` 或 `"unsatisfied"` 时：
   - 把用户反馈追加到 `state.user_feedback`；
   - 调用 LLM 根据反馈生成修正后的目标/关键词；
   - 返回状态使 LangGraph 循环回到 `retrieve_data` 节点。
3. 需要 A 配合在 [src/rdi/graph/builder.py](../../src/rdi/graph/builder.py) 中增加条件边：`human_review` → `retrieve_data`（循环）或 `END`。

**验收标准**：

- [ ] 用户给差评后，系统能重新检索并生成新的数据包；
- [ ] 新结果与旧结果在 `manifest.json` 中有版本关联。

#### 任务 E3：数据包目录组织

**要解决的问题**：当前数据包只有 `files/` 扁平目录，不便于研究人员直接使用。

**怎么做**：

1. 修改 [src/rdi/graph/nodes/assemble.py](../../src/rdi/graph/nodes/assemble.py)；
2. 按类型组织输出目录：
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
3. `ParsedItem.output_path` 决定文件放入哪个子目录；如果 `output_path` 为空，按 `req_type` 默认映射。

**验收标准**：

- [ ] 生成的数据包有按类型组织的目录；
- [ ] `manifest.json` 中文件路径与目录结构一致。

---

### F — 质量工程师 / 持续学习与测试

**二联核心职责**：为每个修改编写/更新测试；跑集成测试；记录 Hermes 经验数据。

#### 任务 F1：Adapter 与 Skill 单元测试

**怎么做**：

1. 为 C 修改的每个 Adapter 更新 `tests/unit/adapters/test_<adapter>.py`；
   - 正常路径：mock HTTP 返回真实格式（xacro/obj/glb/zip）；
   - 异常路径：超时、404、格式不支持；
   - 使用 `respx` 或 `unittest.mock.AsyncMock`，禁止真实网络请求。
2. 为 D 新增的 `CodeSkill`/`DatasetSkill` 编写 `tests/unit/skills/test_code_parse.py`、`tests/unit/skills/test_dataset_parse.py`。
3. 在 `tests/unit/skills/sample_data/` 补充：
   - `code/`：一个简单 repo 的 README + 文件树；
   - `dataset/`：一个 metadata JSON 样本。

**验收标准**：

- [ ] 新增代码覆盖率不低于 80%；
- [ ] 所有单元测试通过。

#### 任务 F2：集成测试覆盖真实数据路径

**怎么做**：

1. 在 `tests/integration/test_second_integration.py` 中新增测试：
   - mock `parse_goal` 返回「Franka + YCB + MuJoCo」DataReq 列表；
   - mock 各 Adapter 返回真实格式数据；
   - 断言最终 `files/` 非空且包含 URDF、mesh、sim_config 至少两类。
2. 使用 `tests/unit/skills/sample_data/` 中的真实样本作为 mock 数据。

**验收标准**：

- [ ] 集成测试能跑通完整链路；
- [ ] 测试不依赖真实网络。

#### 任务 F3：Hermes 经验库录入

**怎么做**：

1. 在每次二联测试运行后，把「源-需求类型-成功率」写入 [src/rdi/hermes/experience_db.py](../../src/rdi/hermes/experience_db.py)；
2. 为二联建立一个专用 collection：`second_integration_experiences`。

**验收标准**：

- [ ] 有二联期间的源成功率统计；
- [ ] Hermes 能根据统计推荐备选源。

---

## 4. 联调节奏与里程碑

建议按 **3 周** 推进，与 [第二次联调计划](../../docs/second_integration_plan.md) 保持一致。

### Week 1：补齐数据类型与真实数据来源（P0 3.1-3.4）

**目标**：让系统能正确请求、获取、解析真实 URDF/mesh。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 确定数据流契约修改 | 优化 parse_goal prompt | 修复 Franka/Allegro/Robotiq URDF | 实现 CodeSkill | — | 准备测试夹具 |
| Day 3-4 | 评审 Adapter 修改 | 实现查询关键词压缩 | 修复 YCB/GoogleScanned Mesh | 实现 DatasetSkill | 前端进度设计 | 编写单元测试 |
| Day 5 | 主持集成回归 | 验证 DataReq 类型识别 | 探活脚本全绿 | 注册 Skill | — | 跑全量测试 |

**Week 1 验收**：

- [ ] `scripts/_probe_adapters.py` 中至少一个 URDF 源和一个 Mesh 源可被对应 Skill 消化；
- [ ] `pytest` 全绿；
- [ ] 能生成 code-only / dataset-only 数据包。

### Week 2：端到端真实场景（P0 3.5 + P1 3.6-3.7）

**目标**：跑通「Franka + YCB + MuJoCo」完整流程。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 协调 A-B-C-D 接口 | 端到端 prompt 调优 | 支持 GraspNet 单个 npz | 强化 URDFSkill/MeshSkill | 前端接入真实数据 | 集成测试骨架 |
| Day 3-4 | 处理循环边 | 实现 revise 关键词修正 | 数据集 metadata 拆分 | 实现格式深度校验 | human_review 闭环设计 | 集成测试完善 |
| Day 5 | 主持集成回归 | 跑多轮目标验证 | 探活+冒烟 | 校验规则单元测试 | 前端真实模式联调 | 跑全量测试 |

**Week 2 验收**：

- [ ] 用「Franka + YCB + MuJoCo」目标生成包含至少两类真实文件的数据包；
- [ ] URDF 可被解析，mesh 可被 trimesh 加载；
- [ ] revise 闭环可触发重检索。

### Week 3：优化与验收（P1 3.8 + P2 3.9-3.11）

**目标**：补齐优化项，全量回归，输出联调报告。

| 天数 | A | B | C | D | E | F |
|---|---|---|---|---|---|---|
| Day 1-2 | 技术债务清理 | Hermes 策略统计 | IEEE Key 配置（如有） | PaperSkill warning 修复 | 前端进度展示实现 | Hermes 经验录入 |
| Day 3-4 | 文档统稿 | 关键词压缩效果验证 | 探活结果更新 | Skill 性能优化 | 数据包目录组织 | 端到端基准测试 |
| Day 5 | 最终验收会议 | 多目标测试 | 全源探活 | 全量测试 | 前端最终验收 | 输出测试报告 |

**Week 3 验收**：

- [ ] 全量单元测试 + 集成测试 + 探活通过；
- [ ] 输出 `docs/second_integration_report.md`；
- [ ] 生成至少一个真实机器人实验数据包样例。

---

## 5. 技术方案取舍与决策记录

| 问题 | 选项 A | 选项 B | 推荐方案 | 决策理由 |
|---|---|---|---|---|
| YCB 返回 `.glb` | C 改 Adapter 拉 `.obj` | D 扩展 MeshSkill 支持 glb | **优先 A，B 兜底** | Adapter 层解决格式问题最轻量；Skill 支持 glb 作为兼容性兜底 |
| Franka 返回 xacro | C 改 Adapter 拉已展开 URDF | D 在 Skill 展开 xacro | **优先 A，B 兜底** | 已展开 URDF 更稳定；Skill 侧做无 ROS 环境兜底 |
| GraspNet 整个 tar | C 拆分为单个 npz 下载 | D 在 Skill 中按需解压 | **优先 A** | 避免下载几十 GB 数据到本地 |
| CODE/DATASET Skill | 单独实现 | 合并为一个通用 Skill | **单独实现** | 两者输出语义不同，合并会导致下游使用混乱 |
| human_review 闭环 | 前端触发重跑 | LangGraph 内部循环 | **LangGraph 内部循环** | 更符合工作流设计，状态可追溯 |

---

## 6. 风险与应对

| 风险 | 影响 | 责任人 | 应对 |
|---|---|---|---|
| GoogleScanned 在当前网络下始终超时 | 缺少 mesh 源 | C / A | 优先修好 YCB；若 GoogleScanned 仍不可用，标记为 P2 或提供本地上传 |
| LLM 持续把 URDF/mesh 识别为 CODE/DATASET | 真实数据不会被请求 | B / A | 增加 prompt few-shot + 后处理规则强制映射 |
| xacro 展开依赖 ROS 环境 | URDFSkill 失败 | D / C | Adapter 直接返回已展开 URDF，Skill 做字符串级降级 |
| GraspNet 单个 npz 路径不稳定 | grasp 数据缺失 | C / F | 准备 DexGrasp/YCB 备选源；测试用录制的文件树结构 |
| 前端真实模式依赖后端异常兜底 | 用户体验差 | E / A | 明确错误状态展示，不生成假数据包 |
| 多角色并行修改冲突 | 集成困难 | A | 每日站会 + 每周五统一合并回归 |

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
# "用 Franka Panda 夹取 YCB 香蕉，在 MuJoCo 中仿真"
# 选择「真实流程」，点击运行。

# 2. 检查输出包
ls data/output_packages/package-<ts>/
# 期望看到 robots/、objects/、sim_config/ 等目录

# 3. 外部工具验证
cd data/output_packages/package-<ts>/
python - <<'PY'
import trimesh, urdfpy, glob
print("meshes:", glob.glob("objects/*"))
print("urdf:", glob.glob("robots/*"))
mesh = trimesh.load(glob.glob("objects/*")[0])
print("mesh faces:", len(mesh.faces))
PY
```

### 7.3 验收清单

- [ ] 输入「Franka + YCB + MuJoCo」目标生成数据包；
- [ ] 数据包包含至少两类真实文件（URDF / mesh / grasp / sim_config）；
- [ ] 至少一个 URDF 可被 `urdfpy` 解析；
- [ ] 至少一个 mesh 可被 `trimesh` 加载；
- [ ] `missing_items` 每项有明确原因；
- [ ] `pytest` 全绿；
- [ ] `scripts/_probe_adapters.py` 13/15 以上 fetch 成功；
- [ ] 前端能展示进度与最终结果。

---

## 8. 附录：关键文件速查表

| 职责 | 文件路径 |
|---|---|
| Adapter 基类与注册表 | [src/rdi/adapters/base.py](../../src/rdi/adapters/base.py)、[registry.py](../../src/rdi/adapters/registry.py) |
| 关键 Adapter | [franka.py](../../src/rdi/adapters/franka.py)、[ycb.py](../../src/rdi/adapters/ycb.py)、[google_scanned.py](../../src/rdi/adapters/google_scanned.py)、[graspnet.py](../../src/rdi/adapters/graspnet.py)、[dexgrasp.py](../../src/rdi/adapters/dexgrasp.py) |
| Skill 基类与注册表 | [src/rdi/skills/base.py](../../src/rdi/skills/base.py)、[registry.py](../../src/rdi/skills/registry.py) |
| 关键 Skill | [urdf_convert.py](../../src/rdi/skills/urdf_convert.py)、[mesh_process.py](../../src/rdi/skills/mesh_process.py)、[grasp_parse.py](../../src/rdi/skills/grasp_parse.py)、[sim_config.py](../../src/rdi/skills/sim_config.py) |
| 工作流节点 | [src/rdi/graph/nodes/parse_goal.py](../../src/rdi/graph/nodes/parse_goal.py)、[retrieve_data.py](../../src/rdi/graph/nodes/retrieve_data.py)、[parse_convert.py](../../src/rdi/graph/nodes/parse_convert.py)、[validate.py](../../src/rdi/graph/nodes/validate.py)、[assemble.py](../../src/rdi/graph/nodes/assemble.py)、[human_review.py](../../src/rdi/graph/nodes/human_review.py) |
| 数据模型 | [src/rdi/models/common.py](../../src/rdi/models/common.py)、[goal.py](../../src/rdi/models/goal.py)、[retrieval.py](../../src/rdi/models/retrieval.py)、[parsed.py](../../src/rdi/models/parsed.py)、[manifest.py](../../src/rdi/models/manifest.py) |
| 前端 | [src/rdi/frontend/app.py](../../src/rdi/frontend/app.py) |
| 探活脚本 | [scripts/_probe_adapters.py](../../scripts/_probe_adapters.py) |
| 测试目录 | [tests/unit/adapters/](../../tests/unit/adapters/)、[tests/unit/skills/](../../tests/unit/skills/)、[tests/integration/](../../tests/integration/) |

---

## 9. 备注

- 所有新增 Skill/Adapter 修改必须同步更新对应单元测试，这是二联的红线；
- 遇到网络不可用的数据源，优先修替代源，不要把时间耗在无法解决的外部环境上；
- 二联不追求覆盖所有数据源，只追求「至少有一条真实机器人数据路径完全跑通」；
- 每周五的集成回归必须全员参加，A 负责主持并记录决策。
