# Checklist

- [x] `DataSource` 枚举恰好 15 个值，不含 `semantic_scholar`
- [x] `get_adapter()` 可构造全部 15 个数据源的 Adapter，`adapter.source == source`
- [x] `src/rdi/adapters/semanticscholar.py` 与 `tests/unit/adapters/test_semanticscholar.py` 已删除，仓库无 `SEMANTIC_SCHOLAR` / `SemanticScholar` 残留引用
- [x] `tests/unit/adapters/test_construct.py`、`test_registry.py` 通过且计数为 15
- [x] `uv run pytest tests/unit/test_settings.py -q` 通过（`_env_file=None` 修复）
- [x] `uv run ruff check src tests` 无错误
- [x] `uv run ruff format --check src tests` 无未格式化文件
- [x] `uv run mypy src` 无错误
- [x] 根目录 6 个旧副本（`app.py`、`client.py`、`embedding.py`、`graspnet.py`、`ieee.py`、`paperswithcode.py`）已删除
- [x] `.github/ci.yml`、`coverage.xml`、未引用的 fixtures（`arxiv_response.xml`、`github_readme.json`、`github_search.json`）已删除
- [x] `scripts/smoke_adapters.py` 与 `README.md` 无 `SEMANTIC_SCHOLAR` / "16 种数据源" 残留，README 为 15
- [x] `uv run python scripts/test_connectivity.py` 全部 `[OK]`
- [x] `uv run pytest tests/unit/ -q --tb=short` 全绿
- [x] `docs/integration_issue_log.md` 状态已更新（关闭/已验证）
- [x] `docs/integration_quality_summary.md` 质量检查清单已勾选
