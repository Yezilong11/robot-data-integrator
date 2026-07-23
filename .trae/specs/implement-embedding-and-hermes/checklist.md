# Checklist

## Embedding 服务
- [x] `src/rdi/intelligence/embedding.py` 已创建
- [x] `EmbeddingClient` 类使用 `openai.OpenAI` 客户端调用 `embeddings.create()`
- [x] `EmbeddingClient` 构造函数支持显式传参覆盖 settings（便于测试）
- [x] `embed(text)` 返回 `list[float]`
- [x] API 失败时捕获 `OpenAIError` 包装为 `LLMUnavailableError`
- [x] 模块级 `get_embedding(text)` 便捷函数使用懒加载单例
- [x] `src/rdi/intelligence/__init__.py` 导出 `EmbeddingClient` 和 `get_embedding`
- [x] `tests/unit/intelligence/test_embedding.py` 覆盖成功路径和失败路径

## 数据源注册表
- [x] `src/rdi/adapters/registry.py` 已创建
- [x] `ADAPTER_REGISTRY` 覆盖全部 9 种 DataReqType
- [x] 每种类型映射到合理的候选 DataSource 列表
- [x] `src/rdi/adapters/__init__.py` 导出 `ADAPTER_REGISTRY`

## ExperienceDB 经验库
- [x] `src/rdi/hermes/experience_db.py` 已创建
- [x] 构造函数支持注入 `db_path` 和 `embed_fn`（便于测试）
- [x] 三个 Collection（experience / feedback / source_stats）正确初始化
- [x] `store_experience` 生成向量并写入 experience collection
- [x] `retrieve_similar_experiences` 使用向量检索返回 top_k 结果
- [x] `store_feedback` 写入 feedback collection
- [x] `get_source_stats` 返回全部数据源统计
- [x] `update_source_stats` 正确累加 total_requests / success_count / avg_elapsed
- [x] `tests/unit/hermes/test_experience_db.py` 使用临时目录 + mock embed_fn

## StrategyEvolver 策略演化
- [x] `src/rdi/hermes/strategy.py` 已创建
- [x] 构造函数接收 `ExperienceDB` 实例（依赖注入）
- [x] `maybe_evolve` 按 6 小时间隔条件触发
- [x] `evolve` 对成功率 < 50% 记录 deprioritize
- [x] `evolve` 对成功率 > 90% 且 total > 10 记录 promote
- [x] `get_source_priority` 从 ADAPTER_REGISTRY 取候选并按成功率降序排序
- [x] 演化日志写入 `data/hermes_evolution.log`
- [x] `tests/unit/hermes/test_strategy.py` 覆盖降级、提升、排序、间隔控制

## HermesEngine 引擎
- [x] `src/rdi/hermes/engine.py` 已创建
- [x] `inject_experience` 有经验时返回格式化 `[历史经验参考]` 字符串
- [x] `inject_experience` 无经验时返回空串
- [x] `record_experience` 调用 store + update_stats + maybe_evolve
- [x] `record_feedback` 委托 ExperienceDB
- [x] `get_source_priority` 委托 StrategyEvolver
- [x] `src/rdi/hermes/__init__.py` 导出 `HermesEngine`
- [x] `tests/unit/hermes/test_engine.py` 覆盖全部四个方法

## retrieve_data 节点接入
- [x] `node_retrieve_single` 查找前调用 `inject_experience`
- [x] `node_retrieve_single` 查找后调用 `record_experience`
- [x] 模块级懒加载 `_hermes_engine` 单例 + `_get_hermes_engine()` 函数
- [x] 保留 `ponytail:` 注释说明等 C 的 Adapter 联调
- [x] 测试验证 Hermes 方法被调用且骨架节点仍返回占位结果

## 质量门禁
- [x] `ruff check src tests` 通过
- [x] `ruff format --check src tests` 通过
- [x] `mypy src` 无错误
- [x] `pytest tests/unit/ -v` 全部通过
- [x] `python -c "from rdi.graph import build_graph; build_graph()"` 图能正常编译
