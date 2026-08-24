# LLM 客户端与目标解析节点 Spec

## Why

5.1 流程编排骨架已完成，`parse_goal` 节点目前是占位实现。B 工程师需要补齐真实的 LLM 调用与目标解析能力，让 `parse_goal` 能把用户自然语言描述转换为结构化的 `GoalSpec` + `list[DataReq]`，供后续 `retrieve_data` / `assemble_package` 等节点消费。

与此同时，当前配置与依赖均绑定阿里云 `dashscope`（`qwen_api_key` / `qwen_model` 等），无法切换其他主流 LLM 厂商。考虑到 Qwen、DeepSeek、GLM、OpenAI 等均提供 OpenAI 兼容接口，本次同时把 LLM 接入层改为 OpenAI 兼容格式，避免厂商锁定。

## What Changes

- **BREAKING**: 将 `qwen_*` 配置项重命名为 `llm_*`，新增 `llm_base_url` 配置项
  - `qwen_api_key` → `llm_api_key`
  - `qwen_model` → `llm_model`
  - `qwen_embedding_model` → `llm_embedding_model`
  - `qwen_max_retries` → `llm_max_retries`
  - `qwen_temperature` → `llm_temperature`
  - 新增 `llm_base_url`（默认指向阿里云百炼兼容端点 `https://dashscope.aliyuncs.com/compatible-mode/v1`，切换厂商时改这一项即可）
- **BREAKING**: `pyproject.toml` 依赖 `dashscope` 替换为 `openai`
- 新增 `src/rdi/intelligence/client.py`：基于 `openai.OpenAI` 封装的 `LLMClient`，提供 `call(prompt)` 和 `call_structured(prompt, schema)` 两个方法
- 新增 `src/rdi/intelligence/prompts/goal_parsing.py`：目标解析 Prompt 模板（系统提示 + 用户提示模板）
- 修改 `src/rdi/intelligence/__init__.py`：导出 `LLMClient`
- 修改 `src/rdi/intelligence/prompts/__init__.py`：导出目标解析 Prompt 常量
- 修改 `src/rdi/graph/nodes/parse_goal.py`：用 `LLMClient` + `call_structured` 替换占位逻辑，输出真实的 `GoalSpec` 和 `list[DataReq]`
- 新增 `tests/unit/test_llm_client.py`：使用 `respx` mock OpenAI 接口的单元测试
- 新增 `tests/unit/test_parse_goal.py`：mock `LLMClient` 验证节点输出
- 新增 `tests/unit/test_goal_parsing_prompt.py`：验证 Prompt 模板渲染正确
- 更新 `.env.example`（若存在）：反映新配置项
- 更新 `README.md`：LLM 接入说明（切换厂商只需改 `llm_base_url`）

## Impact

- **Affected specs**：
  - 5.1 流程编排层（`parse_goal` 节点从骨架变为真实实现）
  - 5.2 Qwen LLM 接入（B 工程师主任务，本 spec 即此模块）
  - 5.3 Hermes 经验库（W5-W6 会依赖本 spec 的 embedding 接口；本次仅预留 `llm_embedding_model` 配置，不实现 embedding 调用）
- **Affected code**：
  - `src/rdi/config/settings.py` — 配置项重命名
  - `src/rdi/intelligence/client.py` — 新建
  - `src/rdi/intelligence/prompts/goal_parsing.py` — 新建
  - `src/rdi/intelligence/__init__.py` — 导出
  - `src/rdi/intelligence/prompts/__init__.py` — 导出
  - `src/rdi/graph/nodes/parse_goal.py` — 接入真实 LLM
  - `pyproject.toml` — 依赖替换
  - `tests/unit/` — 新增三个测试文件

## 边界说明

本 spec **不实现** PDF 论文解析 Skill（属于 D 工程师 5.5 能力执行层范畴）。`parse_goal` 节点对 PDF 的处理策略：

- 若 `state["paper_pdf"]` 存在：本次先用 `PyMuPDF`（已在依赖中）做最简文本抽取，抽取后拼入 LLM Prompt；不实现完整的 `PDFParseSkill`
- 标注 `ponytail:` 注释说明这是临时实现，等 D 的 `PDFParseSkill` 就绪后替换
- 若 PDF 为空：仅基于 `user_goal` 自然语言进行解析

## ADDED Requirements

### Requirement: OpenAI 兼容 LLM 客户端

系统 SHALL 提供 `LLMClient` 类，封装 OpenAI 兼容接口，支持通过 `llm_base_url` 切换任意兼容厂商。

#### Scenario: 普通文本调用成功
- **WHEN** 调用 `LLMClient.call(prompt="你好")` 且配置正确
- **THEN** 返回 LLM 生成的字符串文本

#### Scenario: 结构化输出调用成功
- **WHEN** 调用 `LLMClient.call_structured(prompt, schema=GoalSpec)` 且 LLM 返回合法 JSON
- **THEN** 返回 `GoalSpec` 实例，字段完整且类型校验通过

#### Scenario: 结构化输出 JSON 非法
- **WHEN** LLM 返回的内容无法解析为符合 schema 的 JSON
- **THEN** 抛出 `LLMParseError`，错误信息包含原始返回内容片段

#### Scenario: API 调用失败重试耗尽
- **WHEN** 调用 OpenAI 接口连续失败次数达到 `llm_max_retries`
- **THEN** 抛出 `LLMUnavailableError`，附带模型名和重试次数

#### Scenario: 切换 LLM 厂商
- **WHEN** 用户在 `.env` 中修改 `LLM_BASE_URL` 指向其他厂商（如 DeepSeek）
- **THEN** `LLMClient` 自动使用新的 endpoint，无需修改代码

### Requirement: 目标解析 Prompt 模板

系统 SHALL 提供目标解析 Prompt 模板，引导 LLM 输出符合 `GoalSpec` + `list[DataReq]` 结构的 JSON。

#### Scenario: 仅自然语言输入
- **WHEN** 仅有 `user_goal`，无 PDF 文本
- **THEN** Prompt 中不包含论文上下文段落，仍要求 LLM 输出完整结构化结果

#### Scenario: 自然语言 + PDF 文本
- **WHEN** 同时传入 `user_goal` 和 PDF 抽取文本
- **THEN** Prompt 中包含"论文信息"段落，引导 LLM 利用论文内容丰富 `PaperInfo` 和数据需求

### Requirement: parse_goal 节点真实实现

`node_parse_goal` SHALL 调用 `LLMClient.call_structured` 替换占位逻辑，输出真实结构化结果。

#### Scenario: 节点成功输出
- **WHEN** `state["user_goal"]` 非空，LLM 调用成功
- **THEN** 返回 `parsed_goal: GoalSpec` 和 `data_requirements: list[DataReq]`，且 `data_requirements` 中每项 `req_id` 形如 `req_000`、`req_001`...

#### Scenario: LLM 调用失败降级
- **WHEN** `LLMClient` 抛出 `LLMUnavailableError` 或 `LLMParseError`
- **THEN** 节点不向上抛异常，而是返回 `parsed_goal` 占位 + `errors` 字段记录错误信息，让流程继续（符合开发规范"LangGraph 节点通过 State 的 errors 字段传递错误"）

#### Scenario: provenance 追溯
- **WHEN** 节点执行完成（无论成功或降级）
- **THEN** 在 `provenance` 字段追加一条带时间戳的日志，标注使用的是真实 LLM 还是降级路径

## MODIFIED Requirements

### Requirement: 全局配置 LLM 部分

原 `qwen_*` 配置项重命名为 `llm_*` 并新增 `llm_base_url`：

```python
llm_api_key: str = Field(default="", description="LLM 服务 API Key（OpenAI 兼容）")
llm_base_url: str = Field(
    default="https://dashscope.aliyuncs.com/compatible-mode/v1",
    description="LLM 服务 OpenAI 兼容端点，切换厂商改这一项",
)
llm_model: str = Field(default="qwen-plus", description="LLM 模型名称")
llm_embedding_model: str = Field(default="text-embedding-v3", description="Embedding 模型名称")
llm_max_retries: int = Field(default=3, description="LLM 调用最大重试次数")
llm_temperature: float = Field(default=0.3, description="LLM 生成温度，目标解析用低温度")
```

## REMOVED Requirements

### Requirement: dashscope 依赖
**Reason**: 改用 OpenAI 兼容接口后，不再需要 `dashscope` SDK
**Migration**: `pip install openai` 替代；用户只需配置 `LLM_BASE_URL` 和 `LLM_API_KEY` 即可接入原阿里云 Qwen 服务

### Requirement: qwen_* 配置项
**Reason**: 厂商锁定，改为 `llm_*` 通用命名
**Migration**: 用户迁移 `.env` 文件时，将 `QWEN_API_KEY` 改为 `LLM_API_KEY`，`QWEN_MODEL` 改为 `LLM_MODEL`，依此类推；新增 `LLM_BASE
