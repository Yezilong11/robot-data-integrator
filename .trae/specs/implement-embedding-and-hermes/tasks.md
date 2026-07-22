# Tasks

- [x] Task 1: 实现 Embedding 服务（OpenAI 兼容）
  - [ ] SubTask 1.1: 新建 `src/rdi/intelligence/embedding.py`
    - 定义 `EmbeddingClient` 类，构造函数接收可选 `api_key` / `base_url` / `model`，默认从 `settings` 读取
    - 内部创建 `openai.OpenAI` 实例（`max_retries=0`，与 LLMClient 一致）
    - 实现 `embed(text: str) -> list[float]`：调用 `client.embeddings.create()`，返回 `data[0].embedding`
    - API 失败时捕获 `OpenAIError`，包装为 `LLMUnavailableError`（含 model 名）
    - 模块级提供 `get_embedding(text) -> list[float]` 便捷函数，内部用懒加载单例 `EmbeddingClient`
  - [ ] SubTask 1.2: 修改 `src/rdi/intelligence/__init__.py`，导出 `EmbeddingClient` 和 `get_embedding`
  - [ ] SubTask 1.3: 新建 `tests/unit/intelligence/test_embedding.py`
    - 用 `respx` mock `/embeddings` 端点
    - 测试 `embed` 成功路径返回向量
    - 测试 API 失败抛 `LLMUnavailableError`
    - 测试 `get_embedding` 便捷函数

- [x] Task 2: 创建数据源注册表骨架
  - [ ] SubTask 2.1: 新建 `src/rdi/adapters/registry.py`
    - 定义 `ADAPTER_REGISTRY: dict[str, list[DataSource]]`，覆盖全部 9 种 DataReqType
    - 每种类型映射到合理的候选数据源列表（参考项目文档中的 Adapter 清单）
    - `ponytail:` 注释说明：C 工程师后续在此注册真实 Adapter 类
  - [ ] SubTask 2.2: 修改 `src/rdi/adapters/__init__.py`，导出 `ADAPTER_REGISTRY`

- [x] Task 3: 实现 ExperienceDB 经验库
  - [ ] SubTask 3.1: 新建 `src/rdi/hermes/experience_db.py`
    - 定义 `ExperienceDB` 类
    - 构造函数接收可选 `db_path: str` 和 `embed_fn: Callable[[str], list[float]]`，默认分别取 `settings.chromadb_path` 和 `get_embedding`
    - 初始化三个 ChromaDB Collection：`experience` / `feedback` / `source_stats`（用 `get_or_create_collection`）
    - `store_experience(task_desc, req_type, result_status, sources_used, elapsed_seconds, user_feedback="")`：生成向量 + 写入 experience collection
    - `retrieve_similar_experiences(task_desc, top_k=5) -> list[dict]`：用向量检索 experience collection，返回 metadata 列表
    - `store_feedback(task_desc, feedback_type, feedback_content, corrected_value="")`：写入 feedback collection
    - `get_source_stats() -> list[dict]`：读取 source_stats collection 全部记录
    - `update_source_stats(source, success, elapsed_seconds)`：upsert source_stats（total_requests++, success_count 按结果++, avg_elapsed 滑动平均）
  - [ ] SubTask 3.2: 新建 `tests/unit/hermes/__init__.py`
  - [ ] SubTask 3.3: 新建 `tests/unit/hermes/test_experience_db.py`
    - 使用临时目录作为 ChromaDB 路径（`tmp_path` fixture）
    - mock `embed_fn` 返回固定向量，避免调用真实 API
    - 测试 `store_experience` + `retrieve_similar_experiences` 往返
    - 测试 `update_source_stats` 累加正确
    - 测试 `store_feedback` 写入正确

- [x] Task 4: 实现 StrategyEvolver 策略演化
  - [ ] SubTask 4.1: 新建 `src/rdi/hermes/strategy.py`
    - 定义 `StrategyEvolver` 类
    - 构造函数接收 `ExperienceDB` 实例
    - `maybe_evolve()`：条件触发，距上次演化超过 `evolve_interval_hours`（默认 6）才执行
    - `evolve()`：遍历 `db.get_source_stats()`，成功率 < 0.5 记录 deprioritize，> 0.9 且 total > 10 记录 promote
    - `get_source_priority(req_type) -> list[str]`：从 `ADAPTER_REGISTRY` 取候选，按成功率降序排序
    - `_log_evolution(source, action, reason)`：追加写入 `data/hermes_evolution.log`
  - [ ] SubTask 4.2: 新建 `tests/unit/hermes/test_strategy.py`
    - mock `ExperienceDB` 返回预设统计数据
    - 测试 `evolve()` 对低成功率源记录 deprioritize
    - 测试 `evolve()` 对高成功率源记录 promote
    - 测试 `get_source_priority()` 排序正确
    - 测试 `maybe_evolve()` 时间间隔控制

- [x] Task 5: 实现 HermesEngine 引擎
  - [ ] SubTask 5.1: 新建 `src/rdi/hermes/engine.py`
    - 定义 `HermesEngine` 类
    - 构造函数初始化 `ExperienceDB` + `StrategyEvolver`
    - `inject_experience(task_description, req_type) -> str`：检索相似经验，格式化为 `[历史经验参考]` 片段，无经验返回 `""`
    - `record_experience(task_desc, req_type, result_status, sources_used, elapsed_seconds)`：存储经验 + 更新统计 + 触发 `maybe_evolve`
    - `record_feedback(task_desc, feedback_type, feedback_content, corrected_value="")`：委托 ExperienceDB
    - `get_source_priority(req_type) -> list[str]`：委托 StrategyEvolver
  - [ ] SubTask 5.2: 修改 `src/rdi/hermes/__init__.py`，导出 `HermesEngine`
  - [ ] SubTask 5.3: 新建 `tests/unit/hermes/test_engine.py`
    - mock `ExperienceDB` 和 `StrategyEvolver`
    - 测试 `inject_experience` 有经验时返回格式化字符串
    - 测试 `inject_experience` 无经验时返回空串
    - 测试 `record_experience` 调用 store + update_stats + maybe_evolve
    - 测试 `record_feedback` 委托正确

- [x] Task 6: retrieve_data 节点接入 Hermes
  - [ ] SubTask 6.1: 修改 `src/rdi/graph/nodes/retrieve_data.py`
    - 在 `node_retrieve_single` 中，查找前调用 `HermesEngine.inject_experience()`（结果暂存，等 C 的 Adapter 接入后拼接到 LLM 上下文）
    - 查找后调用 `HermesEngine.record_experience()`，记录 req_id、status、source、elapsed_seconds
    - 模块级懒加载 `_hermes_engine` 单例，提供 `_get_hermes_engine()` 函数便于测试 monkeypatch
    - 保留 `ponytail:` 注释：等 C 的 Adapter 就绪后完整联调
  - [ ] SubTask 6.2: 修改 `tests/unit/test_parse_goal.py` 或新建 `tests/unit/graph/test_retrieve_data.py`
    - mock `HermesEngine`，验证 `inject_experience` 和 `record_experience` 被调用
    - 测试骨架节点仍返回占位 RetrievalResult

- [x] Task 7: 质量门禁验证
  - [ ] SubTask 7.1: 运行 `ruff check src tests` 和 `ruff format src tests` 确保无 lint 错误
  - [ ] SubTask 7.2: 运行 `mypy src` 确保无类型错误
  - [ ] SubTask 7.3: 运行 `pytest tests/unit/ -v` 确保所有单元测试通过
  - [ ] SubTask 7.4: 运行 `python -c "from rdi.graph import build_graph; build_graph()"` 确保图能正常编译

# Task Dependencies

- Task 1（Embedding）无依赖，最先完成
- Task 2（Registry）无依赖，可与 Task 1 并行
- Task 3（ExperienceDB）依赖 Task 1（需要 embedding 函数）
- Task 4（StrategyEvolver）依赖 Task 2（需要 ADAPTER_REGISTRY）和 Task 3（需要 ExperienceDB 接口）
- Task 5（HermesEngine）依赖 Task 3 和 Task 4
- Task 6（retrieve_data 接入）依赖 Task 5
- Task 7（质量门禁）依赖全部完成
