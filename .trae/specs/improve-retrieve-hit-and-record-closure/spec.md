# 检索命中与记录闭环改进 Spec（spec-1）

> change-id: improve-retrieve-hit-and-record-closure
> 范围：仅 spec-1（检索候选预筛 + FAIL error 回填）。spec-2（skill 格式覆盖度）、spec-3（调度与场景组装）另行立项。

## Why

二轮全量 122 题 50 个 FAIL 中 **P2_RETRIEVE 占 20**（最大簇）：检索对 `search_results[0]` 盲取即 fetch（[retrieve_data.py:439](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/graph/nodes/retrieve_data.py#L439)），"拿错候选"与"拿不到"混杂——已具备横切语义校验能力（`_semantic_mismatch`），但只用在 validate 事后拦截，没有用于**检索期选候选**，多源场景首候选拿错即浪费预算且退无可退。同时 50 个 FAIL 记录几乎未填 error 原文（"检索未成功时必须填写 error"），真实失败原因不可考，归因全靠反推。

## What Changes

- **检索候选语义预筛**（`src/rdi/graph/nodes/retrieve_data.py`，复用 `src/rdi/graph/nodes/validate.py` 的语义抽词/匹配函数）：
  - GRASP / MESH / ROBOT_URDF / SIM_CONFIG 四类需求且目标术语非空时，fetch 前对 `search_results[:5]` 计算"命中术语得分"，选得分最高者 fetch；
  - 全部候选零重叠时**保持 fetch search_results[0] 的原行为**（不改变成功/失败边界，validate 层 content_validity ERROR 仍兜底），仅追加诊断到 `search_failures` 供 missing/审计。
- **FAIL error 自动回填**（`scripts/manage_test_records.py`）：
  - 新增 `backfill-errors` 命令：对已判定 FAIL 且无 error 的记录，从 record 现有结构化字段（retrieve.status=error/timeout/missing、RetrievalError 信息、diagnostic）生成 error 摘要回填；无结构化来源的标记"需人工补正"，由成员补正后复核。

**不做（明确排除）**：不改 fetch 成功/失败判定语义；不做多源预算加权（spec-3）；不改 `per_req_timeout`；不重写 SearchResult/adapter。

## Impact

- Affected specs: fix-round2-test-issues（validate 语义校验层，本规格复用其抽词/匹配函数）、llm-decision-layer、implement-third-integration（检索链路）
- Affected code:
  - `src/rdi/graph/nodes/validate.py`——将 `_extract_semantic_terms` / `_term_in` 暴露为可复用公共函数（薄封装，不移动实现）
  - `src/rdi/graph/nodes/retrieve_data.py`——候选预筛接入（~20 行）
  - `scripts/manage_test_records.py`——`backfill-errors` 子命令
  - 新测试：`tests/unit/graph/test_retrieve_candidate_preselection.py`；扩展 `tests/unit/` 记录脚本测试

## ADDED Requirements

### Requirement: 检索候选语义预筛
检索在候选命中时 SHALL 优先 fetch 与需求目标语义重叠最多的候选，而不是无条件取第一个。

#### Scenario: 多候选中存在语义匹配项
- **WHEN** retrieving GRASP/MESH/ROBOT_URDF/SIM_CONFIG 且需求含目标实体术语，`search_results` 多个候选且其中第 2 个候选标识文本命中"banana"等术语而第 1 个未命中
- **THEN** 检索 fetch 第 2 个（命中术语得分最高者），不 fetch 第 1 个

#### Scenario: 全候选零重叠保持不变
- **WHEN** 需求术语非空但所有候选标识文本零重叠
- **THEN** 仍 fetch `search_results[0]`（行为与修复前一致），并在 `search_failures` 追加"候选语义零重叠"诊断

#### Scenario: 非启用类型/术语为空保持原行为
- **WHEN** req_type 不在 GRASP/MESH/ROBOT_URDF/SIM_CONFIG，或目标术语为空
- **THEN** 直接 fetch `search_results[0]`，零额外开销

### Requirement: FAIL error 自动回填
记录治理脚本 SHALL 提供 `backfill-errors` 命令，从既有结构化字段补全 FAIL 记录 error。

#### Scenario: 有结构化依据可回填
- **WHEN** 运行 `manage_test_records.py backfill-errors`，某 FAIL 记录 retrieve.status=error/timeout 或含 RetrievalError/diagnostic 信息
- **THEN** 记录 error 字段被回填该摘要，validate 后不再报"检索未成功时必须填写 error"

#### Scenario: 无结构化依据
- **WHEN** 某 FAIL 记录无任何可提取的错误依据
- **THEN** 该记录标记"需人工补正"（不虚构 error），登记 WARNING 提示成员补正

## MODIFIED Requirements

### Requirement: 记录校验 error 必填（既有）
- 保持"检索未成功时必须填写 error"校验；`backfill-errors` 作为成员补正入口，回填后校验 ERROR 收敛。

## REMOVED Requirements

无。