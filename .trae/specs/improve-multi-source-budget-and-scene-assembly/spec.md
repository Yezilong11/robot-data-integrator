# 多源预算调度与场景组装 Spec（spec-3）

> change-id: improve-multi-source-budget-and-scene-assembly
> 范围：A 多源预算共享软 deadline + B 场景组装接线 + C ycb cup↔mug 语义别名。C 为实施前置分析中现场发现的 ms_011 直接根因（低成本直修）。

## Why

二轮 FAIL 中 P2_RETRIEVE 20 个：E6 均分硬切预算（source_budget = per_req_timeout/源数，[retrieve_data.py:455-464](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/graph/nodes/retrieve_data.py#L455-464)）导致**快源完成后的剩余时间被浪费、慢源（GitHub）占满子预算后快源无执行机会**；ms_011（P3_SOURCE）因 ycb 收录目标中"cup"与"mug"无语义别名而把已有的 025_mug 判为未收录；多源需求（URDF+mesh+scene）各自独立落盘——SimConfigSkill 已支持 `urdf_path`/`mesh_path` kwargs 生成含 URDF/mesh 的 MJCF 场景（[sim_config.py:368-369](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/skills/sim_config.py#L368-369)），但装配层（[registry.py:184](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/skills/registry.py#L184)）从未注入兄弟需求路径，组装能力存在但未接线。

## What Changes

- **A 检索预算共享软 deadline**（`src/rdi/graph/nodes/retrieve_data.py`，最小 diff）：需求级总预算仍为 `per_req_timeout`（需求级超时语义不变）；源循环改为累计软 deadline——每源子预算 = `min(source_budget, deadline - now)`；单源仍受 `source_budget` 上限保护（慢源不拖死其余），快源提前完成后剩余时间释放给后续源（不再浪费）；deadline 到点跳过剩余源并记录。
- **B 场景组装接线**（装配层 `src/rdi/skills/registry.py` 及组装调用方）：SIM_CONFIG 需求处理时自动注入同批次已装配 ROBOT_URDF/MESH 项的 `output_path` 作为 `urdf_path`/`mesh_path` kwargs，使 SimConfigSkill 生成"URDF+mesh 拼接"场景而非空壳。**先核实组装架构**：若当前执行模型为单 req 独立节点、兄弟需求路径不可得，则如实挂账并在总结说明，不强行重构。
- **C ycb cup↔mug 语义别名**（`src/rdi/adapters/ycb.py`）：search 匹配增加语义别名映射（cup→mug 等最小集合），修复"YCB 有该物体却报未收录"。别名仅用于命中判定，不改变返回条目的 id/title。

**不做（明确排除）**：不引入源级历史耗时统计设施（无统计基础设施前提）；不做多轮并行预取/探活；不改 `per_req_timeout` 配置；不做仿真场景的物体布局生成（仅拼接既有资产）。

## Impact

- Affected specs: improve-retrieve-hit-and-record-closure（预算链路）、fix-round2-test-issues（R3 资产链路）、extend-kinova-isaac-format-coverage（error 兜底）
- Affected code:
  - `src/rdi/graph/nodes/retrieve_data.py`——A 预算逻辑（~15 行）
  - `src/rdi/skills/registry.py`（+ 组装调用方）——B 接线
  - `src/rdi/adapters/ycb.py`——C 别名映射
  - 测试：扩展 `tests/unit/graph/test_retrieve_data.py`、`tests/unit/test_ycb_adapter.py`、`tests/unit/skills/test_registry.py`

## ADDED Requirements

### Requirement: 多源预算共享软 deadline
检索在逐源执行时 SHALL 在需求级总预算内共享时间：快源完成后剩余时间释放给后续源，单源仍受均分子预算上限保护。

#### Scenario: 快源提前完成释放时间
- **WHEN** 需求有 3 个候选源，子预算 10s；第 1 源 2s 完成，第 2 源 8s 内未命中
- **THEN** 第 3 源仍可执行（可用时长 = min(10s, deadline 剩余) > 0），而非被硬切 10s 上限浪费后无法执行

#### Scenario: 慢源不拖死其余
- **WHEN** 某源占用达子预算上限仍未返回
- **THEN** 该源被 `asyncio.timeout` 中止并记录源级超时，继续后续源（行为与 E6 一致）

#### Scenario: 总预算到点即停
- **WHEN** 累计执行达 `per_req_timeout`
- **THEN** 剩余源跳过并记录，需求级超时语义不变

### Requirement: 场景组装接线
SIM_CONFIG 需求处理 SHALL 在可行时携带同批次已有机器人 URDF 与物体 mesh 的落盘路径，使降级/生成场景包含真实机器人几何与物体。

#### Scenario: 兄弟需求已装配
- **WHEN** 同批次已装配 ROBOT_URDF 与 MESH 项（有 output_path），SIM_CONFIG 项进入 skill 处理
- **THEN** skill 收到 `urdf_path`/`mesh_path`，生成的最小 MJCF 引用二者（场景不再只有地面+相机）

#### Scenario: 无兄弟需求
- **WHEN** SIM_CONFIG 是唯一需求或兄弟需求未装配
- **THEN** 行为与现状一致（无 urdf_path/mesh_path），不报错

### Requirement: ycb cup↔mug 语义别名
ycb 检索 SHALL 通过语义别名命中已有物体（cup→mug），不因口语别名把已有目标判为未收录。

#### Scenario: 别名命中
- **WHEN** 需求含 "YCB cup mesh"，ycb 收录 "025_mug"（Mug）
- **THEN** 检索命中 025_mug（返回条目 id/title 不变），不再抛"仅收录 N 个已知目标未收录"

## MODIFIED Requirements

无（A/B/C 均为新增行为+最小改动，既有 E6 与 registry 行为在非触发场景保持不变）。

## REMOVED Requirements

无。