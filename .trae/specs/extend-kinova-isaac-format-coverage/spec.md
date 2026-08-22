# Kinova/Isaac 格式覆盖度补全 Spec（spec-2）

> change-id: extend-kinova-isaac-format-coverage
> 用户授权全权主导实施。范围：kinova 资产缺失显性化 + isaac 收录/降级诚实化 + 回归验证。
> 前提（上轮分析结论）：skill 解析层本身无格式缺口（URDFSkill 支持 urdf/xacro；SimConfigSkill 白名单含 xml/mjcf/mujoco/json/py/python/yaml 并对非 MJCF 降级）；6 个 FAIL（ss_kinova_001/003、ms_009、ss_isaac_003/005）真实根因在 adapter 收录覆盖、资产完整性、降级产物语义诚实三层。

## Why

二轮测试 kinova 3 题全部因 URDF 引用的 8~9 个 STL mesh 静默缺失而 FAIL，且 fix-round2 的 assets_missing 显性化未覆盖 kinova 私有下载路径，修复后仍会失败；isaac 2 题因源收录仅 6 个已知目标（无 UR5/kitchen）致 missing/错配，且对 python 输入生成的"最小 MJCF 空壳"在 validate 被判通过——"验证通过但内容不实"。

## What Changes

- **kinova 资产缺失显性化**（`src/rdi/adapters/kinova.py`）：`_download_assets` 与本地挂载路径对下载失败的 mesh/texture 引用清单写入 `RawData.metadata["assets_missing"]`（复用 fix-round2 `_download_xml_with_assets` 同款模式），validate 据此判 ERROR 并给出缺失资产清单。
- **isaac 降级产物诚实化**（`src/rdi/skills/sim_config.py`）：对非 MJCF（python/yaml 等）生成的最小 MJCF 结果携带"降级场景不含机器人/任务语义"标记，validate 对该标记降判 warning 而非通过。
- **SIM_CONFIG 语义错配回退确认**（回归验证）：R2 语义校验对 SIM_CONFIG 已启用，补单测确认 franka.py 与 req UR5 零重叠判 error。
- **IsaacLab 收录扩充（先核实后补）**（`src/rdi/adapters/isaac.py`）：核实 IsaacLab 仓库 `source/isaaclab_assets/isaaclab_assets/robots/` 下是否存在 UR5（ur5e）等工业机械臂资产文件；存在才补入 `_FALLBACK_EXAMPLES`，不存在如实挂账不补。

**不做（明确排除）**：不虚构任何 URL/资产；不改 isaac fetch 的 python 返回格式；不做多源预算调度（spec-3）；不改 `per_req_timeout`。

## Impact

- Affected specs: fix-round2-test-issues（R3 assets_missing 模式复用）、improve-retrieve-hit-and-record-closure（检索/校验链路）
- Affected code:
  - `src/rdi/adapters/kinova.py`——`_download_assets` + `fetch` 本地路径透传 missing 清单
  - `src/rdi/skills/sim_config.py`——降级结果标记
  - `src/rdi/adapters/isaac.py`——`_FALLBACK_EXAMPLES` 扩充（条件性）
  - 新测试：`tests/unit/adapters/test_kinova_assets.py`、`tests/unit/skills/test_sim_config_honesty.py`；扩展语义校验单测

## ADDED Requirements

### Requirement: kinova 资产缺失显性化
kinova 适配器 SHALL 将下载失败的 mesh/texture 引用清单写入检索结果元数据，供 validate 显式判 ERROR。

#### Scenario: 网络资产下载部分失败
- **WHEN** kinova fetch 的 URDF 引用 N 个 mesh，其中 M 个（M>0）下载失败（网络错误/404）
- **THEN** `RawData.metadata["assets_missing"]` 含该 M 个引用清单，manifest 判 ERROR 并列出缺失资产路径

#### Scenario: 本地挂载路径资产缺失
- **WHEN** `_local_raw` 命中的本地 URDF 引用 mesh 但本地镜像无对应文件
- **THEN** 同样产生 assets_missing 清单（与网络路径行为一致）

#### Scenario: 资产全部下载成功
- **WHEN** kinova fetch 所有 mesh/texture 下载成功
- **THEN** 无 assets_missing，manifest 不因资产缺失判 ERROR（行为与修复前一致）

### Requirement: isaac 降级产物语义诚实
sim_config 对非 MJCF 输入生成的降级 MJCF SHALL 携带"降级场景不含机器人/任务语义"标记，validate 对该标记降判 warning 而非通过。

#### Scenario: 非 MJCF 输入降级
- **WHEN** sim_config 处理 isaac python/yaml 输入并生成最小 MJCF（仅地面+相机）
- **THEN** 结果携带降级语义标记，manifest 对本项判 warning（不再 silent passed）

### Requirement: SIM_CONFIG 语义错配回退
SIM_CONFIG 需求语义错配（如请求 UR5、获得 Franka）SHALL 由既有语义校验判 error（回归确认）。

#### Scenario: 语义零重叠
- **WHEN** validate 检查 sim_config 项且 req 目标术语与项标识文本零重叠
- **THEN** 该项判 error（content_validity），与 GRASP/MESH/ROBOT_URDF 一致

## MODIFIED Requirements

无既有需求被修改（均为新增/回归确认）。

## REMOVED Requirements

无。