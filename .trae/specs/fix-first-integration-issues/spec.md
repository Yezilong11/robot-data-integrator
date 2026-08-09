# 修复第一次联调问题 + 清理冗余文件 Spec

## Why

第一次联调后质量门禁未全绿：1 个单元测试失败（`test_settings_defaults`）、ruff check 4 处错误、2 个文件未格式化、mypy 5 处错误；仓库存在冗余文件（6 个根目录旧版本副本、重复 CI 配置 `.github/ci.yml`、过期覆盖率报告 `coverage.xml`、未被测试引用的 fixtures）；且代码数据源数量为 16（含非规划的 `SEMANTIC_SCHOLAR`），与 `E:\智囊腾析微\数据源与数据格式汇总清单.md` 及用户确认的 **15 个数据源** 不符。

## What Changes

- 数据源恢复为 **15 个**：移除 `SEMANTIC_SCHOLAR` 枚举与 `SemanticScholarAdapter`，同步更新 Adapter 工厂、注册表、测试、冒烟脚本与 README
- 修复 `test_settings_defaults` 单测失败（`.env` 文件干扰导致默认值断言失败）
- 修复 ruff check 4 处错误（未使用导入、import 排序、类型检查块、变量命名）
- 修复 ruff format 2 个未格式化文件（`src/rdi/frontend/app.py`、`tests/integration/test_workflow.py`）
- 修复 mypy 5 处错误（3 处删除后自然消失 1 处，剩余 4 处逐一修复）
- 清理冗余文件：6 个根目录旧副本、`.github/ci.yml`、过期 `coverage.xml`、未引用的测试 fixtures
- 更新联调文档状态（`integration_issue_log.md` 状态流转、`integration_quality_summary.md` 质量清单勾选）

## Impact

- Affected specs：`角色C问题诊断与解决步骤报告.md`、`docs/interface-contracts.md`（均为 15 个数据源口径，无需改动；本 spec 使代码与文档一致）
- Affected code：
  - `src/rdi/models/common.py`（`DataSource` 枚举移除 SEMANTIC_SCHOLAR）
  - `src/rdi/adapters/__init__.py`、`registry.py`（移除映射与候选）
  - `src/rdi/adapters/semanticscholar.py`（**删除**）
  - `src/rdi/graph/builder.py`（移除未使用导入）
  - `src/rdi/skills/mesh_process.py`、`src/rdi/intelligence/client.py`、`embedding.py`（mypy 修复）
  - `pyproject.toml`（mypy lxml override）
  - `tests/unit/test_settings.py`、`tests/unit/adapters/test_registry.py`、`tests/integration/test_workflow.py`
  - `tests/unit/adapters/test_semanticscholar.py`、`tests/unit/adapters/fixtures/`（**删除**）
  - `scripts/smoke_adapters.py`、`README.md`
  - 根目录 `app.py`、`client.py`、`embedding.py`、`graspnet.py`、`ieee.py`、`paperswithcode.py`、`.github/ci.yml`、`coverage.xml`（**删除**）
  - `docs/integration_issue_log.md`、`docs/integration_quality_summary.md`

## ADDED Requirements

### Requirement: 数据源数量固定为 15

系统 SHALL 仅包含 15 个数据源，与 `数据源与数据格式汇总清单.md` 一致，不得包含 `SEMANTIC_SCHOLAR`。

#### Scenario: 枚举遍历
- **WHEN** 遍历 `DataSource` 枚举
- **THEN** 恰好 15 个值，且不含 `semantic_scholar`

#### Scenario: 工厂构造
- **WHEN** 调用 `get_adapter(source)` 遍历全部 15 个 `DataSource`
- **THEN** 全部返回对应 Adapter 实例且 `adapter.source == source`

### Requirement: 质量门禁全绿

`ruff check`、`ruff format --check`、`pytest tests/unit/`、`mypy src`、`scripts/test_connectivity.py` SHALL 全部通过，作为本次联调修复的验收基准。

#### Scenario: CI 检查命令
- **WHEN** 运行 `uv run ruff check src tests` 与 `uv run ruff format --check src tests`
- **THEN** 无任何 lint / format 错误

#### Scenario: 测试与类型
- **WHEN** 运行 `uv run pytest tests/unit/ -q --tb=short` 与 `uv run mypy src`
- **THEN** 全部测试通过、无 mypy 错误

## MODIFIED Requirements

### Requirement: settings 默认值测试不依赖 .env

`test_settings_defaults` SHALL 通过显式禁用 `.env` 文件加载（如 `Settings(_env_file=None)`）来验证默认值，而非仅清空 `os.environ`。

#### Scenario: 无 .env 环境下默认值
- **WHEN** 使用 `Settings(_env_file=None)` 构造配置
- **THEN** `llm_model`、`log_level`、`adapter_timeout` 等于代码默认值

## REMOVED Requirements

### Requirement: SEMANTIC_SCHOLAR 数据源

**Reason**：非规划内的第 16 个数据源，与指导文档 `数据源与数据格式汇总清单.md` 的 15 个数据源清单不符（该源仅是 PapersWithCode 连通性故障时的脚本级替代，不构成独立数据源）。
**Migration**：PAPER 需求类型回退至 `ArxivAdapter` / `PapersWithCodeAdapter` / `IEEEXploreAdapter` 三个候选；`SemanticScholarAdapter` 及其测试删除；冒烟脚本移除对应用例。

### Requirement: 根目录冗余文件

**Reason**：根目录 6 个文件（`app.py`、`client.py`、`embedding.py`、`graspnet.py`、`ieee.py`、`paperswithcode.py`）均为 `src/rdi/` 下对应文件的旧版本副本，其中记录的少量类型标注改进（见 `root-level-duplicate-improvements.md`）已反向合入 `src/rdi/` 源文件；`.github/ci.yml` 为未被 GitHub Actions 读取的死配置（有效配置在 `.github/workflows/ci.yml`）；`coverage.xml` 为过期报告（仅 20 行）。
**Migration**：直接删除，功能无影响；GitHub Actions 继续使用 `.github/workflows/ci.yml`。

### Requirement: 未引用的测试 fixtures

**Reason**：`tests/unit/adapters/fixtures/` 下 `arxiv_response.xml`、`github_readme.json`、`github_search.json` 无任何测试引用（测试使用内嵌 mock 数据）。
**Migration**：删除 fixtures 目录内容。
