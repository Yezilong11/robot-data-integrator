# Tasks

- [x] Task 1: 依赖与配置层切换为 OpenAI 兼容
  - [x] SubTask 1.1: 修改 `pyproject.toml`，将 `dashscope>=1.0.0` 替换为 `openai>=1.50.0`
  - [x] SubTask 1.2: 修改 `src/rdi/config/settings.py`，将 `qwen_*` 字段重命名为 `llm_*`，新增 `llm_base_url` 字段（默认 `https://dashscope.aliyuncs.com/compatible-mode/v1`）
  - [x] SubTask 1.3: 修改 `tests/unit/test_settings.py`，更新字段名断言
  - [x] SubTask 1.4: `.env.example` 中 `QWEN_*` 已更新为 `LLM_*` 并补充 `LLM_BASE_URL`；README.md 原本无 `QWEN_*` 字样

- [x] Task 2: 实现 LLMClient（OpenAI 兼容封装）
  - [x] SubTask 2.1: 新建 `src/rdi/intelligence/client.py`，定义 `LLMClient` 类
    - 构造函数接收 `settings`（或显式参数），内部创建 `openai.OpenAI` 实例
    - 实现 `call(prompt: str, system: str | None = None) -> str`：纯文本返回
    - 实现 `call_structured(prompt: str, schema: type[BaseModel], system: str | None = None) -> BaseModel`：通过 `response_format={"type": "json_object"}` + Pydantic 校验实现
    - 重试逻辑使用 `tenacity` 或手写循环（ponytail：手写循环，避免新增依赖），重试次数取 `llm_max_retries`
    - 失败抛 `LLMUnavailableError`，JSON 解析失败抛 `LLMParseError`（均已在 `exceptions.py` 中定义）
  - [x] SubTask 2.2: 修改 `src/rdi/intelligence/__init__.py`，导出 `LLMClient`
  - [x] SubTask 2.3: 新建 `tests/unit/test_llm_client.py`
    - 用 `respx` mock `/chat/completions` 接口
    - 测试 `call` 成功路径
    - 测试 `call_structured` 成功路径（返回合法 JSON）
    - 测试 `call_structured` JSON 非法时抛 `LLMParseError`
    - 测试 API 连续失败重试耗尽抛 `LLMUnavailableError`

- [x] Task 3: 设计目标解析 Prompt 模板
  - [x] SubTask 3.1: 新建 `src/rdi/intelligence/prompts/goal_parsing.py`
    - 定义 `GOAL_PARSING_SYSTEM`：系统提示，说明 LLM 角色（机器人数据整合助手）、输出要求（严格 JSON）
    - 定义 `GOAL_PARSING_USER_TEMPLATE`：用户提示模板，包含 `{user_goal}` 和可选的 `{paper_text}` 占位符
    - 提供 `build_goal_parsing_prompt(user_goal, paper_text=None) -> tuple[str, str]` 函数返回 (system, user)
    - Prompt 中明确要求输出的 JSON schema 与 `GoalSpec` + `list[DataReq]` 对齐
  - [x] SubTask 3.2: 修改 `src/rdi/intelligence/prompts/__init__.py`，导出 Prompt 构建函数
  - [x] SubTask 3.3: 新建 `tests/unit/test_goal_parsing_prompt.py`
    - 测试无 paper_text 时模板渲染不含论文段落
    - 测试有 paper_text 时模板渲染包含论文段落
    - 测试占位符被完整替换

- [x] Task 4: 接入 parse_goal 节点真实实现
  - [x] SubTask 4.1: 修改 `src/rdi/graph/nodes/parse_goal.py`
    - 移除占位数据
    - 若 `state["paper_pdf"]` 存在，用 `PyMuPDF` (`fitz`) 做最简文本抽取
      - `ponytail:` 注释说明：这是临时实现，等 D 工程师的 `PDFParseSkill` 就绪后替换
    - 调用 `build_goal_parsing_prompt` 构建 (system, user)
    - 调用 `LLMClient.call_structured` 输出 `GoalSpec` 和 `list[DataReq]`
      - LLM 一次返回两个对象时可封装为一个临时 Pydantic 模型（如 `_GoalParsingResult`），或调用两次（ponytail：优先单次调用，减少 token 消耗）
    - 捕获 `LLMUnavailableError` / `LLMParseError`，降级返回占位 `GoalSpec` + 空 `data_requirements` + `errors` 字段
    - 追加 `provenance` 日志，标注真实 LLM 路径或降级路径
  - [x] SubTask 4.2: 新建 `tests/unit/test_parse_goal.py`
    - mock `LLMClient`，测试成功路径输出正确的 `GoalSpec` 和 `list[DataReq]`
    - mock `LLMClient` 抛 `LLMUnavailableError`，测试降级路径不抛异常、`errors` 字段非空
    - 测试 PDF 抽取路径（提供合法 PDF bytes 和空 PDF 两种情况）

- [x] Task 5: 文档更新与最终验证
  - [x] SubTask 5.1: 更新 `README.md` 中 LLM 配置部分，说明切换厂商只需改 `LLM_BASE_URL`
  - [x] SubTask 5.2: 运行 `ruff check src tests` 和 `ruff format src tests` 确保无 lint 错误
  - [x] SubTask 5.3: 运行 `mypy src` 确保无类型错误
  - [x] SubTask 5.4: 运行 `pytest tests/unit/` 确保所有单元测试通过
  - [x] SubTask 5.5: 运行 `python -c "from rdi.graph import build_graph; build_graph()"` 确保图能正常编译

# Task Dependencies

- Task 2 依赖 Task 1（需要 `llm_*` 配置才能创建客户端）
- Task 3 可与 Task 2 并行（纯字符串模板，不依赖客户端）
- Task 4 依赖 Task 2 和 Task 3（节点同时使用客户端和 Prompt 模板）
- Task 5 依赖 Task 1