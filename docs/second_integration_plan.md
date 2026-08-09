# Robot Data Integrator — 第二次联调计划

> 编制日期：2026-08-07  
> 依据：[第一次联调报告](first_integration_report.md)  
> 目标：让系统产出**非空的机器人实验数据包**（含 URDF / mesh / grasp / sim_config 等真实文件），而不仅是论文文本。

## 1. 联调目标

**最终目标**：让研究人员能够日常使用 RDI 准备机器人实验，输入自然语言目标后拿到可直接用于仿真或实物实验的结构化数据包。

在第一次联调已打通 E2E 链路的基础上，第二次联调聚焦**“真实机器人实验数据”的获取、解析与落盘**：

1. 补齐对 `CODE` 和 `DATASET` 两类数据需求的 Skill 支持；
2. 修复或绕过导致真实 mesh/URDF 数据源不可用的阻塞问题；
3. 用典型机器人实验目标（Franka + YCB + MuJoCo）跑通完整流程；
4. 让输出包中的文件可被外部工具验证（MuJoCo / trimesh / URDF 解析器）。

## 1.1 关键差距：真实数据来源与 Adapter-Skill 格式契约未对齐

第一次联调验证了“能下载论文文本”，但没有验证“下载回来的机器人数据能被系统消化”。当前的核心问题不是“不知道源在哪”，而是 **Adapter 返回的数据格式与 Skill 能处理的格式对不上**。

### URDF 来源现状

| 候选源 | 实际 fetch 内容 | 问题 |
|--------|----------------|------|
| `FrankaAdapter` | `panda.urdf.xacro` | 是 xacro 宏文件，不是纯 URDF；需要 ROS `xacro` 模块才能展开，且通常依赖同仓库的 mesh/include 文件 |
| `AllegroAdapter` / `RobotiqAdapter` | 同样是 `.xacro` | 与 Franka 相同问题 |
| `MuJoCoAdapter` | `aloha.xml` | 是 MJCF 格式，不是 URDF |
| `IsaacSimAdapter` | `franka.py` | 是 IsaacLab 的 Python 资产配置，不是 URDF |
| `GitHubAdapter` | 仓库 README | 没有机制定位并下载仓库内具体 `.urdf` 文件 |

**结论**：当前没有一个源能稳定返回可直接解析的纯 URDF 文件。

### Mesh 来源现状

| 候选源 | 实际 fetch 内容 | 问题 |
|--------|----------------|------|
| `YCBAdapter` | `textured.glb` | `MeshSkill` 只支持 `stl/obj/ply/dae`，**不支持 `.glb`** |
| `GoogleScannedAdapter` | `.zip` 压缩包 | **超时**（>30s），探活 `fetch_ok=false`；这是设计里专门给 mesh 准备的源 |
| `GraspNetAdapter` | `collision_label.tar`（31GB） | 是整个数据集的 tar 包，不是单个 mesh 文件 |

**结论**：Mesh 也没有可用的真实来源。

### Grasp / SimConfig 类似问题

- **Grasp**：GraspNet / DexGrasp 返回的是 `.tar`/`.tar.gz` 数据集（几十 GB），不是单个 `.npz`/`.pkl` 抓取姿态文件；
- **SimConfig**：MuJoCo / Isaac 返回的是场景级 XML / Python，不是某个统一格式的 `sim_config`。

### 为什么 CODE/DATASET Skill 是阻塞项

目前 `SkillRegistry` 未注册 `CODE` 和 `DATASET` Skill（见 [registry.py](../src/rdi/skills/registry.py#L50-L58)）。这意味着 LLM 即使从自然语言目标中识别出需要机器人模型或物体 mesh，也会因为 `parse_convert` 找不到对应 Skill 而直接记为 `MissingItem`，根本不会去调用 Franka/YCB/GoogleScanned 等 Adapter。所以**补齐 CODE/DATASET Skill 是让真实数据被请求的前提**。

## 2. 范围边界

### 2.1 在范围内

- `CODE` / `DATASET` Skill 的实现与注册；
- `GoogleScannedAdapter` 超时问题诊断与修复；
- 真实机器人数据包端到端生成（Franka / YCB / GraspNet / MuJoCo 组合）；
- URDF / mesh / grasp / sim_config 等格式的深度校验；
- `revise` 节点从“记录反馈”升级为“驱动重检索”；
- 查询关键词压缩，提升 Adapter 命中率。

### 2.2 不在范围内（建议第三轮）

- 多目标并发/大规模批量生成；
- 数据包版本管理与增量更新；
- 完整的前端可视化编辑器；
- 新的外部数据源接入（IEEE 等需先配置 API Key）。

## 3. 任务清单

### P0 — 第二轮必须完成（阻塞验收）

| 任务 | 负责人 | 验收标准 | 建议时间 |
|------|--------|----------|----------|
| **3.1 补齐 `CODE` Skill** | 后端/Skill | 注册表中新增 `CodeSkill`；能从 GitHub 等源解析 README + 文件结构并写入 `files/`；能识别并分发 `ROBOT_URDF` / `POLICY_MODEL` 等代码/模型类需求；`validation_issues` 无 Skill 缺失相关错误。 | 2d |
| **3.2 补齐 `DATASET` Skill** | 后端/Skill | 注册表中新增 `DatasetSkill`；能解析数据集元数据（描述、格式、下载链接、文件列表）并写入 `files/`；能识别并分发 `MESH` / `GRASP` / `SIM_CONFIG` 等数据集类需求；与 `CodeSkill` 共用下载/缓存逻辑。 | 2d |
| **3.3 修复真实 URDF 来源格式问题** | 后端/Adapter | `FrankaAdapter` / `AllegroAdapter` / `RobotiqAdapter` 返回的内容能被 `URDFSkill` 解析：要么提供已展开的纯 URDF raw URL，要么在运行时展开 xacro 并下载依赖的 mesh/include 文件；探活脚本中至少一个机器人 URDF 源标记为可直接解析。 | 1.5d |
| **3.4 修复真实 Mesh 来源可用性问题** | 后端/Adapter | 在当前网络环境下至少有一个 Mesh 源可用：`GoogleScannedAdapter` 30s 内完成 fetch，或 `YCBAdapter` 改拉 `.obj`/`.stl` 格式并被 `MeshSkill` 处理；`GraspNetAdapter` 至少能定位单个 object mesh 而不下载整个 tar。 | 1.5d |
| **3.5 跑通“Franka + YCB + MuJoCo”真实目标** | 全链路 | 输入目标后能生成包含至少两类真实文件（URDF / mesh / grasp / sim_config）的数据包；`files/` 非空；`missing_items` 可解释；探活/测试覆盖该路径。 | 2d |

### P1 — 建议完成（提升质量）

| 任务 | 负责人 | 验收标准 | 建议时间 |
|------|--------|----------|----------|
| **3.6 增加格式深度校验** | 后端/Validate | `validate` 节点增加 URDF 可解析、mesh 可加载（trimesh）、XML/JSON 合法性检查；校验失败项写入 `validation_issues`。 | 1.5d |
| **3.7 实现 `revise` 真正闭环** | 后端/LangGraph | 用户 `review_decision` 为不满意时，将反馈传给 LLM 修正目标或关键词，并触发一次重新检索；新结果进入下一轮 assemble。 | 1.5d |
| **3.8 优化查询关键词** | 后端/Retrieve | 在 `retrieve_data` 中对 LLM 生成的长描述做关键词压缩/提取；相同目标下 Adapter 命中率不低于第一次联调。 | 1d |

### P2 — 可选优化（有空再做）

| 任务 | 负责人 | 验收标准 | 建议时间 |
|------|--------|----------|----------|
| **3.9 修复 `PaperSkill.output_path` warning** | 后端/Skill | `validation_issues` 中不再出现 `output_path` 相关良性 warning。 | 0.5d |
| **3.10 前端进度/日志展示** | 前端 | 前端能实时展示当前检索的数据源、命中/失败原因、已落盘文件数；不再只展示最终结果。 | 1-2d |
| **3.11 配置 `IEEEXploreAdapter` API Key** | 运维/配置 | 在 `.env` 中配置 `IEEE_API_KEY` 并验证该 Adapter 可用；如无法获取 Key，则明确标记为未启用。 | 0.5d |

## 4. 联调节奏建议

建议分三周推进，每周一个里程碑：

### Week 1：补齐数据类型与真实数据来源（P0 3.1-3.4）

- 实现 `CodeSkill` 与 `DatasetSkill`；
- 修复 `FrankaAdapter` 等返回 xacro 的问题，确保 `URDFSkill` 能解析；
- 修复 Mesh 源可用性：`GoogleScannedAdapter` 超时 或 `YCBAdapter` 改拉 `.obj`/`.stl`；
- 每日用 `scripts/_probe_adapters.py` 探活确认数据源可用性；
- 产出：能分别生成 code-only 和 dataset-only 的数据包，且 URDF/mesh 至少各有一个源可被 Skill 消化。

### Week 2：端到端真实场景（P0 3.5 + P1 3.6-3.7）

- 以“Franka Panda + YCB 香蕉 + MuJoCo”为目标跑完整流程；
- 增加 URDF/mesh 格式校验；
- 跑通 revise 闭环：人工给差评后系统能重检索；
- 产出：至少一个包含两类以上真实文件的数据包，且文件可被外部工具加载。

### Week 3：优化与验收（P1 3.8 + P2 3.9-3.11 + 全量回归）

- 关键词压缩优化；
- 修复 warning、前端进度展示；
- 全量单元测试与集成测试回归；
- 更新联调报告与示例数据包。

## 5. 关键风险与应对

| 风险 | 影响 | 应对 |
|------|------|------|
| `GoogleScanned` 网络问题无法根本解决 | 缺少真实 mesh 数据源 | 准备备选源（如其他公开 3D 模型站点）或允许用户上传本地 mesh |
| `CODE`/`DATASET` Skill 实现复杂度高 | 拖延 Week 1 | 先实现最小可用版本（README/元数据 + 文件列表），解析逻辑后续迭代 |
| Adapter 返回格式与 Skill 处理格式不匹配 | 数据 fetch 成功但无法落盘（如 YCB `.glb`、Franka `.xacro`） | 每个 P0 任务都附带“可被对应 Skill 解析”的验收标准；优先走“改 Adapter 返回格式”而非“改 Skill 支持所有格式” |
| 真实文件格式多样，深度校验难覆盖全 | 校验误报/漏报 | 先覆盖 URDF + trimesh 可加载两类最常见格式，其余格式后续补充 |
| revise 闭环需要 LLM 稳定输出 | 重检索目标漂移 | 在 prompt 中约束只能修改关键词/筛选条件，不能改变原始目标 |

## 6. 验收标准

第二次联调通过需同时满足：

1. [ ] 用“Franka + YCB + MuJoCo”目标生成一个数据包，包含至少两类真实文件（URDF / mesh / grasp / sim_config）；
2. [ ] 数据包 `files/` 目录非空，且至少一个 URDF 可被 `urdfpy`/`yourdfpy` 解析、一个 mesh 可被 `trimesh` 加载；
3. [ ] `missing_items` 列表中的每一项都有明确原因说明；
4. [ ] `pytest` 全绿，`ruff check/format` 通过，`mypy src` 无新增错误；
5. [ ] `scripts/_probe_adapters.py` 中 13/15 以上的 Adapter fetch 成功，且 Franka/YCB 至少有一个能被对应 Skill 消化的真实数据路径；
6. [ ] 前端能展示最终数据包目录、缺失项和校验结果（P2 进度展示可选）。

> **关键判定**：验收时不能只检查“文件存在”，必须检查“文件是真实机器人数据且能被外部工具加载”。论文文本、README、xacro 宏文件、`.glb` 模型等若无法被当前 Skill 处理，均不计入“真实文件”。

## 7. 输出物

- [ ] `docs/second_integration_report.md` — 第二轮联调报告；
- [ ] `data/output_packages/package-<ts>/` — 至少一个真实机器人实验数据包样例；
- [ ] 更新后的 `scripts/_probe_adapters.py` 探活结果；
- [ ] 新增/更新的集成测试用例。

## 8. 备注

- 第一次联调样例包位于 `data/output_packages/package-20260805-143339/`，可作为报告格式参考；
- 所有新增 Skill/Adapter 修改应同步更新对应单元测试；
- 如遇需求变更，优先保证 P0 任务，P2 任务可顺延至第三轮。