# 第二次联调 Spec

> 依据：[第二次联调技术指导文档](../../../documents/second-integration-technical-guide.md)

## Why

第一次联调已打通从自然语言目标到论文文本数据包的端到端链路，但系统无法产出研究人员日常可用的真实机器人实验数据包。第二次联调的目标是让系统能够生成包含可被外部工具加载的 URDF / mesh / grasp / sim_config 等真实文件的数据包。

## What Changes

- 补齐 `CODE` 和 `DATASET` Skill，使 `parse_convert` 能处理这两类需求；
- 修复 Adapter-Skill 格式契约未对齐问题：
  - `FrankaAdapter` 等返回已展开 URDF，替代 xacro；
  - `YCBAdapter` 改拉 `.obj`/`.stl`，替代 `.glb`；
  - `GoogleScannedAdapter` 修复超时或提供降级方案；
- 优化 `parse_goal` 的 DataReq 类型识别，使 LLM 能正确产出 `robot_urdf`/`mesh`/`grasp`/`sim_config` 类型；
- 实现格式深度校验：`validate` 节点验证 URDF/mesh/sim_config/grasp 可被外部工具加载；
- 跑通「Franka + YCB + MuJoCo」端到端目标，生成真实数据包样例；
- 更新测试覆盖新增和修改的 Adapter/Skill/集成路径。

## Impact

- 受影响模块：`src/rdi/skills/`、`src/rdi/adapters/`、`src/rdi/graph/nodes/`、`src/rdi/intelligence/prompts/`、`tests/`；
- 受影响文档：`docs/second_integration_report.md`；
- 用户可见变化：输入自然语言目标后，系统可输出包含真实机器人数据的结构化数据包。

## ADDED Requirements

### Requirement: CODE Skill

The system SHALL provide a `CodeSkill` registered in `SkillRegistry` for `DataReqType.CODE`.

#### Scenario: Success case

- **WHEN** `parse_convert` receives a `RetrievalResult` with `req_type=code` and raw data from GitHub README or HuggingFace config
- **THEN** it returns a `ParsedItem` with `canonical_format="CodeRepoSummary"` containing repo URL, README text, file tree, and framework info

### Requirement: DATASET Skill

The system SHALL provide a `DatasetSkill` registered in `SkillRegistry` for `DataReqType.DATASET`.

#### Scenario: Success case

- **WHEN** `parse_convert` receives a `RetrievalResult` with `req_type=dataset` and metadata JSON from Zenodo/GraspNet/HuggingFace
- **THEN** it returns a `ParsedItem` with `canonical_format="DatasetSummary"` containing title, description, download URL, file tree, and license

### Requirement: Real URDF Source

The system SHALL have at least one `ROBOT_URDF` Adapter that returns plain URDF bytes parseable by `URDFSkill`.

#### Scenario: Success case

- **WHEN** `FrankaAdapter.fetch("panda")` is called
- **THEN** it returns `RawData` with format `urdf` and bytes representing a valid URDF document

### Requirement: Real Mesh Source

The system SHALL have at least one `MESH` Adapter that returns a mesh file in a format supported by `MeshSkill`.

#### Scenario: Success case

- **WHEN** `YCBAdapter.fetch("025_mug")` is called
- **THEN** it returns `RawData` with format in `stl/obj/ply/dae` and bytes loadable by `trimesh`

### Requirement: Deep Format Validation

The system SHALL validate that parsed robot data files can be loaded by external tools.

#### Scenario: URDF validation

- **WHEN** a `ParsedItem` with `req_type=robot_urdf` reaches `validate`
- **THEN** the node attempts to parse it with `urdfpy`/`yourdfpy` and records any ERROR in `validation_issues`

#### Scenario: Mesh validation

- **WHEN** a `ParsedItem` with `req_type=mesh` reaches `validate`
- **THEN** the node attempts to load it with `trimesh` and records any ERROR in `validation_issues`

### Requirement: End-to-End Real Robot Package

The system SHALL generate a real robot experiment data package from the goal "Franka Panda grasps YCB banana in MuJoCo simulation".

#### Scenario: Success case

- **WHEN** the user inputs the above goal and runs the real workflow
- **THEN** `data/output_packages/package-<ts>/` is created with at least two categories of real files (URDF / mesh / grasp / sim_config), and at least one URDF is parseable and one mesh is loadable

## MODIFIED Requirements

### Requirement: Goal Parsing Type Recognition

The `parse_goal` node SHALL produce correct `DataReq.req_type` for robot experiment goals.

#### Scenario: Robot URDF recognized

- **WHEN** the user goal mentions "Franka Panda URDF"
- **THEN** the output `DataReq` has `req_type=robot_urdf` and `fallback_sources` contains "franka"

#### Scenario: Mesh recognized

- **WHEN** the user goal mentions "YCB banana mesh"
- **THEN** the output `DataReq` has `req_type=mesh` and `fallback_sources` contains "ycb"

## REMOVED Requirements

None.
