# 联调质量总结

## 1. 目标

本次 F 角色联调目标：

1. 提供一键连通性检测脚本 `scripts/test_connectivity.py`。
2. 完成集成测试骨架 `tests/integration/test_workflow.py`。
3. 维护联调问题记录表，确保问题可追踪。
4. 提交 PR 前执行代码检查与单元测试，保证质量。

## 2. 已完成工作

- 新增 `scripts/test_connectivity.py`：
  - 检查 `.env` 是否存在且包含 `LLM_API_KEY`
  - 检查所有 `DataSource` 对应 Adapter 是否可构造
  - 检查 ChromaDB 经验库 `ExperienceDB` 是否可初始化并写入
- 新增 `tests/integration/test_workflow.py`：
  - `test_parse_goal_to_data_requirements`
  - `test_full_workflow_mocks`（使用 mock LLM 与 fake Adapter 验证全链路结构）
- 在 `docs/integration_issue_log.md` 中创建问题记录表模板。
- 在 `docs/integration_quality_summary.md` 中生成联调质量总结文档。

## 3. 发现的问题

| 编号 | 模块 | 问题 | 当前状态 | 影响 |
|------|------|------|----------|------|
| 1 | `parse_goal` | 依赖 LLM 服务，真实调用需 `LLM_API_KEY` | 关闭（`.env` 已配置 `LLM_API_KEY`） | 高 |
| 2 | 集成测试 | 当前只有 mock 验证，真实 API 需后续补充 | 进行中 | 中 |

## 4. 推荐后续工作

- 根据 `integration_issue_log.md` 持续记录联调问题与修复状态。
- 由 B 提供 `build_graph()` 真实数据流测试样例，补充更多 integration case。
- 规范 PR reviewers：建议设置 B 和 F 两位进行复核。

## 5. 质量检查清单

- [x] `uv run ruff check src tests` — All checks passed
- [x] `uv run ruff format --check src tests` — 106 files already formatted
- [x] `uv run pytest tests/unit/ -q --tb=short` — 278 passed, 1 skipped
- [x] `uv run python scripts/test_connectivity.py` — 全部 `[OK]`（15 sources）
