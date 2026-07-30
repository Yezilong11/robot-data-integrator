# 接入 Adapter 到 retrieve_data 节点 Spec

## Why

`node_retrieve_single` 当前是骨架实现：返回 `placeholder data`，不调用任何 Adapter，Hermes 经验记录的 source 固定为 `github`。C 工程师已交付 15 个 Adapter（含双路径 fallback、类型安全、集中 URL 配置），B 工程师需要把 `retrieve_data` 节点从骨架填成真实实现，完成第一次 B↔C 联调。

本 spec 只覆盖 `retrieve_data` 节点的接入工作，不修改 Adapter 内部实现，不修改 Hermes 引擎本身。

## What Changes

- **MODIFIED** `src/rdi/graph/nodes/retrieve_data.py`：
  - `node_retrieve_single` 改为 `async def`
  - 通过 `select_adapter(DataReqType(req_type))` 获取候选 Adapter 类列表
  - 通过 `hermes.get_source_priority(req_type)` 获取按成功率排序的候选源（用于指导 fallback 顺序）
  - 按优先级逐个尝试 `await adapter.search(query)` → `await adapter.fetch(item_id)`
  - 任一源成功即停止，全部失败则返回 `status="error"` / `"missing"`
  - 真正使用 `inject_experience` 返回的经验提示（拼入 provenance）
  - `record_experience` 传入真实的 `status`、`sources_used`、`elapsed_seconds`
  - 删除两处 `ponytail:` 注释
- **MODIFIED** `tests/unit/graph/test_retrieve_data.py`：
  - 现有测试改为 async（使用 `pytest-asyncio`）
  - mock `select_adapter` 返回假 Adapter 类
  - 更新断言以反映真实 Adapter 调用链路
- **NEW** `tests/integration/test_b_c_retrieval.py`：
  - 覆盖成功、主源失败 fallback 成功、全部失败、无搜索结果四个场景

## Impact

- **Affected specs**：
  - 5.1 流程编排层（`retrieve_data` 节点从骨架变为真实实现）
  - 5.3 Hermes 经验库（`retrieve_data` 真正消费 Hermes 的经验注入与记录）
- **Affected code**：
  - `src/rdi/graph/nodes/retrieve_data.py` — 核心修改
  - `tests/unit/graph/test_retrieve_data.py` — 适配 async + 真实 mock
  - `tests/integration/test_b_c_retrieval.py` — 新建集成测试

## ADDED Requirements

### Requirement: retrieve_data 节点接入真实 Adapter

系统 SHALL 在 `node_retrieve_single` 中通过 `select_adapter()` 获取候选 Adapter，按 Hermes 优先级排序后逐个尝试，成功即返回，全部失败则返回错误结果。

- `node_retrieve_single` 必须是 `async def`，因为 Adapter 的 `search` / `fetch` 均为 async
- 通过 `hermes.get_source_priority(req_type)` 获取排序后的候选源名称列表
- 通过 `select_adapter(DataReqType(req_type))` 获取候选 Adapter 类列表
- 按优先级逐个实例化并调用 `await adapter.search(query)`
- search 有结果时取第一个，调用 `await adapter.fetch(item_id)`
- fetch 成功则返回 `RetrievalResult(status="success", data=raw, ...)`
- 某个 Adapter 抛 `AdapterError` 或返回空结果时，记录失败后继续下一个候选源
- 全部 Adapter 都失败时返回 `RetrievalResult(status="error", error_message=...)`
- 全部 Adapter search 都无结果时返回 `RetrievalResult(status="missing")`
- `is_fallback=True` 标记使用了非首个候选源的成功结果

#### Scenario: 主源成功

- **WHEN** req_type="code"，第一个候选 GitHubAdapter search 返回结果且 fetch 成功
- **THEN** 返回 `RetrievalResult(status="success")`，`is_fallback=False`

#### Scenario: 主源失败 fallback 成功

- **WHEN** GitHubAdapter 抛 `AdapterError`，PapersWithCodeAdapter fetch 成功
- **THEN** 返回 `RetrievalResult(status="success", is_fallback=True)`

#### Scenario: 全部失败

- **WHEN** 所有候选 Adapter 均抛 `AdapterError`
- **THEN** 返回 `RetrievalResult(status="error", error_message="...")`

#### Scenario: 无搜索结果

- **WHEN** 所有候选 Adapter search 均返回空列表
- **THEN** 返回 `RetrievalResult(status="missing")`

### Requirement: Hermes 经验注入真正使用

系统 SHALL 在 `node_retrieve_single` 中将 `hermes.inject_experience()` 的返回值拼入 provenance 溯源日志，而非丢弃。

- 经验提示字符串非空时，追加到返回的 `provenance` 列表
- 经验提示为空字符串时不追加（避免空条目）

#### Scenario: 有历史经验

- **WHEN** `inject_experience` 返回 "[历史经验参考]..."
- **THEN** provenance 列表包含该字符串

#### Scenario: 无历史经验

- **WHEN** `inject_experience` 返回 ""
- **THEN** provenance 列表不包含经验条目

### Requirement: Hermes 经验记录真实结果

系统 SHALL 在 `node_retrieve_single` 完成查找后，调用 `hermes.record_experience()` 传入真实的 status、sources_used、elapsed_seconds。

- `status` 取自实际 `RetrievalResult.status`
- `sources_used` 取自实际使用的 `RawData.source.value`（失败时为最后尝试的源）
- `elapsed_seconds` 取自实际查找耗时

#### Scenario: 成功记录

- **WHEN** 查找成功，source=github
- **THEN** `record_experience` 被调用，`result_status="success"`，`sources_used=["github"]`

#### Scenario: 失败记录

- **WHEN** 所有 Adapter 均失败
- **THEN** `record_experience` 被调用，`result_status="error"`

## MODIFIED Requirements

### Requirement: node_retrieve_single 异步签名

`node_retrieve_single` 从同步函数改为 `async def`，以适配 Adapter 的 async 接口。LangGraph 支持 async 节点，无需额外包装。

- 签名：`async def node_retrieve_single(payload: dict[str, Any]) -> dict[str, Any]`
- 返回值结构不变：`{"retrieval_results": {req_id: RetrievalResult}, "provenance": [...]}`

## REMOVED Requirements

### Requirement: 占位 placeholder data

**Reason**: 已被真实 Adapter 调用替换
**Migration**: 删除 `placeholder_result` 及 `RawData(source=DataSource.GITHUB, item_id=f"placeholder_{req_id}", ...)` 相关代码
