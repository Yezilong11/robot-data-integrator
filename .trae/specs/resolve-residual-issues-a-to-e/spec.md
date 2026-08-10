# 遗留问题 A-E 组逐项解决 Spec

## Why

上一轮 P0+P1 修复落地后，验证（Task 8）发现 4 项实现 gap（A 组），设计审查文档中还有 P0+P1 未覆盖的真实缺陷（B/C 组）、既定 P2 演进项（D 组）与体验/可观测性问题（E 组）。用户要求按 A→E 顺序逐项解决，把「demo 能跑通」推进到「科研人员日常使用」。

## What Changes

### A 组：实现 gap 补齐（本次 P0+P1 范围收口）
- **A1 资产进 manifest/checksums**：assemble 对落盘资产文件（mesh/texture/include）生成 ManifestFile 条目（downloaded=true、checksum 计算、format 按扩展名推断），并纳入 checksums.txt。
- **A2 资产递归下载 + MJCF 校验**：`_download_xml_with_assets` 递归解析 include 子 XML 的 mesh/texture 引用（有限深度防循环、按相对路径去重）；`_mujoco_runtime_check` 把 `item.assets` 写入临时目录后再加载，不再恒为 skipped。
- **A3 `package://` 引用下载**：`package://` 后路径按「xml 所在目录为基准的相对路径」解析下载（pybullet_robots panda 的实际语义）；下载失败降级为 missing asset 并计入 validate 警告。
- **A4 合成占位 is_fallback 标记**：`StandardResult` 增加 `is_fallback: bool = False`；grasp_parse 合成降级置 True；registry 装配 ParsedItem 时 `is_fallback = result.is_fallback or skill_result.is_fallback`。

### B 组：R 系列可复现性（R4/R5/R6）
- **B1 URL 钉 commit（R4）**：所有 raw.githubusercontent / 可变分支 URL 改为钉 commit hash（settings 源配置 + franka 的 `_PANDA_*_URL`），代码注释记录 pin 日期；禁止 `master`/`main` 分支引用。
- **B2 run_id 贯穿（R5）**：流程启动时生成 `run_id`（时间戳+随机短串）；`SystemState.run_id` 承载；`manifest.package_info.run_id` 落盘；前端展示。
- **B3 缓存失效与键稳定（R6）**：`_make_cache_key` 规范化 URL（query 排序、去除冗余）；内存缓存加 TTL 与最大条目数（settings 可配 `cache_ttl_seconds` / `cache_max_entries`）；franka 主/降级路径缓存键明确区分（不互相覆盖）。

### C 组：D/E 业务链路（D1/D2/D5/D7/H3）
- **C1 object_name 接通（D2）**：`DataReq` 增加 `object_name`（LLM 从目标提取）；retrieve_data 将 object_name 透传给 search/fetch kwargs；graspnet/ycb 用 object_name 精确定位目标文件（接通 `_graspnet_objects` 映射与 YCB 物体名）。
- **C2 硬编码清单外明确提示（D1）**：adapter search 对清单外目标返回「该源仅收录已知目标，未收录 xxx」的可诊断语义，MissingItem.reason 明确「有源但未收录」，不再静默返回空。
- **C3 合成占位降级（D5）**：grasp_parse 合成抓取不再以 success 冒充真实数据——返回 MissingItem（reason 说明原始数据缺失、合成占位仅作参考）**BREAKING**：抓取类需求在数据集无真实标注时变为缺失项而非合成数据。
- **C4 类型错配检测（D7）**：registry/parse_convert 校验需求期望的 canonical_format 与实际返回（如 GRASP 期望 CanonicalGrasp 却拿到 obj），不匹配记 MissingItem（reason 含期望/实际格式）。
- **C5 仅修订失败 req（H3）**：human_review unsatisfied/revised 时只对失败/有问题的 req 重检索+重解析，已成功项沿用不重拉；state 增加 `retry_req_ids` 承载待修订集合。

### D 组：P2 演进（6.1/6.2/D6）
- **D1 物理量纲显式化（6.1）**：`ParsedItem` 增加 `units`、`coordinate_frame`、`timestamp_epoch` 元数据；`CanonicalGrasp` 增加 units/frame 标注；`DATASET_CONVENTIONS`（旋转/原点/单位）随数据落盘为包内 `units.json`，不再只存在于代码常量；skills 装配时从约定表填充并透传到 manifest。
- **D2 DataReqType 扩充（6.2）**：新增 CAMERA_CALIB / TEACHING_TRAJECTORY / ROBOT_CONFIG / BENCHMARK_TASK 四类；LLM 提示、前端类型选项、goal 解析同步；无内置 adapter/skill 的类型诚实失败（missing + reason「该类型暂无内置数据源」）而非塞入 UNKNOWN。
- **D3 本地数据集挂载（D6）**：settings 增加 `local_datasets: dict[str, str]`（来源→本地目录）；adapter 检索/下载时优先检查本地挂载目录，命中则用本地文件（不走网络）；与前端 per-req 注入（local_files）并存。

### E 组：体验与可观测性（6.4）
- **E1 前端分步进度**：前端运行改为分步推进（retrieve→parse→validate→assemble 逐步 yield 中间状态 + gr.Progress），不再黑盒一次性提交。
- **E2 日志启用**：接入 structlog，`LOG_LEVEL`/`LOG_FORMAT` 配置实际生效；核心节点（retrieve/parse/validate/assemble/human_review）增加结构化日志。
- **E3 演示包与真实产物隔离**：演示流程产物明确标记 demo（写入 demo 目录或 manifest 标记），不混入真实 output_packages；后端异常不再伪造 fallback 包当成功展示。

## Impact

- 受影响 specs：`SystemState`（run_id/retry_req_ids）、`DataReq`（object_name）、`DataReqType`（+4 类型）、`ParsedItem`（units/coordinate_frame/timestamp_epoch）、`CanonicalGrasp`（units/frame）、`StandardResult`（is_fallback）、`ManifestFile`/`package_info`（run_id、资产条目）、`RawData`/`ParsedItem` 资产链路（递归/package://）。
- 受影响代码：adapters/base.py（缓存、递归、package://）、adapters/franka.py、settings.py（URL 钉 commit、cache 配置、local_datasets）、graph/state.py、nodes/retrieve_data.py、nodes/parse_convert.py、nodes/validate.py、nodes/assemble.py、nodes/human_review.py、skills/registry.py、skills/grasp_parse.py、skills/urdf_convert.py、skills/sensor_data.py、models/common.py、models/goal.py、models/manifest.py、models/parsed.py、frontend/app.py、日志配置、README。
- 用户可见变化：数据包每个文件（含资产）都有 checksum；MJCF/URDF 包可离线完整加载；抓取类需求无真实数据时明确缺失而非合成冒充；manifest 关联 run_id 且类型/来源语义诚实；前端有分步进度；本地已有数据集直接挂载使用。
- 兼容性：C3（合成占位→MissingItem）为行为变更（BREAKING）；D2（+4 DataReqType）为新增枚举（兼容）；其余为加字段/配置（兼容）。

## ADDED Requirements

### Requirement: 资产文件纳入 manifest 与校验和（A1）

The system SHALL 为数据包内落盘的每个资产文件生成 manifest 条目与 sha256。

#### Scenario: 资产可校验
- **WHEN** assemble 写入 mesh/texture/include 资产文件
- **THEN** manifest 含对应 ManifestFile（downloaded=true、checksum_sha256 与磁盘一致、format 按扩展名），且 checksums.txt 覆盖这些文件

### Requirement: 资产递归下载与 MJCF 深度校验（A2）

The system SHALL 递归解析 include 引用的资产，并让 MJCF 校验消费 assets。

#### Scenario: MJCF 链离线完整
- **WHEN** MJCF 主文件 include 子 XML，子 XML 引用 assets/mesh
- **THEN** 资产全部进入 RawData.assets；`_mujoco_runtime_check` 用 assets 落地临时目录后加载，不再恒 skipped

#### Scenario: 递归防环
- **WHEN** include 链存在循环引用或深度超过上限
- **THEN** 递归终止（深度上限 + 已下载路径去重），不抛异常

### Requirement: package:// 引用解析（A3）

The system SHALL 尝试下载 URDF 中 `package://` 引用的资源。

#### Scenario: pybullet_robots URDF 自包含
- **WHEN** panda.urdf 引用 `package://meshes/...`
- **THEN** 资产按「xml 所在目录为基准的相对路径」解析并下载进 assets；无法解析的 package:// 引用计入 validate 警告而非静默

### Requirement: 合成占位显式标记（A4）

The system SHALL 在 skill 层显式标记合成降级。

#### Scenario: 合成抓取可识别
- **WHEN** grasp_parse 返回合成占位
- **THEN** StandardResult.is_fallback=True，ParsedItem.is_fallback=True（与检索层 is_fallback 合并），manifest 可见

### Requirement: URL 钉 commit（B1）

The system SHALL 禁止可变分支 URL，统一钉 commit。

#### Scenario: 实验可复现
- **WHEN** 两次运行同一 item_id
- **THEN** 下载内容一致（URL 指向固定 commit，非 master/main）；代码注释记录 pin 日期

### Requirement: run_id 贯穿（B2）

The system SHALL 生成并贯穿 run_id。

#### Scenario: 溯源可关联
- **WHEN** 一次完整流程运行
- **THEN** SystemState.run_id 非空，manifest.package_info.run_id 等于该值，前端可见

### Requirement: 缓存失效与键稳定（B3）

The system SHALL 提供带 TTL 与大小上限的缓存，键规范化稳定。

#### Scenario: 重跑不拿过期数据
- **WHEN** 缓存条目超过 TTL（settings.cache_ttl_seconds）
- **THEN** 重新请求而非返回过期数据；franka 主/降级路径缓存互不覆盖

### Requirement: object_name 接通（C1）

The system SHALL 将目标物体名贯穿到检索与解析。

#### Scenario: 按物体名取数据
- **WHEN** 目标含「banana 的抓取标注」且 object_name=banana
- **THEN** graspnet/ycb 按 object_name 定位对应文件，而非下载仓库第一个文件

### Requirement: 清单外目标可诊断（C2）

The system SHALL 明确告知「有源但未收录」。

#### Scenario: 清单外目标
- **WHEN** search 目标不在 adapter 硬编码清单内
- **THEN** MissingItem.reason 含「该源仅收录已知目标」语义，不静默返回空

### Requirement: 合成占位不冒充成功（C3）

The system SHALL 将合成降级结果降为缺失项。

#### Scenario: 无真实抓取数据
- **WHEN** 数据集仅返回元数据且无真实抓取文件
- **THEN** grasp_parse 返回 MissingItem（reason 说明原始数据缺失、合成占位仅作参考），不再以 success 交付合成数据

### Requirement: 类型错配检测（C4）

The system SHALL 检测需求类型与返回格式不匹配。

#### Scenario: GRASP 拿到 obj
- **WHEN** 需求为 GRASP 但返回格式无法装配为 CanonicalGrasp
- **THEN** 记 MissingItem（reason 含期望/实际格式），不静默 success

### Requirement: 仅修订失败项（C5）

The system SHALL 支持只重跑失败的 req。

#### Scenario: 修订不重拉成功项
- **WHEN** 用户 unsatisfied/revised 且指定待修订 req 集合
- **THEN** 仅这些 req 重新检索/解析/校验，已成功项沿用

### Requirement: 物理量纲显式化（D1）

The system SHALL 记录并落盘单位/坐标系/时间基准。

#### Scenario: 数据带单位标注
- **WHEN** 装配 CanonicalGrasp/CanonicalRobot/SensorDataset
- **THEN** ParsedItem.units/coordinate_frame/timestamp_epoch 非空；包内 units.json 含每类数据的旋转/原点/单位约定

### Requirement: 需求类型扩充（D2）

The system SHALL 支持科研常见需求类型。

#### Scenario: 新类型诚实失败
- **WHEN** 目标为相机标定/示教轨迹/机器人配置/benchmark 任务
- **THEN** 类型可识别（CAMERA_CALIB/TEACHING_TRAJECTORY/ROBOT_CONFIG/BENCHMARK_TASK），无内置源时 missing + reason「暂无内置数据源」

### Requirement: 本地数据集挂载（D3）

The system SHALL 支持来源级本地目录挂载。

#### Scenario: 本地命中不走网络
- **WHEN** settings.local_datasets 配置了 graspnet 目录且本地存在目标文件
- **THEN** adapter 直接使用本地文件（跳过网络检索/下载）

### Requirement: 前端分步进度（E1）

The system SHALL 分步展示流程进度。

#### Scenario: 运行可见中间状态
- **WHEN** 前端运行流程
- **THEN** 逐步显示 retrieve/parse/validate/assemble 各阶段状态与结果，非一次性黑盒提交

### Requirement: 日志生效（E2）

The system SHALL 启用结构化日志。

#### Scenario: 关键节点有日志
- **WHEN** 节点执行
- **THEN** retrieve/parse/validate/assemble/human_review 输出结构化日志，LOG_LEVEL/LOG_FORMAT 配置生效

### Requirement: 演示与真实产物隔离（E3）

The system SHALL 隔离演示产物与真实产物。

#### Scenario: 演示包明确标记
- **WHEN** 演示流程生成产物
- **THEN** 产物带 demo 标记（独立目录或 manifest 标记），不混入真实 output_packages；真实流程不伪造 fallback 包

## MODIFIED Requirements

### Requirement: 资产下载策略扩展

原 `_download_xml_with_assets`（仅直接引用）扩展为递归 include + package:// 解析（见 A2/A3）。缓存行为扩展为 TTL/键稳定（见 B3）。

#### Scenario: 旧行为兼容
- **WHEN** URDF/MJCF 无 include 无 package:// 引用
- **THEN** 行为与上一版一致（assets 为空或仅直接引用）

## REMOVED Requirements

### Requirement: 合成抓取以 success 交付

**Reason**: 研究者会把合成占位当真实数据（E3/D5）。
**Migration**: 降级为 MissingItem（reason 说明），真实抓取文件仍可通过 reference 手动获取。
