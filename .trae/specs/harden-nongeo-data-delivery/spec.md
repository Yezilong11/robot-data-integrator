# 非几何数据交付链路补全 Spec

## Why

DATASET/SENSOR/POLICY/GRASP 四类非几何需求的 42 题评审：0–2 纯 PASS，大量元数据卡/摘要冒充交付（68B/100B/126B 摘要判 fulfilled）。根因三环缺口：源握手 ≠ 数据交付、降级当成功、验证无牙齿。本 spec 按商定方案 v1（决策 D1–D14）补齐交付链路：语义校验可见化、文件按命名定位、大文件不落本地、小文件真实下载、拿不到时显式交付下载指引。

## What Changes

- **语义校验补牙齿**：`_SEMANTIC_REQ_TYPES` 纳入 DATASET/SENSOR_DATA/POLICY_MODEL；`DataReq` 新增 `semantic_terms` 字段，由 parse_goal 的 LLM 提炼（形态 A），validate 规则判定、LLM 失败 fail-open 回退现有提取
- **文件选择器**：新增 `select_target_file(tree, req_type)`，按"扩展名白名单 + 名字信号"在源文件树定位目标文件，四类共用一张规则表，不解析文件内容
- **体积护栏 + 真实下载**：HEAD 预检（现成 `_head_content_length`），≤`max_fetch_bytes` 真实下载落盘；超限不落本地，交付文件级 `RawReference`
- **下载指引显性化**：超限/降级项落 `download_guide.json`（URL+size+原因+wget 命令）+ manifest `downloaded=false`；explain（`explain_quality`）注入未下载项清单，规则兜底自动 append 获取指引段；不新建 GETTING_DATA.md
- **完整性校验锚点**：每项 `downloaded=false` 必须存在 download_guide + explain 说明，缺则完整性 ERROR
- **GRASP 纳入**：dataset-skill 的 GRASP 降级链（ycb 摘要顶替、dexgrasp markdown）补 reference 与格式白名单护栏；grasp_label/*.npz 定位逻辑不动
- **验收口径（严口径）**：小文件下载成功 → PASS；超限 → FAIL（指引照给）；语义错配/指引缺失 → FAIL

## Impact

- Affected specs: 语义校验（validate）、目标解析（parse_goal）、检索装配（retrieve/assemble）、质量解释（explain_quality）、台账判定（verdict/backfill-errors）
- Affected code:
  - `src/rdi/graph/nodes/validate.py`
  - `src/rdi/graph/nodes/parse_goal.py`
  - `src/rdi/models/goal.py`
  - `src/rdi/intelligence/decisions.py`（explain_quality 注入）
  - `src/rdi/adapters/huggingface.py` / `zenodo.py` / `github.py`（tree/files 提取 + 下载/引用）
  - `src/rdi/skills/dataset_parse.py` / `sensor_data.py` / `policy_interface.py`（fallback 富文本指引）
  - `src/rdi/graph/nodes/assemble.py`（校验锚点）
  - 新增 `src/rdi/adapters/selectors.py`（select_target_file）

## ADDED Requirements

### Requirement: 非几何类型语义校验

系统 SHALL 对 DATASET / SENSOR_DATA / POLICY_MODEL 需求启用语义匹配校验：需求术语与产物标识文本零重叠时产出 content_validity ERROR。

#### Scenario: 语义错配被硬判
- **WHEN** dataset 需求"带动作标注的机器人操作数据集"命中日食音频记录（内容文本与术语零重叠）
- **THEN** validate 产出 ERROR（不受 is_fallback 豁免），驱动换源或如实失败

#### Scenario: 名词稀疏需求不误伤
- **WHEN** 需求无 object_name 且 semantic_terms/keywords 均为空
- **THEN** 语义校验跳过，行为等价现状

### Requirement: semantic_terms LLM 提炼（形态 A）

系统 SHALL 在 parse_goal 决策输出中由 LLM 提炼 `semantic_terms`（从 description 提取语义约束词）并存入 `DataReq`；LLM 不可用/解析失败时该字段为空，validate 回退现有提取（object_name / YCB 词典 / keywords），不中断流水线。

#### Scenario: LLM 失败 fail-open
- **WHEN** parse_goal 的 LLM 调用失败
- **THEN** semantic_terms 为空，validate 走现有规则提取，校验不失效

### Requirement: 文件选择器 select_target_file

系统 SHALL 提供 `select_target_file(tree, req_type)`，按 req_type 的扩展名白名单 + 名字信号优先级在源文件树中选择目标文件（候选排序），不解析文件内容。

| req_type | 扩展名白名单 | 名字信号（优先级） |
|---|---|---|
| POLICY_MODEL | .safetensors/.bin/.pt/.pth | policy/checkpoint/actuator/model |
| SENSOR_DATA | .csv/.json | sensor/torque/force/joint/time |
| DATASET | 按需求语义 | 需求数据集名/类目 |
| GRASP | .npz（复用 grasp_label/* 定位） | — |

### Requirement: 体积护栏与真实下载

系统 SHALL 对选中目标文件做 HEAD 预检：≤`max_fetch_bytes` 下载落盘；超限不落本地，构造文件级 `RawReference`（URL + size + reason）。

#### Scenario: 小文件真实下载
- **WHEN** 目标文件体积 ≤ max_fetch_bytes
- **THEN** 文件真实下载落盘，manifest 无 downloaded=false

#### Scenario: 大文件不落本地
- **WHEN** 目标文件体积 > max_fetch_bytes（含数 GB 级）
- **THEN** 本地零落盘，交付带直链/体积/原因的 RawReference

### Requirement: 下载指引显性化

系统 SHALL 为每条未下载项产出 `download_guide.json`（status/reason/source_file_url/file_size/method_hint(wget)/selected_by/alternatives）并在 manifest 中标 `downloaded=false` + file_url + file_size（不新增 manifest 字段）；explain 解释中说明"为什么未交付 + 如何获取"，规则兜底时自动 append 获取指引段（保证 wget 命令恒在）。

### Requirement: 完整性校验锚点

系统 SHALL 在打包时校验：任一 `downloaded=false` 项必须同时存在 download_guide.json 与 explain 中的对应说明，缺任一项为完整性 ERROR。

## MODIFIED Requirements

### Requirement: _SEMANTIC_REQ_TYPES 扩展
原仅 GRASP/MESH/ROBOT_URDF/SIM_CONFIG；现加入 DataReqType.DATASET / SENSOR_DATA / POLICY_MODEL。

### Requirement: _extract_semantic_terms 读取优先级
现只从 object_name/YCB/keywords 提取；改为优先读取 `req.semantic_terms`，空则回退现有提取。

### Requirement: 验收口径（严口径）
原"带完整指引的降级可判 PASS_WITH_FALLBACK"；现改：小文件下载成功 → PASS；超限 → FAIL（指引照给，可手动补全）；语义错配 / 指引缺失 → FAIL。GRASP 大归档超限全 FAIL 为预期行为。