# 修复 sim_config 与 grasp 真实数据获取 Spec

## Why

第二次联调后，中文自然语言目标已能正确解析出 robot_urdf、mesh、sim_config、grasp 四类需求，并成功生成 URDF 与 mesh 真实文件。但实际端到端测试中，sim_config 仍拿到 Isaac Python 配置（非用户指定的 MuJoCo XML），grasp 仍因 GraspNet 返回 metadata JSON 而非 npz 导致解析失败。本 spec 聚焦补齐这两类数据的真实/可用落盘路径。

## What Changes

- 修复 `MuJoCoAdapter` 搜索逻辑，使「MuJoCo + 机器人/物体名」能命中 `mujoco_menagerie` 的真实 XML 场景；
- 在 `SimConfigSkill` 中新增基于已有 URDF/mesh 生成最小 MJCF 场景的 fallback，确保 sim_config 至少产出可运行的 XML；
- 在 `GraspSkill` 中新增 metadata JSON 的解析 fallback，将无法下载整数据集的 GraspNet 结果降级为可读的抓取元数据；
- 如仍无真实 grasp 数据，提供基于物体包围盒的 synthetic grasp 生成作为最后兜底；
- 更新 `retrieve_data` 与 `parse_convert` 的交互，确保 `fmt` 和 `dataset_name` 正确传递；
- 新增/更新单元测试覆盖以上路径。

## Impact

- 受影响模块：`src/rdi/adapters/mujoco.py`、`src/rdi/skills/sim_config.py`、`src/rdi/skills/grasp_parse.py`、`src/rdi/graph/nodes/retrieve_data.py`、`src/rdi/graph/nodes/parse_convert.py`、`tests/`；
- 用户可见变化：输入"Franka Panda 在 MuJoCo 中抓取 YCB 香蕉"后，数据包至少包含 URDF、mesh、MJCF XML 三类可用文件；grasp 至少包含 metadata JSON 或 synthetic 抓取，不再解析失败。

## ADDED Requirements

### Requirement: MuJoCo XML 真实来源

The system SHALL return a MuJoCo MJCF XML file when the user goal mentions MuJoCo.

#### Scenario: Success case

- **WHEN** the user goal contains "MuJoCo" and a robot/object name (e.g. "Franka Panda", "banana")
- **THEN** `MuJoCoAdapter.search` returns at least one `SearchResult` pointing to a real `mujoco_menagerie` XML

### Requirement: SimConfig Synthetic Fallback

The system SHALL generate a minimal runnable MJCF XML if no real sim_config source returns valid data.

#### Scenario: Success case

- **WHEN** `parse_convert` receives a `sim_config` requirement but no successful retrieval/parse from adapters
- **THEN** `SimConfigSkill` uses the already-retrieved URDF and mesh to emit a minimal MJCF XML containing the robot and object

### Requirement: Grasp Metadata Fallback

The system SHALL parse GraspNet/DexGrasp metadata JSON instead of failing when no single `.npz` is available.

#### Scenario: Success case

- **WHEN** `GraspSkill.process` receives metadata JSON (format=json) from GraspNet for a `grasp` requirement
- **THEN** it returns a `StandardResult` with canonical_format="CanonicalGrasp" containing a synthetic grasp list derived from the object name, without raising

### Requirement: End-to-End Four-Category Package

The system SHALL generate a package containing at least three usable real files from the Chinese goal "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉，并测试抓取姿态的稳定性。".

#### Scenario: Success case

- **WHEN** the user inputs the above goal and runs the real workflow
- **THEN** `data/output_packages/package-<ts>/` contains `req_*.urdf`, `req_*.stl`, `req_*.xml`, and `req_*.json` (grasp metadata/synthetic), with no `validation_issues` severity=ERROR

## MODIFIED Requirements

### Requirement: Adapter Search Token Matching

The `MuJoCoAdapter` and `IsaacSimAdapter` search functions SHALL support multi-token queries by matching any token against id/title/description.

#### Scenario: Multi-word keyword

- **WHEN** `MuJoCoAdapter.search("MuJoCo panda")` is called
- **THEN** it returns the `franka_emika_panda` scene because "panda" matches its title

## REMOVED Requirements

None.
