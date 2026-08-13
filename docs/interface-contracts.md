# RDI 模块接口契约文档

> 版本：v1.0
> 日期：2026-07-29
> 分支：`feat/integration-v1`
> 适用范围：第一次 B/C/D/E/F 集成联调

---

## 1. 文档目标

本文档定义第一次联调中 B（AI 工程师）与 C（数据工程师）、D（机器人工程师）、E（前端工程师）、F（质量工程师）之间的代码接口契约。

所有契约包含三部分：
- **数据契约**：输入/输出的 Pydantic 模型字段
- **调用契约**：函数签名、同步/异步、异常行为
- **状态契约**：LangGraph `SystemState` 中每个节点写入的字段

---

## 2. 全局约定

### 2.1 同步 / 异步约定

| 层级 | 约定 | 说明 |
|------|------|------|
| Adapter | 全部 `async` | `search()` / `fetch()` 为 async，涉及网络请求 |
| Skill | 全部 `sync` | `process()` / `validate()` 为 sync，只处理本地 bytes |
| Graph Node | 视情况 | `parse_goal` 为 sync；`retrieve_single` 为 async；`parse_convert` 为 sync |
| 前端 | 调用后端 sync 函数，内部用 `asyncio.run` 包装 async 调用 | |

### 2.2 错误处理约定

| 场景 | 行为 | 错误载体 |
|------|------|---------|
| Adapter 失败 | 不抛异常到节点外，节点内部继续 fallback | `AdapterError` 在节点内部捕获 |
| Skill 处理失败 | 返回 `StandardResult(success=False, errors=[...])`，不抛异常 | `StandardResult.errors` |
| 节点级失败 | 不抛异常中断整图，写入 `state["errors"]` 并返回降级字段 | `state["errors"]` |
| 未知格式 / 无 Skill | 装配 `MissingItem` 继续 | `missing_items` |

### 2.3 数据模型严格模式

所有 Pydantic 模型使用 `model_config = ConfigDict(extra="forbid")`。
新增字段必须先修改模型定义，否则会被拒绝。

---

## 3. B ↔ C：Adapter 接口契约

### 3.1 Adapter 基类

**文件**：`src/rdi/adapters/base.py`

```python
class BaseAdapter(ABC):
    source: DataSource  # 子类必须定义的类属性

    def __init__(self, base_url: str, rate_limit: int = 10) -> None: ...

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]: ...

    @abstractmethod
    async def fetch(self, item_id: str) -> RawData: ...
```

### 3.2 工厂与注册表

**文件**：`src/rdi/adapters/registry.py`

| 函数 | 签名 | 返回 | 用途 |
|------|------|------|------|
| `get_adapter` | `get_adapter(source: DataSource) -> BaseAdapter` | 实例 | 无参构造，供 D 的 Skill 等单源调用 |
| `select_adapter` | `select_adapter(req_type: DataReqType) -> list[type[BaseAdapter]]` | 类列表 | 按需求类型返回候选 Adapter，B 使用 |
| `get_sources_for_type` | `get_sources_for_type(req_type: DataReqType) -> list[str]` | 字符串列表 | 供 Hermes 策略演化使用 |

### 3.3 B 调用 C 的方式

```python
from rdi.adapters.registry import select_adapter
from rdi.models.common import DataReqType

adapter_classes = select_adapter(DataReqType(req_type))
for adapter_cls in adapter_classes:
    adapter = adapter_cls()  # 无参构造
    search_results = await adapter.search(query)
    if search_results:
        raw = await adapter.fetch(search_results[0].item_id)
```

### 3.4 C 对 B 的承诺

| 承诺项 | 保证 |
|--------|------|
| 每个 `DataSource` 都有对应 Adapter | 15 个 source 全部可 `get_adapter(source)()` 构造 |
| `select_adapter` 不遗漏 | 每个 `DataReqType` 至少有一个主源 |
| `search` 无结果 | 返回空列表 `[]`，不抛异常 |
| `fetch` 失败 | 抛出 `AdapterError`，不返回 None 或异常到 B 调用层 |
| `source` 类属性 | 子类必须定义，且与注册表一致 |
| 无参构造 | 所有子类 `__init__` 无需参数（基类签名除外） |

### 3.5 数据模型

**`SearchResult`**（`src/rdi/models/retrieval.py`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `item_id` | `str` | 是 | 数据项唯一标识，如 arxiv_id、repo 全名 |
| `title` | `str` | 是 | 标题 |
| `source` | `DataSource` | 是 | 数据源 |
| `url` | `str` | 否 | 原始 URL |
| `pdf_url` | `str \| None` | 否 | PDF 链接 |
| `metadata` | `dict` | 否 | 额外元数据 |

**`RawData`**（`src/rdi/models/retrieval.py`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | `DataSource` | 是 | 数据源 |
| `item_id` | `str` | 是 | 数据项 ID |
| `format` | `str` | 是 | 原始格式，如 `pdf`, `zip`, `urdf`, `stl`, `npz` |
| `data` | `bytes` | 是 | 原始二进制内容 |
| `url` | `str` | 否 | 获取来源 URL |
| `retrieved_at` | `datetime` | 否 | 获取时间 |
| `size_bytes` | `int` | 否 | 数据大小 |

---

## 4. B ↔ D：Skill 接口契约

### 4.1 Skill 基类

**文件**：`src/rdi/skills/base.py`

```python
class BaseSkill(ABC):
    skill_name: str

    @abstractmethod
    def process(self, data: bytes, **kwargs: Any) -> StandardResult: ...

    @abstractmethod
    def validate(self, result: StandardResult) -> ValidationReport: ...
```

### 4.2 B 调用 D 的方式

```python
from rdi.skills import default_registry

skill = default_registry.get_skill(req.req_type)
if skill is None:
    # 无 Skill，装配 MissingItem
    ...

result = skill.process(raw.data, fmt=raw.format, name=raw.item_id)
```

### 4.3 D 对 B 的承诺

| 承诺项 | 保证 |
|--------|------|
| `process` 不抛异常 | 任何失败返回 `StandardResult(success=False, errors=[...])` |
| `process` 输入为 bytes | 来自 `RawData.data` |
| `process` 返回 `StandardResult` | 字段完整，至少 `success` + `canonical_format` + `data` |
| `validate` 接收 `StandardResult` | 返回 `ValidationReport` |
| 已注册 Skill | 至少支持 `ROBOT_URDF`, `MESH`, `GRASP`, `SIM_CONFIG`, `POLICY_MODEL`, `SENSOR_DATA` |

### 4.4 数据模型

**`StandardResult`**（`src/rdi/models/common.py`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `success` | `bool` | 是 | 是否成功 |
| `canonical_format` | `str` | 是 | 标准化后的格式名 |
| `output_path` | `str \| None` | 否 | 输出文件路径 |
| `completeness_pct` | `float` | 否 | 完整度 0-100 |
| `confidence_score` | `float` | 否 | 置信度 0-1 |
| `errors` | `list[str]` | 否 | 错误列表 |
| `warnings` | `list[str]` | 否 | 警告列表 |
| `provenance` | `ProvenanceEntry \| None` | 否 | 溯源（可空） |
| `data` | `Any` | 否 | 处理后的内存对象 |

**`ParsedItem`**（`src/rdi/models/parsed.py`）

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `req_id` | `str` | 是 | 关联需求 ID |
| `req_type` | `DataReqType` | 是 | 类型 |
| `name` | `str` | 是 | 数据项名称 |
| `canonical_format` | `str` | 是 | 标准化格式 |
| `output_path` | `str` | 否 | 输出路径 |
| `data` | `Any` | 否 | 标准化数据 |
| `provenance` | `ProvenanceEntry` | 是 | 溯源 |
| `completeness_pct` | `float` | 否 | 完整度 |
| `confidence_score` | `float` | 否 | 置信度 |
| `is_inferred` | `bool` | 否 | 是否推断 |
| `warnings` | `list[str]` | 否 | 警告 |

---

## 5. B ↔ E：前端接口契约

### 5.1 前端调用入口

**文件**：`src/rdi/frontend/app.py`

| 函数 | 签名 | 说明 |
|------|------|------|
| `run_graph` | 需确认 | 接收 `user_goal: str`，返回 `state` dict |
| `build_graph` | 无参 | 返回 LangGraph 实例 |
| `render_package_tabs` | 接收 `PackageManifest` | 渲染四个 Tab |

### 5.2 E 对 B 的承诺

| 承诺项 | 保证 |
|--------|------|
| state 字段可 JSON 序列化 | 所有值必须可序列化 |
| `experiment_package` | 为 `PackageManifest` 或其 JSON 等价结构 |
| `validation_issues` | 为 `list[ValIssue]` 或 JSON 列表 |
| `missing_items` | 为 `list[MissingItem]` 或 JSON 列表 |
| `provenance` | 为 `list[str]` |

### 5.3 B 对 E 的承诺

| 承诺项 | 保证 |
|--------|------|
| `run_graph` 不抛异常 | 失败时返回包含 `errors` 字段的 state |
| `experiment_package` 存在 | 即使失败也返回最小可用结构 |
| `provenance` 可读 | 每条记录为中文文本，带时间戳 |

---

## 6. B ↔ F：质量检测接口契约

### 6.1 F 提供的脚本

**文件**：`scripts/test_connectivity.py`

| 检查项 | 预期 |
|--------|------|
| Python 版本 | >= 3.11 |
| `.env` | 存在 `LLM_API_KEY` |
| 所有 Adapter 可构造 | 15 个 `DataSource` 全部 `get_adapter(source)()` 成功 |
| ChromaDB | 可初始化、写入、读取 |

### 6.2 F 对 B 的承诺

| 承诺项 | 保证 |
|--------|------|
| PR 前检查 | 执行 ruff / format / pytest / connectivity 脚本 |
| 问题记录 | 维护联调问题记录表 |
| 集成测试骨架 | 提供 `tests/integration/test_workflow.py` |

### 6.3 B 对 F 的承诺

| 承诺项 | 保证 |
|--------|------|
| 新增代码通过 ruff | 提交前运行 `ruff check src tests` |
| 新增代码通过 format | 提交前运行 `ruff format src tests` |
| 新增功能带测试 | 核心路径有单测或集成测试 |

---

## 7. LangGraph 状态契约

**文件**：`src/rdi/graph/state.py`

每个节点只写入自己负责的分组字段。

| 字段 | 写入节点 | 读取节点 | 类型 |
|------|---------|---------|------|
| `user_goal` | 前端 | `parse_goal` | `str` |
| `paper_pdf` | 前端 | `parse_goal` | `bytes` |
| `parsed_goal` | `parse_goal` | 后续 | `GoalSpec` |
| `data_requirements` | `parse_goal` | `retrieve_data` | `list[DataReq]` |
| `retrieval_results` | `retrieve_single` | `parse_convert` | `dict[str, RetrievalResult]` |
| `retrieval_errors` | `retrieve_single` | `validate` | `list[RetrievalError]` |
| `parsed_data` | `parse_convert` | `validate` / `assemble` | `dict[str, ParsedItem]` |
| `validation_issues` | `validate` | 前端 | `list[ValIssue]` |
| `experiment_package` | `assemble` | 前端 | `PackageManifest` |
| `missing_items` | `parse_convert` / `validate` | 前端 | `list[MissingItem]` |
| `provenance` | 各节点 | 前端 | `list[str]` |
| `errors` | 各节点 | 前端 | `list[str]` |
| `iteration_count` | 全局 | 循环边 | `int` |
| `review_decision` | `human_review` | 循环边 | `str` |
| `user_feedback` | `human_review` | 循环边 | `list[str]` |

**注意**：
- `retrieve_data` 节点返回 `list[Send]`，实现 fan-out；实际写入由 `retrieve_single` 完成
- `retrieve_single` 返回的 `retrieval_results` 是 `dict[str, RetrievalResult]`，key 为 `req_id`

---

## 8. Hermes 接口契约

**文件**：`src/rdi/hermes/engine.py`

| 方法 | 签名 | 用途 |
|------|------|------|
| `inject_experience` | `(task_description: str, req_type: str) -> str` | 返回历史经验字符串，用于 Prompt 注入 |
| `record_experience` | `(task_desc, req_type, result_status, sources_used, elapsed_seconds) -> None` | 记录结果并更新统计 |
| `get_source_priority` | `(req_type: str) -> list[str]` | 返回当前策略下排序后的候选源 |
| `record_feedback` | `(task_desc, feedback_type, feedback_content, corrected_value) -> None` | 记录用户反馈 |

**调用约定**：
- B 在 `retrieve_single` 调用前 `inject_experience`
- B 在 `retrieve_single` 调用后 `record_experience`
- 经验字符串中可能包含中文，前端直接展示即可

---

## 9. 变更管理

本契约为第一次联调临时锁定版本。后续变更需遵循：

1. 任何模型字段变更 → 同步修改 `src/rdi/models/` + 调用方 + 测试
2. 任何 Adapter/Skill 签名变更 → 同步更新本契约 + 通知所有相关角色
3. 新增 `DataReqType` → 必须注册到 `ADAPTER_REGISTRY` 和 `SkillRegistry`
4. 变更后必须通过 `scripts/test_connectivity.py` + `pytest tests/unit/`

---

## 10. 附录：关键文件清单

| 角色 | 必读文件 |
|------|---------|
| B | `src/rdi/graph/nodes/retrieve_data.py`, `src/rdi/graph/state.py`, `src/rdi/hermes/engine.py` |
| C | `src/rdi/adapters/base.py`, `src/rdi/adapters/registry.py`, `src/rdi/models/retrieval.py` |
| D | `src/rdi/skills/base.py`, `src/rdi/skills/registry.py`, `src/rdi/graph/nodes/parse_convert.py` |
| E | `src/rdi/graph/state.py`, `src/rdi/models/manifest.py`, `src/rdi/frontend/app.py` |
| F | `scripts/test_connectivity.py`, `.github/workflows/ci.yml`, `pyproject.toml` |
