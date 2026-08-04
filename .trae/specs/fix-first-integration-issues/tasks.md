# Tasks

- [x] Task 1: 移除 SEMANTIC_SCHOLAR，数据源恢复为 15 个
  - [x] SubTask 1.1: `src/rdi/models/common.py` 删除 `SEMANTIC_SCHOLAR = "semantic_scholar"` 枚举
  - [x] SubTask 1.2: 删除 `src/rdi/adapters/semanticscholar.py`
  - [x] SubTask 1.3: `src/rdi/adapters/__init__.py` 移除 `SemanticScholarAdapter` 导入与 `_ADAPTER_CLASSES` 映射
  - [x] SubTask 1.4: `src/rdi/adapters/registry.py` 移除 PAPER 候选、`source_name_map`、`select_adapter` 延迟导入与映射中的 SemanticScholar 引用
  - [x] SubTask 1.5: 删除 `tests/unit/adapters/test_semanticscholar.py`；更新 `test_registry.py`（移除导入、计数 16 → 15）
  - [x] SubTask 1.6: 验证：`uv run pytest tests/unit/adapters/test_construct.py tests/unit/adapters/test_registry.py -q` 通过，`DataSource` 枚举恰好 15 个

- [x] Task 2: 修复 `test_settings_defaults` 单测失败
  - [x] SubTask 2.1: `tests/unit/test_settings.py` 改为 `Settings(_env_file=None)` 构造（并保留 `patch.dict(os.environ, {}, clear=True)`），不再读取 `.env`
  - [x] SubTask 2.2: 验证：`uv run pytest tests/unit/test_settings.py -q` 通过

- [x] Task 3: 修复 ruff check / format 错误
  - [x] SubTask 3.1: `src/rdi/graph/builder.py` 删除未使用的 `MemorySaver` 导入（L10）
  - [x] SubTask 3.2: `tests/integration/test_workflow.py` 修复 import 排序（I001）、`SystemState` 移入 TYPE_CHECKING 块（TC001）、`FakeAdapter` 变量名改小写（N806）
  - [x] SubTask 3.3: 运行 `uv run ruff format src/rdi/frontend/app.py tests/integration/test_workflow.py` 格式化两个文件
  - [x] SubTask 3.4: 验证：`uv run ruff check src tests` 与 `uv run ruff format --check src tests` 全绿

- [x] Task 4: 修复 mypy 5 处错误
  - [x] SubTask 4.1: `src/rdi/intelligence/client.py` L126 删除多余的 `# type: ignore[no-any-return]`
  - [x] SubTask 4.2: `src/rdi/intelligence/embedding.py` L49 删除多余的 `# type: ignore[no-any-return]`
  - [x] SubTask 4.3: `src/rdi/skills/mesh_process.py` L50 返回类型不匹配（Geometry vs Trimesh）——用 `isinstance` 守卫或 `cast` 修复
  - [x] SubTask 4.4: `pyproject.toml` 增加 `[[tool.mypy.overrides]] module = "lxml.*"` `ignore_missing_imports = true`
  - [x] SubTask 4.5: 验证：`uv run mypy src` 全绿（semanticscholar.py 已在 Task 1 删除，对应错误自然消失）

- [x] Task 5: 清理冗余文件
  - [x] SubTask 5.1: 删除根目录旧副本：`app.py`、`client.py`、`embedding.py`、`graspnet.py`、`ieee.py`、`paperswithcode.py`
  - [x] SubTask 5.2: 删除死配置 `.github/ci.yml`（有效 CI 在 `.github/workflows/ci.yml`）
  - [x] SubTask 5.3: 删除过期覆盖率报告 `coverage.xml`
  - [x] SubTask 5.4: 删除未被测试引用的 fixtures：`tests/unit/adapters/fixtures/arxiv_response.xml`、`github_readme.json`、`github_search.json`
  - [x] SubTask 5.5: 验证：`git status` 确认删除清单，`uv run pytest tests/unit/ -q` 仍通过

- [x] Task 6: 更新 smoke_adapters.py 与 README 数据源计数（依赖 Task 1）
  - [x] SubTask 6.1: `scripts/smoke_adapters.py` 移除 `(DataSource.SEMANTIC_SCHOLAR, ...)` 用例，改为 PapersWithCode 或删除
  - [x] SubTask 6.2: `README.md` 将 "16 种数据源适配器 / 16 种数据源" 改为 "15"，并同步项目结构树注释
  - [x] SubTask 6.3: 验证：`uv run python scripts/smoke_adapters.py` 可运行（预期无 SemanticScholar 引用）

- [x] Task 7: 更新联调文档
  - [x] SubTask 7.1: `docs/integration_issue_log.md`：问题 1（GitHub search 空）状态更新为已验证/关闭（真实根因 401 需 token）；问题 2（parse_goal 依赖 LLM）状态更新为关闭（`.env` 已配置 LLM_API_KEY）
  - [x] SubTask 7.2: `docs/integration_quality_summary.md`：勾选质量检查清单 4 项（ruff check / format / pytest / connectivity）

- [x] Task 8: 全量验证与收口（依赖 Task 1-7）
  - [x] SubTask 8.1: `uv run ruff check src tests` 通过
  - [x] SubTask 8.2: `uv run ruff format --check src tests` 通过
  - [x] SubTask 8.3: `uv run pytest tests/unit/ -q --tb=short` 全绿
  - [x] SubTask 8.4: `uv run mypy src` 全绿
  - [x] SubTask 8.5: `uv run python scripts/test_connectivity.py` 全部 OK
  - [x] SubTask 8.6: `uv run pytest tests/integration/ -q` 可运行（集成测试默认被 -m 排除，验证不被破坏）

# Task Dependencies

- [Task 6] depends on [Task 1]（smoke 脚本与 README 引用了 SEMANTIC_SCHOLAR）
- [Task 8] depends on [Task 1-7]
- [Task 2] / [Task 3] / [Task 4] / [Task 5] / [Task 7] 相互独立，可并行
- [Task 4.4] 与 [Task 4.5] 需在 [Task 1] 完成后验证（删除 semanticscholar.py 消除 1 处 mypy 错误）
