# Tasks

- [x] Task 1: 改造 `node_retrieve_single` 为 async 并接入真实 Adapter
  - [x] SubTask 1.1: 将 `node_retrieve_single` 改为 `async def`
  - [x] SubTask 1.2: 通过 `select_adapter(DataReqType(req_type))` 获取候选 Adapter 类列表
  - [x] SubTask 1.3: 按 `hermes.get_source_priority(req_type)` 排序候选源
  - [x] SubTask 1.4: 逐个尝试 `await adapter.search(query)` → `await adapter.fetch(item_id)`
  - [x] SubTask 1.5: 成功时返回 `RetrievalResult(status="success")`，标记 `is_fallback`
  - [x] SubTask 1.6: 全部失败时返回 `status="error"`，无结果时返回 `status="missing"`
  - [x] SubTask 1.7: 删除 `placeholder_result` 占位代码和两处 `ponytail:` 注释
- [x] Task 2: 真正使用 Hermes 经验注入与记录
  - [x] SubTask 2.1: 将 `inject_experience` 返回值拼入 provenance（非空时追加）
  - [x] SubTask 2.2: `record_experience` 传入真实的 status、sources_used、elapsed_seconds
- [x] Task 3: 更新现有单元测试 `tests/unit/graph/test_retrieve_data.py`
  - [x] SubTask 3.1: 测试函数改为 async（`async def test_...`）
  - [x] SubTask 3.2: mock `select_adapter` 返回假 Adapter 类，mock `adapter.search` / `adapter.fetch`
  - [x] SubTask 3.3: 更新断言以反映真实 Adapter 调用链路（不再断言 placeholder）
  - [x] SubTask 3.4: 确保现有 2 个测试用例通过
- [x] Task 4: 新增集成测试 `tests/integration/test_b_c_retrieval.py`
  - [x] SubTask 4.1: 创建 `tests/integration/` 目录和 `__init__.py`
  - [x] SubTask 4.2: 测试场景：主源成功
  - [x] SubTask 4.3: 测试场景：主源失败 fallback 成功（`is_fallback=True`）
  - [x] SubTask 4.4: 测试场景：全部失败（`status="error"`）
  - [x] SubTask 4.5: 测试场景：无搜索结果（`status="missing"`）

# Task Dependencies

- [Task 2] depends on [Task 1]
- [Task 3] depends on [Task 1]
- [Task 4] depends on [Task 1]
- [Task 3] 和 [Task 4] 可并行
