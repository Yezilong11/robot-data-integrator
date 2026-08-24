# 第三次联调（三联）执行 Spec

## Why

二联已打通「自然语言目标 → 真实文件数据包」链路（393 测试全绿），但 grasp 仍为 synthetic/metadata 降级、sim_config 多为最小 MJCF 回退、human_review 是占位节点、输出目录扁平，距离「研究人员日常可用」仍有差距。本 spec 按 `.trae/documents/third-integration-technical-guide.md` 推进 P0（真实 grasp 数据路径、LLM 目标解析稳定化、human_review 真实闭环）、P1（数据包目录结构化、真实可运行性验证、Hermes 源选择优化）、P2（前端进度可视化）。

**北极星指标**：输入任意常见机器人操作目标（中英文、多种机器人/物体/仿真器组合），系统自动生成结构化实验数据包，其中 grasp 来自真实数据集或高质量备选源，sim_config 能在 MuJoCo 中直接加载并运行至少一步仿真，用户可通过 human_review 闭环修正结果。

## 当前现状（评估结论摘要）

| 差距 | 现状 |
|---|---|
| grasp 真实性 | `.npz` 近似解析可用（旋转矩阵近似重建，completeness 70）、pkl 不可用（依赖 graspnetAPI）、无本地缓存、探活只拿 metadata JSON |
| sim_config 真实性 | 6 个 mujoco_menagerie 场景可达，但真实 XML 被重建压缩（丢 mesh/执行器）、fallback 无相机 |
| LLM 解析稳定性 | `_correct_req_type` 后处理关键词不全（缺 robot/机器人/模型/物体/抓取/simulation）、无 10+ few-shot、无 UNKNOWN |
| human_review 闭环 | 占位节点；图有 revise→retrieve_data 边，缺 parse_goal 回边与 unsatisfied 分支；state 缺 revised_goal/query_cache |
| 数据包组织 | 仍为扁平 files/，manifest path=`files/req_xxx.ext` |
| 可运行性验证 | URDF/mesh 深校验有；SIM_CONFIG 仅 XML 语法解析；mujoco 依赖未安装；manifest 缺三字段 |
| Hermes 源选择 | 动态排序已接入 retrieve_data，但统计缺「源-需求类型」二维维度 |
| 前端体验 | 有 provenance/校验展示，无逐 DataReq 阶段/成败/原因表 |

## What Changes

- 扩展 `PackageManifest` / `ManifestFile`：新增 `runtime_check`、`data_source_quality`、`revision_history`。
- `BaseAdapter` 增加统一本地缓存 `get_cache_path()` / `is_cached()`，缓存目录 `data/cache/<source>/`。
- 补齐真实 grasp 数据路径：GraspNet 按物体定位 `grasp_label/` 下 `.npz`、DexGrasp `.pkl`、YCB-Video grasp 标注 fallback；`GraspSkill` 解析真实 `.npz`/`.pkl` 并标注 `data_source_quality`。
- 提升 sim_config 真实命中：扩展 `mujoco_menagerie` 场景列表（含 `unitree_go2`、`scene.xml` 命名）；命中真实 XML 时 Skill 直接返回 XML bytes；最小 MJCF fallback 增加相机。
- 稳定 LLM 目标解析：prompt 增加 10+ few-shot；`parse_goal` 规则后处理补全关键词并增加 `UNKNOWN` 分支。
- 实现 human_review 真实闭环：feedback 转换、条件边（revised→parse_goal / unsatisfied→retrieve_data / satisfied→END）、state 增加 `revised_goal`/`query_cache`、限制最大循环次数。
- 数据包目录按类型结构化：`robots/`、`objects/`、`grasps/`、`sim_config/`、`policies/`、`resources/`。
- validate 对 `SIM_CONFIG` 增加 MuJoCo `mj_step` 运行时验证（mujoco 作为可选依赖安装）。
- Hermes 统计升级为「源-需求类型-成功率」，动态影响 `retrieve_data` 排序。
- 前端展示每个 DataReq 的阶段/成功/失败/降级与原因。
- 新增 `tests/integration/test_third_integration.py` 覆盖 5 个端到端目标。

## Impact

- 受影响 spec：无前置未完成 spec（`implement-second-integration` 已完成）。
- 受影响代码：
  - 模型：`src/rdi/models/manifest.py`、`common.py`、`parsed.py`
  - Adapter：`src/rdi/adapters/base.py`、`graspnet.py`、`dexgrasp.py`、`ycb.py`、`mujoco.py`、`isaac.py`
  - Skill：`src/rdi/skills/grasp_parse.py`、`sim_config.py`
  - 图：`src/rdi/graph/nodes/parse_goal.py`、`retrieve_data.py`、`human_review.py`、`assemble.py`、`validate.py`；`src/rdi/graph/builder.py`、`edges.py`、`state.py`
  - 智能：`src/rdi/intelligence/prompts/goal_parsing.py`
  - Hermes：`src/rdi/hermes/strategy.py`、`experience_db.py`
  - 前端：`src/rdi/frontend/app.py`
  - 依赖：`pyproject.toml`（mujoco 可选依赖）、`uv.lock`
  - 测试：`tests/integration/test_third_integration.py`（新增）、`tests/unit/skills/sample_data/grasp/`（新增 `.pkl` 样本）

## ADDED Requirements

### Requirement: 数据包清单元数据扩展

`PackageManifest` SHALL 增加 `runtime_check`（记录 MuJoCo 一步仿真是否通过）、`data_source_quality`（每个文件标注 `real` / `synthetic` / `fallback`）、`revision_history`（记录 human_review 触发的版本关联）；`ManifestFile` SHALL 增加 `data_source_quality` 字段。扩展不得破坏现有 393+ 测试。

#### Scenario: 端到端生成带元数据的数据包
- **WHEN** 系统生成数据包并写出 manifest.json
- **THEN** manifest 含 `runtime_check`、各文件 `data_source_quality`、空 `revision_history`

### Requirement: Adapter 统一本地缓存

`BaseAdapter` SHALL 提供 `get_cache_path(item_id)` 与 `is_cached(item_id)`；各 Adapter `fetch()` SHALL 优先从 `data/cache/<source>/` 读取，命中则不触发网络请求；至少 Franka、YCB、GraspNet 使用统一缓存。

#### Scenario: 缓存命中不请求网络
- **WHEN** 同一 item 第二次 fetch（mock 网络）
- **THEN** 直接从缓存返回，无网络调用

### Requirement: human_review 真实闭环

`human_review` 节点 SHALL 支持三种决策：`satisfied` → `END`；`revised` → 调用 LLM 将用户反馈转换为修正后目标并经 `parse_goal` 重新解析；`unsatisfied` → 生成更激进的重检索建议回 `retrieve_data`。循环 SHALL 限制最大次数（如 3 次），每次循环清空旧 `retrieval_results`。

#### Scenario: revised 触发重生成
- **WHEN** 用户选择 `revised` 并给出反馈
- **THEN** 系统生成新数据包，且 manifest `revision_history` 记录版本关联

#### Scenario: satisfied 结束流程
- **WHEN** 用户选择 `satisfied`
- **THEN** 工作流到达 `END`

### Requirement: 集成测试覆盖 5 个目标

`tests/integration/test_third_integration.py` SHALL 覆盖 5 个中英文混合目标（Franka Panda + YCB banana in MuJoCo、中文等价表述、Kinova Gen3 + EGAD mug in Isaac、UR5 + Robotiq 2F-85 + YCB apple、Franka Panda + YCB blocks in PyBullet），mock 环境下至少 4/5 全绿，断言包含四类文件、无 ERROR，且 grasp/sim_config 至少一个 `data_source_quality="real"`。

## MODIFIED Requirements

### Requirement: 真实 Grasp 数据路径（原：grasp 为 synthetic/metadata 降级）

`GraspNetAdapter` SHALL 支持按 `object_name` 定位 `grasp_label/` 下对应 `.npz` 并缓存到 `data/cache/graspnet/`；`DexGraspAdapter` 类似定位单个 `.pkl`；YCB-Video SHALL 提供 grasp 标注（`.mat`/`.json`）作为 fallback；`GraspSkill` SHALL 解析真实 `.npz`/`.pkl` 为 `CanonicalGrasp` 并在 `metadata` 标注 `data_source_quality`，保留 synthetic fallback（标注 `fallback`）。验收：`scripts/_probe_adapters.py` 中 GraspNet/DexGrasp/YCB-Video 至少一个返回单个真实 grasp 文件。

#### Scenario: GraspNet 返回真实 npz
- **WHEN** 目标含特定物体，GraspNet 命中
- **THEN** 返回真实 `.npz`，`GraspSkill` 解析出 `CanonicalGrasp` 且 `data_source_quality="real"`

### Requirement: 真实 SimConfig 场景命中率提升（原：多为最小 MJCF fallback）

`MuJoCoAdapter` SHALL 扩展 `_FALLBACK_SCENES`（含 `unitree_go2`、`franka_emika_panda/scene.xml` 等），每条记录标注适用关键词；`SimConfigSkill` SHALL 在 Adapter 返回真实 XML 时直接返回 XML bytes（不重建），未命中时才生成最小 MJCF（SHALL 包含地面、相机、灯光）；`IsaacSimAdapter` SHALL 提供官方场景映射或明确提示。

#### Scenario: 命中真实场景
- **WHEN** 输入 "Franka Panda in MuJoCo"
- **THEN** `MuJoCoAdapter` 返回真实 `scene.xml`，`SimConfigSkill` 原样输出 XML bytes

#### Scenario: 未命中走 fallback
- **WHEN** 未命中真实场景
- **THEN** 生成含地面与相机的最小 MJCF，且可被 MuJoCo 加载

### Requirement: LLM 目标解析稳定化（原：特定句式可用）

`goal_parsing.py` prompt SHALL 增加 10+ 组 few-shot，覆盖 Franka/Kinova/UR5 × YCB/EGAD/ModelNet × MuJoCo/Isaac/PyBullet；`parse_goal.py` 规则后处理 SHALL 覆盖指导书全部强制映射关键词（含 `robot`/`机器人`→ROBOT_URDF、`模型`/`物体`→MESH、`抓取`→GRASP、`simulation`→SIM_CONFIG），无法识别时标记 `UNKNOWN` 并记录 warning。验收：10 个常见组合至少 9 个正确产出四类 DataReq。

#### Scenario: 中文目标正确解析
- **WHEN** 输入中文目标「我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉」
- **THEN** 产出 ROBOT_URDF / MESH / GRASP / SIM_CONFIG 四类 DataReq

### Requirement: 数据包目录结构化（原：扁平 files/）

`assemble.py` SHALL 按 `req_type` 映射子目录（ROBOT_URDF→robots/、MESH→objects/、GRASP→grasps/、SIM_CONFIG→sim_config/、POLICY_MODEL→policies/、CODE/DATASET/PAPER→resources/），`req_id` 作文件名前缀；manifest `files[].path` SHALL 同步为相对子目录路径。

#### Scenario: 生成结构化数据包
- **WHEN** 端到端运行生成数据包
- **THEN** 包含 robots/、objects/、grasps/、sim_config/ 子目录且 manifest path 一致

### Requirement: 真实可运行性验证（原：仅解析格式）

`validate.py` 对 SIM_CONFIG SHALL 使用 `mujoco.MjModel.from_xml_string` + `mj_step` 验证；验证结果写入 `validation_issues` 与 `runtime_check`。mujoco 以可选依赖加入 `pyproject.toml`（测试用 marker 标记，本地开发必跑）。失败项 severity 为 ERROR。

#### Scenario: MuJoCo 加载运行一步
- **WHEN** 数据包含合法 MJCF XML
- **THEN** `mj_step` 成功，`runtime_check` 通过

### Requirement: Hermes 源选择优化（原：按 fallback 固定顺序）

`experience_db` 统计 SHALL 升级为「源-需求类型-成功率」二维统计；`strategy.get_source_priority` SHALL 基于该统计动态排序；`retrieve_data` 检索失败时自动尝试历史成功率更高的源。

#### Scenario: 动态推荐备选源
- **WHEN** 某源对某需求类型历史成功率低
- **THEN** Hermes 将其排序下调，优先尝试成功率更高的源

### Requirement: 前端进度可视化（原：只展示最终结果）

`frontend/app.py` SHALL 在真实流程模式下以表格展示每个 DataReq 的阶段（解析中/检索中/成功/失败/降级）、失败原因与 fallback 来源，并展示数据包目录结构与 `validation_issues`。

#### Scenario: 逐 DataReq 状态展示
- **WHEN** 流程运行或完成后
- **THEN** 前端表格展示每个 DataReq 的状态与失败原因

## REMOVED Requirements

无（本次仅增强既有能力，不删除功能）。
