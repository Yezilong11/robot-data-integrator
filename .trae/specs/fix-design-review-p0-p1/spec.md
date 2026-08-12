# 修复科研就绪设计审查 P0-P1 项 Spec

## Why

`docs/design-large-file-reference-model.md` 审查确认：系统设计目标是「demo 能跑通」而非「科研人员日常使用」，存在可复现性地基缺失、失败语义塌缩、数据不自包含、大文件无统一引用模型、静默降级撒谎、人机审查形同虚设等问题（上一轮逐条核对已全部验证属实）。本 spec 按审查第 8 章的 P0/P1 优先级落地修复，P2（units/frame、扩充 DataReqType、本地数据集挂载）留作后续演进。

## What Changes

- **P0-1 可复现性地基**：`SystemState.provenance` / `errors` 加 `Annotated[list, operator.add]` reducer 累积；`parse_convert` 移除无条件 `"errors": []` 清空；`node_retrieve_single` 把 `AdapterError` 结构化为 `RetrievalError`（error_type: timeout/rate_limit/not_found/auth/unknown）写入 `retrieval_errors`（当前是死字段）；`RetrievalResult.status` 语义枚举化（success / missing / error，error 附带 error_type）。
- **P0-2 真实 human_review**：builder 用 `MemorySaver` checkpointer 编译 + `interrupt_before=["human_review"]`；前端两阶段运行（首跑中断 → 用户提交审查决定 → resume）；`unsatisfied` 分支把 feedback 写入 `data_requirements` 后再重检索（避免相同 query 重跑）；拆分为 `validate_iteration` 与 `review_iteration` 两个独立计数器；新增 per-req 本地文件注入（前端可对单个 req_id 指定本地文件路径）。
- **P0-3 数据自包含**：`RawData` 增加 `assets: dict[str, bytes]`，base.py 新增 `_download_xml_with_assets` 递归下载 URDF/MJCF 引用的 mesh/texture/include 资源；`ParsedItem` 增加 `raw_bytes` / `assets`；URDF 校验改用 `load_meshes=True` 并对资源落地临时目录完整加载；assemble 把原始 XML + 资产按相对目录结构写入数据包。
- **P0-4 大文件统一引用模型**：新增 `RawReference {url, local_path, file_size, download_hint, reason}`，`RawData.reference` 承载引用模式；graspnet/arxiv/google_scanned/huggingface 的大文件/引用结果统一设置 reference（保留 data=JSON 供 skill 降级解析）；`ManifestFile` 记录 `{source, file_url, file_size, downloaded, local_path}`。
- **P1-1 manifest 完整性与 status 推导**：包内每个文件计算 sha256 并写入 `ManifestFile.checksum_sha256` + 包级 `checksums.txt`；`package_info` 增加 `pipeline_version`、`license`、`citation`；`status` 由 fulfilled/missing/ERROR 推导 complete/partial/failed，不再硬编码 "complete"。
- **P1-2 静默降级显式化**：`ManifestFile.data_source_quality` 默认值由 "fallback" 改为 "unknown"；assemble 不再 `or "fallback"`；`ManifestFile` 增加 `is_fallback`，由检索/解析阶段的降级标记透出。
- **P1-3 并行检索 + 超时预算**：`node_retrieve_data` 用 `asyncio.gather` 并行执行各需求检索，每个需求有独立超时预算（新增 `per_req_timeout` 配置，默认 60s），超时按 error 处理；README「并行检索」声明与实现一致。

## Impact

- 受影响 specs：`SystemState`（字段语义）、`RawData`/`ParsedItem`/`ManifestFile`/`RetrievalError`（模型字段）、`node_retrieve_data`/`node_parse_convert`/`node_validate`/`node_assemble`/`node_human_review`（节点行为）、`build_graph`（checkpointer/interrupt）、前端 `run_workflow`（两阶段）、全部相关 adapter（assets/reference）、README。
- 用户可见变化：数据包内含可被外部工具加载的原始 URDF/MJCF + 引用资产；manifest 提供文件校验和、真实来源标记（downloaded/local_path/引用）、正确 status；失败可区分限流/超时/未找到；审查真正在运行中等待用户决策。
- 兼容性：`RawData`/`ParsedItem`/`ManifestFile` 为**加字段**（`extra="forbid"` 不影响新增字段，新增均为可选/默认值），不破坏既有构造调用；`RetrievalResult.status` 仍是字符串三值，不破坏前端。

## ADDED Requirements

### Requirement: state 累积型溯源与错误

The system SHALL accumulate `provenance` and `errors` across graph nodes instead of last-value-overwriting.

#### Scenario: 溯源日志完整性

- **WHEN** 一次完整流程经过 parse_goal → retrieve_data → parse_convert → validate → assemble
- **THEN** `manifest.provenance_log` 包含上述每个节点的溯源行，而非只剩 assemble 一行

#### Scenario: 错误不被前序清空

- **WHEN** parse_goal 因 LLM 降级写入 `errors`，随后 parse_convert 执行
- **THEN** `state.errors` 仍保留 parse_goal 的错误记录（parse_convert 不得返回空列表覆盖）

### Requirement: 结构化失败语义

The system SHALL record typed per-source retrieval failures instead of silently swallowing them.

#### Scenario: 限流/超时/未找到可区分

- **WHEN** 某个需求的所有候选源均抛 `AdapterError`（429/超时/404/401 等）
- **THEN** `state.retrieval_errors` 包含对应 `RetrievalError`（error_type 分别为 rate_limit/timeout/not_found/auth/unknown），且 `RetrievalResult.status == "error"`，error_message 保留具体原因

### Requirement: 真实 human_review（checkpointer + interrupt）

The system SHALL pause the graph before `human_review` and resume with the user's actual decision.

#### Scenario: 两阶段运行

- **WHEN** 前端以真实流程运行且不预选决策
- **THEN** 首跑在 human_review 前中断返回中间状态；用户提交 decision/feedback 后 resume 继续，同一 thread 的中间结果不被丢弃

#### Scenario: unsatisfied 重检索携带反馈

- **WHEN** 用户 decision=unsatisfied 且给出 feedback
- **THEN** `data_requirements` 被 feedback 更新后再重检索，retrieve_data 使用更新后的需求与关键词，而非原样重跑

#### Scenario: 独立修订计数器

- **WHEN** validate 与 human_review 各自计数
- **THEN** validate 使用 `validate_iteration`、human_review 使用 `review_iteration`，互不污染；超过上限的强制 pass 在 manifest 中可见（revision_history 已有记录）

#### Scenario: per-req 本地文件注入

- **WHEN** 前端对某 req_id 指定本地文件路径
- **THEN** 该路径文件进入数据包对应 req 输出，跳过该需求的外部检索

### Requirement: 数据包自包含（URDF/MJCF 资产递归下载）

The system SHALL package URDF/MJCF 及其引用的全部 mesh/texture/include 资源。

#### Scenario: 外部工具可直接加载

- **WHEN** 数据包含 URDF/MJCF
- **THEN** 包内同时含原始 XML 文件与全部被引用资源（相对路径保持可解析），validate 以 `load_meshes=True` 完整加载通过

### Requirement: 大文件统一引用模型

The system SHALL represent reference-mode (不下载大文件) 结果通过统一的 `RawData.reference` 字段。

#### Scenario: 引用结果可识别

- **WHEN** graspnet/arxiv/google_scanned/huggingface 返回 metadata（引用）结果
- **THEN** `RawData.reference` 非空且含 `url`/`file_size`/`download_hint`；manifest 对应文件记录 `downloaded=false` 与 `local_path=""`

### Requirement: manifest 完整性

The system SHALL record checksum、pipeline 版本、许可、引用与真实来源标记。

#### Scenario: 校验与溯源

- **WHEN** assemble 生成数据包
- **THEN** 每个 `ManifestFile` 含 `checksum_sha256`、`is_fallback`、`data_source_quality`（默认 unknown）、`file_size`、`downloaded`、`local_path`；`package_info` 含 `pipeline_version`；包内含 `checksums.txt`

#### Scenario: status 推导

- **WHEN** 存在 0 文件或 REQUIRED 缺失
- **THEN** `package_info.status` 为 "failed"；部分缺失为 "partial"；全部满足为 "complete"（不再恒为 "complete"）

### Requirement: 并行检索与超时预算

The system SHALL retrieve multiple requirements in parallel with a per-requirement timeout budget.

#### Scenario: 多需求并行

- **WHEN** `node_retrieve_data` 收到 N 个需求
- **THEN** 各需求并行执行（asyncio.gather），单需求超时（`per_req_timeout`，默认 60s）按 error 记录，不阻塞其他需求；README 的「并行检索」描述与实现一致

## MODIFIED Requirements

### Requirement: parse_convert 不再清空错误

`node_parse_convert` SHALL 不再返回 `"errors": []`；只返回真实发生的错误（如无则省略该 key）。

#### Scenario: 错误累积

- **WHEN** parse_convert 处理中存在失败项
- **THEN** 该失败被记为 missing_item，若存在异常则写入 `errors`

### Requirement: registry 失败语义透出

`SkillRegistry.process_retrieval_result` SHALL 保留 `RetrievalResult` 的失败类型语义到 `MissingItem.reason`，不再把「搜索无结果」与「下载被限流/超时」混为一谈。

#### Scenario: 失败原因可诊断

- **WHEN** status="error"（含 error_type）的 result 进入解析阶段
- **THEN** 生成的 `MissingItem.reason` 含具体错误类型与原因

### Requirement: assemble 不默认撒谎

`node_assemble` SHALL 不再把未标记的质量打上 "fallback"。

#### Scenario: 真实下载不被标 fallback

- **WHEN** URDFSkill 等未显式设置 `data_source_quality` 的成功项落盘
- **THEN** manifest 中 `data_source_quality` 为 "unknown" 而非 "fallback"

## REMOVED Requirements

### Requirement: 硬编码 status="complete"

**Reason**: 恒为 complete 掩盖 0 文件/REQUIRED 缺失的真实状态（E5）。
**Migration**: 由 fulfilled/missing/ERROR 计数推导 complete/partial/failed。

### Requirement: 前端一次性预选 review_decision

**Reason**: 审查在运行前预选、单次 ainvoke 跑完全图，审查形同虚设（H1）。
**Migration**: 前端改为两阶段（运行中断 → 提交决策 → resume），仅当用户提交时才生效。
