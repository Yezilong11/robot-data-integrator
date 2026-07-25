# Checklist

## 配置与依赖
- [x] `pyproject.toml` 中 `dashscope` 已替换为 `openai>=1.50.0`
- [x] `settings.py` 中 `qwen_*` 字段全部重命名为 `llm_*`
- [x] `settings.py` 新增 `llm_base_url` 字段，默认值 `https://dashscope.aliyuncs.com/compatible-mode/v1`
- [x] `tests/unit/test_settings.py` 中字段名断言已更新
- [x] `.env.example` 或 `README.md` 中的 `QWEN_*` 环境变量已改为 `LLM_*`

## LLMClient 实现
- [x] `src/rdi/intelligence/client.py` 已创建
- [x] `LLMClient` 类包含 `call(prompt, system=None) -> str` 方法
- [x] `LLMClient` 类包含 `call_structured(prompt, schema, system=None) -> BaseModel` 方法
- [x] 客户端通过 `settings.llm_base_url` 初始化 `openai.OpenAI` 实例
- [x] API 失败时按 `llm_max_retries` 重试，耗尽后抛 `LLMUnavailableError`
- [x] JSON 解析失败时抛 `LLMParseError`，错误信息含原始返回片段
- [x] `src/rdi/intelligence/__init__.py` 导出 `LLMClient`

## Prompt 模板
- [x] `src/rdi/intelligence/prompts/goal_parsing.py` 已创建
- [x] 定义了 `GOAL_PARSING_SYSTEM` 系统提示
- [x] 定义了 `GOAL_PARSING_USER_TEMPLATE` 用户提示模板
- [x] 提供 `build_goal_parsing_prompt(user_goal, paper_text=None) -> tuple[str, str]` 函数
- [x] Prompt 中明确要求输出与 `GoalSpec` + `list[DataReq]` 对齐的 JSON schema
- [x] `src/rdi/intelligence/prompts/__init__.py` 导出 Prompt 构建函数

## parse_goal 节点
- [x] `parse_goal.py` 中的占位数据已移除
- [x] 节点调用 `LLMClient.call_structured` 获取真实 `GoalSpec` 和 `list[DataReq]`
- [x] PDF 处理用 `PyMuPDF` 最简文本抽取，并带 `ponytail:` 注释说明等 D 的 Skill 替换
- [x] 捕获 `LLMUnavailableError` / `LLMParseError` 时降级返回，不抛异常
- [x] 降级时 `errors` 字段记录错误信息
- [x] `provenance` 字段追加日志，标注真实 LLM 路径或降级路径

## 测试覆盖
- [x] `tests/unit/test_llm_client.py` 已创建
- [x] 测试覆盖 `call` 成功路径
- [x] 测试覆盖 `call_structured` 成功路径
- [x] 测试覆盖 JSON 非法时抛 `LLMParseError`
- [x] 测试覆盖重试耗尽抛 `LLMUnavailableError`
- [x] `tests/unit/test_goal_parsing_prompt.py` 已创建
- [x] 测试覆盖无 paper_text 时模板渲染
- [x] 测试覆盖有 paper_text 时模板渲染
- [x] `tests/unit/test_parse_goal.py` 已创建
- [x] 测试覆盖成功路径输出正确结构
- [x] 测试覆盖 LLM 失败降级路径
- [x] 测试覆盖 PDF 抽取路径

## 质量门禁
- [x] `ruff check src tests` 通过
- [x] `ruff format --check src tests` 通过
- [x] `mypy src` 无错误
- [x] `pytest tests/unit/` 全部通过
- [x] `python -c "from rdi.graph import build_graph; build_graph()"` 图能正常编译

## 文档
- [x] `README.md` 中说明切换 LLM 厂商只需改 `LLM_BASE_URL`
- [x] spec.md 中标注的 BREAKING CHANGE 在