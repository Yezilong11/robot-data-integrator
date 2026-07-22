# Embedding 封装与 Hermes 持续学习引擎 Spec

## Why

5.2 LLM 接入中唯一未完成的 Embedding 服务是 5.3 Hermes 经验库向量检索的前置依赖。
当前并行组 B（5.4/5.5/5.7）正在开发中，5.3 Hermes 层与它们无耦合，可先行启动。
Hermes 经验库原计划分配给 F（质量工程师），但其核心逻辑（experience_db / strategy / engine）
属于智能决策层业务代码，应由 B（AI 工程师）统一实现，F 负责对应测试。

## What Changes

- 新增 `src/rdi/intelligence/embedding.py`：基于 OpenAI 兼容 SDK 的 Embedding 服务封装
- 新增 `src/rdi/adapters/registry.py`：数据源注册表骨架（DataReqType → DataSource 映射），供 Hermes 策略演化查询候选源，C 工程师后续扩展
- 新增 `src/rdi/hermes/experience_db.py`：ChromaDB 三 Collection（experience / feedback / source_stats）的 CRUD 封装
- 新增 `src/rdi/hermes/strategy.py`：StrategyEvolver，根据历史成功率动态调整数据源优先级
- 新增 `src/rdi/hermes/engine.py`：HermesEngine，对外统一接口（经验注入 / 经验记录 / 策略演化 / 用户反馈）
- 修改 `src/rdi/hermes/__init__.py`：导出 HermesEngine
- 修改 `src/rdi/intelligence/__init__.py`：导出 embedding 服务
- 修改 `src/rdi/graph/nodes/retrieve_data.py`：接入 Hermes 经验注入与记录（骨架级，等 C 的 Adapter 就绪后完整联调）
- 新增对应单元测试

## Impact

- Affected specs: 5.2（补全 Embedding）、5.3（Hermes 全量实现）
- Affected code:
  - `src/rdi/intelligence/embedding.py`（新建）
  - `src/rdi/intelligence/__init__.py`（修改）
  - `src/rdi/adapters/registry.py`（新建）
  - `src/rdi/hermes/experience_db.py`（新建）
  - `src/rdi/hermes/strategy.py`（新建）
  - `src/rdi/hermes/engine.py`（新建）
  - `src/rdi/hermes/__init__.py`（修改）
  - `src/rdi/graph/nodes/retrieve_data.py`（修改）
  - `tests/unit/intelligence/test_embedding.py`（新建）
  - `tests/unit/hermes/test_experience_db.py`（新建）
  - `tests/unit/hermes/test_strategy.py`（新建）
  - `tests/unit/hermes/test_engine.py`（新建）

## ADDED Requirements

### Requirement: Embedding 服务

系统 SHALL 提供基于 OpenAI 兼容 SDK 的 Embedding 服务封装，将文本转为向量供 Hermes 经验检索使用。

- 使用 `openai.OpenAI` 客户端的 `embeddings.create()` 方法，与 `LLMClient` 共享同一 `llm_base_url` / `llm_api_key`
- 模型名取 `settings.llm_embedding_model`（默认 `text-embedding-v3`）
- 提供 `get_embedding(text: str) -> list[float]` 函数接口
- 提供 `EmbeddingClient` 类，支持构造函数注入参数（便于测试），内部缓存 OpenAI 客户端实例
- API 调用失败时抛 `LLMUnavailableError`，复用现有异常体系
- 不做重试（Embedding 调用量低，失败由上层处理）

#### Scenario: 正常获取 Embedding

- **WHEN** 调用 `get_embedding("机器人抓取")`
- **THEN** 返回 `list[float]`，维度与模型一致（text-embedding-v3 为 1024 维）

#### Scenario: API 调用失败

- **WHEN** OpenAI SDK 抛出 `OpenAIError`
- **THEN** 包装为 `LLMUnavailableError` 抛出，包含模型名信息

### Requirement: 数据源注册表骨架

系统 SHALL 提供数据源注册表 `ADAPTER_REGISTRY`，映射 `DataReqType` 到候选 `DataSource` 列表，供 Hermes 策略演化查询。

- 定义为模块级常量 `dict[str, list[DataSource]]`（key 用 DataReqType 的字符串值）
- 覆盖所有 9 种 DataReqType 的默认候选源
- C 工程师后续在此注册真实 Adapter 时扩展，当前提供静态映射即可

#### Scenario: 策略演化查询候选源

- **WHEN** `StrategyEvolver.get_source_priority("robot_urdf")` 被调用
- **THEN** 从 `ADAPTER_REGISTRY["robot_urdf"]` 获取候选列表，按历史成功率排序后返回

### Requirement: ExperienceDB 经验库

系统 SHALL 提供基于 ChromaDB 的经验持久化服务，包含三个 Collection：

1. **experience**：存储任务描述 + 向量 + 元数据（req_type, result_status, sources_used, elapsed_seconds, created_at）
2. **feedback**：存储用户反馈（task_desc, feedback_type, feedback_content, corrected_value, created_at）
3. **source_stats**：存储数据源统计（source_name, total_requests, success_count, avg_elapsed, last_updated）

- 使用 `chromadb.PersistentClient`，路径取 `settings.chromadb_path`
- Experience collection 在首次写入时用 `get_embedding()` 生成向量，维度由模型决定
- 提供 `store_experience()` / `retrieve_similar_experiences()` / `store_feedback()` / `get_source_stats()` / `update_source_stats()` 方法
- `retrieve_similar_experiences()` 使用 ChromaDB 向量检索，返回 top_k 条最相似经验
- 构造函数接受可选的 embedding 函数和 chromadb 路径，便于测试注入

#### Scenario: 存储并检索经验

- **WHEN** 调用 `store_experience(task_desc="查找URDF", ...)` 后再调用 `retrieve_similar_experiences("查找URDF", top_k=3)`
- **THEN** 返回包含刚存储经验的列表

#### Scenario: 更新数据源统计

- **WHEN** 调用 `update_source_stats("github", success=True, elapsed_seconds=1.5)`
- **THEN** `get_source_stats()` 中 github 的 `total_requests` +1，`success_count` 按结果 +1 或不变

### Requirement: StrategyEvolver 策略演化

系统 SHALL 提供策略演化器，根据历史统计数据动态调整数据源优先级。

- 定期检查（默认 6 小时间隔）各数据源成功率
- 成功率低于 50% 的源降低优先级（标记 deprioritize）
- 成功率高于 90% 且请求总数 > 10 的源提升优先级（标记 promote）
- `get_source_priority(req_type)` 返回按成功率降序排列的数据源列表
- 演化日志写入 `data/hermes_evolution.log`
- 构造函数接受 `ExperienceDB` 实例（依赖注入）

#### Scenario: 低成功率降级

- **WHEN** github 的成功率为 40%（< 50%）
- **THEN** `evolve()` 在日志中记录 `action=deprioritize`，`get_source_priority` 中 github 排序靠后

#### Scenario: 高成功率提升

- **WHEN** arxiv 的成功率为 95% 且总请求数 > 10
- **THEN** `evolve()` 在日志中记录 `action=promote`

### Requirement: HermesEngine 引擎

系统 SHALL 提供 HermesEngine 作为 Hermes 持续学习引擎的对外统一接口。

- 组合 `ExperienceDB` + `StrategyEvolver`
- `inject_experience(task_description, req_type) -> str`：检索相似经验，格式化为 Prompt 注入片段，无经验返回空串
- `record_experience(task_desc, req_type, result_status, sources_used, elapsed_seconds)`：记录经验 + 更新统计 + 触发策略演化
- `record_feedback(task_desc, feedback_type, feedback_content, corrected_value)`：记录用户反馈
- `get_source_priority(req_type) -> list[str]`：委托给 StrategyEvolver

#### Scenario: 经验注入

- **WHEN** 经验库中有相似经验时调用 `inject_experience("查找Franka URDF", "robot_urdf")`
- **THEN** 返回格式化的 `[历史经验参考]` 字符串，包含状态、来源、耗时

#### Scenario: 无经验时注入

- **WHEN** 经验库为空时调用 `inject_experience(...)`
- **THEN** 返回空字符串 `""`

### Requirement: retrieve_data 节点接入 Hermes

系统 SHALL 在 `retrieve_data` 节点的 `node_retrieve_single` 中接入 Hermes 经验注入与记录。

- 查找前：调用 `HermesEngine.inject_experience()` 获取经验提示
- 查找后：调用 `HermesEngine.record_experience()` 记录结果
- 当前 retrieve_single 仍为骨架实现，Hermes 接入为骨架级（记录占位结果的经验）
- Hermes 引擎通过模块级懒加载单例获取，便于测试 monkeypatch

#### Scenario: 骨架节点记录经验

- **WHEN** `node_retrieve_single` 执行完毕
- **THEN** Hermes 经验库中新增一条经验记录，包含 req_id、状态、耗时
