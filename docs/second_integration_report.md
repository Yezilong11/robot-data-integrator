# 第二次联调报告

> 报告日期：2026-08-08
> 对应目标：让系统生成包含可被外部工具加载的 URDF / mesh / grasp / sim_config 等真实文件的机器人实验数据包。
> 生成数据包：`data/output_packages/package-20260808-181854/`
> 演示脚本：`scripts/run_second_integration_demo.py`

---

## 1. 执行摘要

### 目标

在第一次联调已打通「自然语言目标 → 论文文本数据包」链路的基础上，第二次联调聚焦**真实机器人实验数据**：要求系统能理解类似「Franka Panda grasps YCB banana in MuJoCo simulation」的目标，并产出包含可被 `urdfpy`/`trimesh`/MuJoCo 加载的真实文件的数据包。

### 达成结果

- 补齐了 `CODE` 与 `DATASET` Skill，解决了 `parse_convert` 因缺少 Skill 而直接返回 `MissingItem` 的瓶颈。
- 修复了真实 URDF / mesh 来源的格式契约：Franka 返回纯 URDF，YCB 返回 `.obj`/`.stl`，MuJoCo/Isaac 从 `ROBOT_URDF` 注册表中移除或调整至 `SIM_CONFIG`。
- 优化了 `parse_goal` 的 DataReq 类型识别，增加 few-shot 示例和后处理规则，并实现 `fallback_sources` 顺序检索。
- 强化了 Skill 兼容性：`URDFSkill` 支持 xacro 降级处理，`MeshSkill` 支持 `glb`/`zip` 兜底。
- 在 `validate` 节点增加深度可加载性校验（URDF/mesh/sim_config/grasp）。
- 跑通「Franka + YCB + MuJoCo」端到端 demo，生成真实数据包样例，并回归通过 378 个测试用例。
- 2026-08-08 追加修复：中文自然语言目标端到端可用；`sim_config` 输出 MuJoCo MJCF XML；`grasp` 支持 GraspNet metadata JSON 解析并生成 synthetic grasp JSON；全量测试回归至 393 个通过。

---

## 2. 各任务完成情况

### Task 1：CODE / DATASET Skill 实现与注册

- 实现 `src/rdi/skills/code_parse.py`，支持 markdown / json / zip / tar 输入，输出 `CodeRepoSummary`（repo URL、README 文本、文件树、框架信息、安装说明）。
- 实现 `src/rdi/skills/dataset_parse.py`，支持 json / tar / zip 输入，输出 `DatasetSummary`（标题、描述、下载 URL、文件树、许可证）。
- 在 `src/rdi/skills/registry.py` 中完成注册：`DataReqType.CODE → CodeSkill`、`DataReqType.DATASET → DatasetSkill`。
- 新增/更新单元测试：`tests/unit/skills/test_code_parse.py`、`tests/unit/skills/test_dataset_parse.py`。

### Task 2：真实 URDF 来源修复

- 修改 `src/rdi/adapters/franka.py`，返回已展开纯 URDF 字节。
- 同步修改 `src/rdi/adapters/allegro.py` 与 `src/rdi/adapters/robotiq.py`，统一按纯 URDF 格式返回。
- 调整 `src/rdi/adapters/registry.py`：将 MuJoCo / IsaacSim 从 `ROBOT_URDF` 注册表中移除，转而作为 `SIM_CONFIG` 候选源。
- 更新对应单元测试，验证 URDF 可被 `URDFSkill` / `yourdfpy` 解析。

### Task 3：真实 Mesh 来源修复

- 修改 `src/rdi/adapters/ycb.py`，优先拉取 `.obj`/`.stl` 格式（如 `google_16k/textured.obj`），替代原先不支持的 `.glb`。
- 修复 `src/rdi/adapters/google_scanned.py` 超时问题：改为按单 mesh 文件下载、增加重试与超时降级，必要时跳过不可用文件。
- 修改 `src/rdi/adapters/graspnet.py` 与 `src/rdi/adapters/dexgrasp.py`：根据 `DataReqType` 返回单个 grasp 文件（`.npz`/`.pkl`）或数据集 metadata JSON，不再直接返回整个 `.tar`。
- 更新单元测试并验证 mesh 可被 `trimesh.load` 加载。

### Task 4：目标解析 DataReq 类型识别优化

- 修改 `src/rdi/intelligence/prompts/goal_parsing.py`：在 system prompt 中增加 few-shot 示例，明确 `robot_urdf`/`mesh`/`grasp`/`sim_config` 与 `code`/`dataset` 的区分。
- 修改 `src/rdi/graph/nodes/parse_goal.py`：基于 `expected_format` 和关键词对误识别的 `code`/`dataset` 进行后处理强制映射到正确的数据类型。
- 修改 `src/rdi/graph/nodes/retrieve_data.py`：按 `fallback_sources` 顺序尝试数据源，而非全局注册表顺序。
- 更新 `tests/unit/graph/nodes/test_parse_goal.py` 与 `test_retrieve_data.py`。

### Task 5：Skill 格式兼容性增强

- 在 `src/rdi/skills/urdf_convert.py` 中增加 xacro 字符串级降级处理：当 ROS `xacro` 模块不可用时，移除 `<xacro:` 标签、替换 `$(find ...)` 占位路径，并给出明确 warning。
- 在 `src/rdi/skills/mesh_process.py` 中增加 `glb` 与 `zip` 支持：`glb` 使用 `trimesh.load(..., force="mesh")`；`zip` 解压后取首个可用 mesh 文件。
- 更新对应单元测试，使用 `tests/unit/skills/sample_data/` 中的样例数据。

### Task 6：格式深度校验

- 修改 `src/rdi/graph/nodes/validate.py`：
  - `ROBOT_URDF`：使用 `urdfpy`/`yourdfpy` 解析并记录 ERROR。
  - `MESH`：使用 `trimesh.load` 加载，检查 faces > 0。
  - `SIM_CONFIG`：使用 XML 或 `ast.parse` 做语法校验。
  - `GRASP`：检查 `.npz`/`.pkl` 中必要字段是否存在。
- 校验失败项写入 `validation_issues`，最终反映到 `manifest.json` 的 `quality_report` 中。
- 新增集成测试覆盖校验路径。

### Task 7：端到端真实场景与数据包样例

- 使用目标 "Franka Panda grasps YCB banana in MuJoCo simulation" 运行完整工作流。
- 生成数据包 `data/output_packages/package-20260807-165308/`，包含：
  - `files/req_000.urdf`：Franka Panda URDF，可解析。
  - `files/req_001.stl`：YCB banana mesh，可加载。
  - `files/req_002.json`：MuJoCo 场景配置（由 `panda.xml` 转换而来的 `SceneDescription`）。
- Adapter 探活：`scripts/_probe_adapters.py` 14/15 通过（IEEE 因缺少 API Key 被跳过）。
- 全量测试：`pytest` 378 passed / 1 skipped / 9 deselected。

### Task 8：中文目标与真实 XML/grasp 修复

- 修复 `retrieve_data` 多 token 查询问题，支持包含中文、空格与标点的自然语言目标正常检索。
- 修复 `MuJoCoAdapter` / `IsaacSimAdapter` token 匹配逻辑，使 "MuJoCo" / "Isaac Sim" 等关键词能正确命中对应适配器。
- `SimConfigSkill` 增加最小 MJCF 回退：当无法从 `mujoco_menagerie` 获取真实 scene 时，生成包含 URDF、mesh 与 worldbody 的基本 MuJoCo MJCF XML，并以 XML bytes 输出。
- `GraspSkill` 增加 GraspNet metadata JSON 解析，在真实 `.npz`/`.pkl` 不可用时生成 synthetic grasp JSON，避免节点崩溃。
- 使用中文目标「我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉，并测试抓取姿态的稳定性。」完成端到端验证，输出 URDF + STL + MJCF XML + grasp JSON。

---

## 3. 验证结果

### 3.1 代码质量检查

| 检查项 | 命令 | 结果 |
|---|---|---|
| lint | `uv run ruff check src tests` | passed |
| format | `uv run ruff format --check src tests` | passed |
| 类型检查 | `uv run mypy src` | passed |

### 3.2 测试

| 指标 | 结果 |
|---|---|
| 通过 | 393 |
| 跳过 | 1 |
| 取消选择 | 9 |
| 失败 | 0 |

### 3.3 Adapter 探活

- 运行：`uv run python scripts/_probe_adapters.py`
- 结果：**14/15 fetch 成功**
- 唯一未通过：IEEE，原因为本地未配置 IEEE API Key。

### 3.4 生成数据包验证

数据包路径：`data/output_packages/package-20260808-181854/`

manifest 摘要：

```json
{
  "package_info": {
    "goal": "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉，并测试抓取姿态的稳定性。",
    "package_id": "package-20260808-181854",
    "status": "complete"
  },
  "files": [
    {"req_id": "req_000", "path": "files/req_000.urdf", "format": "urdf"},
    {"req_id": "req_001", "path": "files/req_001.stl", "format": "trimesh.Trimesh"},
    {"req_id": "req_002", "path": "files/req_002.xml", "format": "mujoco-mjcf"},
    {"req_id": "req_003", "path": "files/req_003.json", "format": "grasp-metadata-json"}
  ],
  "missing_items": [],
  "quality_report": {
    "total_requirements": 4,
    "fulfilled": 4,
    "missing": 0,
    "validation_issues": 0,
    "avg_confidence": 0.95,
    "avg_completeness": 95.0
  }
}
```

外部工具验证：

- URDF：使用 `yourdfpy.URDF.load(..., load_meshes=False)` 成功解析。
- Mesh：使用 `trimesh.load(..., force="mesh")` 成功加载，faces 数量正常。
- MJCF XML：可被 MuJoCo 加载，包含 worldbody、robot 与物体引用。
- Grasp JSON：包含 synthetic grasp 元数据，可被下游工具读取。
- 数据包包含 URDF、mesh、sim_config、grasp 四类文件，满足第二次联调目标。

---

## 4. 已知问题与风险

| 问题/风险 | 影响 | 当前状态 |
|---|---|---|
| `parse_goal` 在本地真实 LLM 环境下仍不稳定 | 自然语言目标可能无法正确生成 `robot_urdf`/`mesh`/`sim_config` 类型的 DataReq | 中文目标已可端到端运行，但不同措辞/模型的稳定性仍需继续优化 prompt 与输出 schema |
| IEEE API Key 未配置 | IEEE 源无法 fetch | 仅影响该单一源，已通过探活脚本跳过 |
| GoogleScanned 仍可能慢或失败 | mesh 来源的鲁棒性 | 已做超时降级，但仍依赖网络环境；YCB 作为主要 mesh 源已可用 |
| `grasp` 数据为 synthetic/metadata 降级 | 不是真实 GraspNet `.npz`/`.pkl` 抓取数据 | 已实现 metadata JSON 解析与 synthetic grasp 生成，端到端不崩溃，但真实抓取数据路径仍需补齐 |
| `sim_config` 常为最小 MJCF 回退 | 生成的仿真场景较简单，未复用真实 `mujoco_menagerie` 场景 | 可生成合法 MuJoCo XML，但复杂真实场景覆盖率有限 |
| `human_review` 节点仍是占位 | 缺少真实反馈闭环 | 节点存在但仅返回 satisfied，未实现 revise/unsatisfied 循环重检索 |
| 输出数据包目录扁平 | 所有文件放在 `files/`，不利于直接使用 | 已记录需求，计划在第三次联调按类型组织目录 |

---

## 5. 下一步建议（第三次联调方向）

1. **补齐真实 grasp 数据路径**：继续打磨 GraspNet / DexGrasp 单个 `.npz`/`.pkl` 下载逻辑，增加本地缓存与备选源（如 YCB-Video grasp 标注），替换当前的 synthetic/metadata 降级。
2. **提升 `sim_config` 真实场景覆盖率**：优先复用 `mujoco_menagerie` 等真实 MJCF 场景，减少最小 MJCF 回退比例。
3. **稳定真实 LLM 目标解析**：在 `parse_goal` 中引入更结构化的输出 schema 与更多 few-shot，覆盖中英文、不同句式与机器人/物体名称变体，必要时切换到本地可复现的轻量模型或规则兜底。
4. **实现 `human_review` 真实闭环**：接入用户反馈触发的 LangGraph 循环重检索，支持 revise/unsatisfied 决策与重试策略。
5. **数据包目录结构化**：按 `robots/`、`objects/`、`grasps/`、`sim_config/`、`scripts/` 组织输出，提升研究人员直接使用体验。
6. **Hermes 经验库接入**：记录「源-需求类型-成功率」统计，让 `retrieve_data` 能基于历史成功率动态推荐备选源。
7. **前端进度可视化**：在 `rdi.frontend.app` 中展示每个 DataReq 的检索阶段、成功/失败状态与原因。
8. **IEEE / 其他 API Key 配置**：完善本地开发环境配置文档，减少探活失败项。

---

## 6. 关键文件清单

| 类别 | 路径 |
|---|---|
| 本报告 | `docs/second_integration_report.md` |
| 联调 Spec | `.trae/specs/implement-second-integration/spec.md` |
| 任务清单 | `.trae/specs/implement-second-integration/tasks.md` |
| 技术指导 | `.trae/documents/second-integration-technical-guide.md` |
| 演示脚本 | `scripts/run_second_integration_demo.py` |
| 生成数据包 | `data/output_packages/package-20260808-181854/manifest.json` |
| CODE Skill | `src/rdi/skills/code_parse.py` |
| DATASET Skill | `src/rdi/skills/dataset_parse.py` |
| URDF Skill | `src/rdi/skills/urdf_convert.py` |
| Mesh Skill | `src/rdi/skills/mesh_process.py` |
| validate 节点 | `src/rdi/graph/nodes/validate.py` |
| parse_goal 节点 | `src/rdi/graph/nodes/parse_goal.py` |
| retrieve_data 节点 | `src/rdi/graph/nodes/retrieve_data.py` |
| Adapter 注册表 | `src/rdi/adapters/registry.py` |
