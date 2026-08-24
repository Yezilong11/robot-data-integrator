# 二轮测试问题修复 Spec

## Why

全量 122 题测试可用率仅 59.0%，50 个 FAIL 暴露多项系统性缺陷：元数据/摘要冒充真实数据却判 complete、检索命中与题设目标语义错配、URDF mesh 依赖缺失静默放行、markdown 摘要不可消费、检索轴失败仍空转 3 轮、解析类型偏移、LLM 列表输出不兼容，以及记录校验工具口径滞后。多数缺陷可通过代码层修复消除，使后续测试如实反映真实数据质量。

## What Changes

- **P0-A** `src/rdi/graph/nodes/validate.py`：新增横切内容校验——元数据代理占位检测（`_is_metadata_proxy`）与目标-内容语义匹配（`_semantic_mismatch`），对 GRASP/MESH/ROBOT_URDF/SIM_CONFIG 四类启用；`is_fallback` 不再豁免内容校验；issue 标注 `context["issue_type"]="content_validity"`。
- **P0-B** `src/rdi/graph/nodes/assemble.py`：内容有效性 ERROR 的 req 不入 manifest_files，转为 MissingItem（含原原因），占位项不再判 complete（判 partial/failed）。
- **P0-C** `src/rdi/adapters/base.py` + `validate.py`：资产下载失败写入 `RawData.metadata["assets_missing"]`（XML 远程与本地分支均覆盖），`_validate_urdf_loadability` 结合缺失清单判 ERROR，且 raw_bytes 缺失分支也执行 XML 引用核对。
- **P0-D** `src/rdi/skills/dataset_parse.py`：新增 `_parse_markdown`，github/HF 摘要按 fallback summary 消费（is_fallback=True、completeness 55%、warning 注明未下载数据），不再 0 文件。
- **P1-A** `validate.py` + `src/rdi/graph/edges.py`：检索侧无数据类 issue 标注 `context["issue_type"]="retrieval_axis"`；`route_after_validate` 在"全部 ERROR 均为检索轴且无新增 retry_req_ids"时直接 pass，不再空转 3 轮。
- **P1-B** `src/rdi/graph/nodes/parse_goal.py`：GRASP 强词补「抓取标签/抓取标注/抓取规划/grasp label/grasp annotation/grasp planning」；`_normalize_datareq` 增加 DATASET→GRASP 单向消歧（前置）。
- **P1-C** `src/rdi/intelligence/client.py`：`call_structured` 捕获 ValidationError 后对 list[str] 字段做逗号/顿号/分号拆分归一化并重试一次（qwen-max 兼容）。
- **P2-A** `scripts/manage_test_records.py`：`ALLOWED_FAILURE_CATEGORIES` 对齐 second_round_plan 八类（P1_PARSE…P8_OTHER）；旧枚举值兼容映射为 WARNING 而非 ERROR。
- **P2-B** 管理脚本台账输出增加 `round` 列（一轮 63 / 二轮 59 由分配清单派生），重新生成本地台账。
- **P2-C** 新增 `docs/fix_actions_checklist.md`：截图补齐、一轮补正、一轮 15 FAIL 处置、122 题复核分配、P0 补位的成员级管理动作清单。
- **BREAKING**：旧 `ALLOWED_FAILURE_CATEGORIES` 枚举（P5_RUNTIME/P6_FRONTEND/P7_ENV）移除，历史记录按映射等价转换登记 WARNING。

## Impact

- Affected specs：content-validity 校验、retrieval 路由、goal 解析、LLM 客户端、记录治理
- Affected code：`src/rdi/graph/nodes/validate.py`、`assemble.py`、`parse_goal.py`、`src/rdi/graph/edges.py`、`src/rdi/adapters/base.py`、`src/rdi/skills/dataset_parse.py`、`src/rdi/intelligence/client.py`、`scripts/manage_test_records.py`、`records/_management/progress.csv`、`assignments.csv`
- 新增测试：`tests/unit/graph/`、`tests/unit/skills/`、`tests/unit/adapters/`、`tests/unit/intelligence/` 对应用例（见各 Requirement Scenario）
- 新增文档：`docs/fix_actions_checklist.md`

## ADDED Requirements

### Requirement: 元数据代理占位检测
系统 SHALL 在 validate 阶段检测每个 ParsedItem 是否仅为元数据/占位，并判 ERROR（不受 is_fallback 豁免）。
- 检测规则（任一命中即占位）：`reference` 非空（大文件仅 URL）；`canonical_format == "DatasetSummary"` 且 `data.file_tree` 为空；序列化后 < 200B 且为 fallback 来源（`is_fallback=True` 或 `data_source_quality=="fallback"`）。
- 常量 `_PLACEHOLDER_BYTE_THRESHOLD = 200`，issue 消息「需求实际未获得真实数据（仅元数据/占位）」；issue 带 `context={"issue_type": "content_validity"}`。

#### Scenario: markdown 摘要项被如实降级
- **WHEN** github README 经 DatasetSkill 消费为 fallback summary 且 file_tree 为空
- **THEN** validate 产生 content_validity ERROR，包不再判 complete

### Requirement: 目标-内容语义匹配校验
系统 SHALL 对 GRASP / MESH / ROBOT_URDF / SIM_CONFIG 四类启用目标-内容语义匹配：目标实体词（object_name / keywords / description 中的 YCB 中英名单与 YCB id）与该 ParsedItem 标识文本（name + source_url 末两段 + data 的 title/description 前 200 字符）零重叠时判 ERROR「内容与需求语义不符（目标 X，实际 Y）」。
- 泛词过滤名单（robot/dataset/mesh/grasp/模型/物体/抓取/配置/仿真等）不计入术语；目标术语为空时跳过。
- 以 `ponytail:` 注释标注轻量规则上限与升级路径（LLM 深度校验）。

#### Scenario: UR5 需求拿到 franka 资产
- **WHEN** retriever 对「UR5」需求返回 franka panda URDF
- **THEN** validate 判语义不符 ERROR，触发重试换源或如实失败

### Requirement: assemble 排除占位项
系统 SHALL 将 validation_issues 中 `issue_type=="content_validity"` 的 ERROR 对应 req 排除出 manifest_files，转为 MissingItem（reason="内容有效性未通过" + 原原因），使包状态判 partial（非必需）或 failed（REQUIRED），杜绝元数据判 complete。

### Requirement: URDF 资产缺失显性化
系统 SHALL 将资产下载失败显式记录：`_download_xml_with_assets` 与 `_local_assets_from_xml` 把失败资产写入 `RawData.metadata["assets_missing"]`；`_validate_urdf_loadability` 在 raw_bytes 缺失分支也执行 XML 引用核对，缺失 mesh 判 ERROR「引用的外部资源缺失: …」。
- `metadata["assets_missing"]` 经 parse_convert 透传到 ParsedItem（warnings 或 metadata），validate 据此判 ERROR。

#### Scenario: ms_011 类 cup mesh 缺失
- **WHEN** YCB cup URDF 的 mesh 下载失败被记录到 assets_missing
- **THEN** validate 判 ERROR，包判 partial/failed 而非 complete

### Requirement: DatasetSkill 消费 markdown 摘要
系统 SHALL 让 `DatasetSkill.process` 支持 markdown/md 及 markdown 特征内容：提取首个 `# ` 标题与首个非空段为 description，file_tree 为空，返回 `StandardResult(success=True, is_fallback=True, data_source_quality="fallback", completeness_pct=55, confidence_score=0.6, warnings=["仅数据集摘要（markdown），未下载数据文件"])`。

#### Scenario: github README 摘要
- **WHEN** github 源对 dataset 需求返回 README markdown
- **THEN** DatasetSkill 返回 fallback summary（非 success=False 0 文件），validate 配合占位检测如实降级

### Requirement: validate 重试路由区分检索轴
系统 SHALL 在 node_validate 缺失类（missing 需求、result.data 为 None）issue 上加 `context["issue_type"]="retrieval_axis"`；`route_after_validate` 当全部 ERROR 均为检索轴且无新增 retry_req_ids 时返回 pass（进 assemble 如实报失败），不再空转 3 轮；内容/语义/可加载性 ERROR 仍走 retry（≤3 轮不变）。

#### Scenario: 源超时全失败
- **WHEN** 某需求的全部候选源均超时/未命中，validate 产生检索轴 ERROR
- **THEN** 路由直接 pass，P2_RETRIEVE 不再 3 轮空转

### Requirement: 抓取解析消歧
系统 SHALL 补 GRASP 强词（抓取标签/抓取标注/抓取规划/grasp label/grasp annotation/grasp planning），并在 `_normalize_datareq` 前置 DATASET→GRASP 单向消歧（文本含上述 GRASP 数据内容词且当前判定为 DATASET 时改写为 GRASP，不影响"机器人抓取数据集"类 DATASET 语义题）。

#### Scenario: ss_graspnet_004 类文本
- **WHEN** 描述为「抓取标签/数据集」类但题设预期 grasp
- **THEN** req_type 判 GRASP 而非 DATASET

### Requirement: LLM 列表输出归一化
系统 SHALL 在 `call_structured` 捕获 ValidationError 后，对 schema 中 list[str] 字段按 `[，,、;;；\s]+` 拆分字符串为数组后重试一次；仍失败走原降级路径。

#### Scenario: qwen-max 逗号字符串
- **WHEN** 模型对 keywords 返回 "a, b, c" 字符串
- **THEN** 归一化为 ["a","b","c"] 后通过校验

### Requirement: 记录校验枚举与台账轮次
系统 SHALL 将 `ALLOWED_FAILURE_CATEGORIES` 更新为 eight 类（P1_PARSE / P2_RETRIEVE / P3_SOURCE / P4_FORMAT / P5_LLM / P6_VALIDATE / P7_PACKAGE / P8_OTHER），旧值（P5_RUNTIME/P6_FRONTEND/P7_ENV）映射为等价新值并登记 WARNING；台账输出增加 `round` 列（一轮=1、二轮=2），一轮/二轮筛选各返回 63/59 行。

## MODIFIED Requirements

### Requirement: is_fallback 内容校验豁免取消
原 `_check_loadability` 对 `is_fallback` 项跳过深度校验（仅 WARNING）的行为修改为：保留格式/加载跳过，但新增的内容有效性与语义校验对所有项一律生效，不受 is_fallback 豁免。

### Requirement: 管理脚本枚举口径
原 `ALLOWED_FAILURE_CATEGORIES`（含 P5_RUNTIME/P6_FRONTEND/P7_ENV）更新为 second_round_plan 八类，历史记录按映射等价转换。

## REMOVED Requirements

### Requirement: 校验对占位数据的放行
**Reason**：占位/元数据冒充被判 successful 是 50 个 FAIL 的最大共性根因，放行使包"有文件即 complete"。
**Migration**：内容校验替代——占位项判 ERROR，assemble 移出 manifest 并判 partial/failed。

### Requirement: 旧 failure_category 枚举值
**Reason**：与 second_round_plan 记录口径不一致。
**Migration**：P5_RUNTIME→P6_VALIDATE、P6_FRONTEND→P8_OTHER、P7_ENV→P8_OTHER 等价映射，登记 WARNING 不报 ERROR。