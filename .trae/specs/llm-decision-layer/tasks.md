# Tasks

> 执行顺序：L1（决策层基座）→ L2/L3（可并行，不共享文件）→ L4/L5（可并行）→ L6（前端，依赖 L2-L5 的 state 字段与落盘产物）→ Task 7 回归。组内并行时注意「共享文件」冲突（见文末清单）。

## L1 通用决策层

- [x] Task 1: 决策层基座（新增 `src/rdi/intelligence/decisions.py`、`schemas.py`、`prompts/` 四个提示词文件，修改 `src/rdi/graph/state.py`）
  - [ ] `schemas.py` 定义 RetrievalPlan / SemanticConvention / QualityExplanation / ReviewSuggestions 四个 pydantic schema（全部含 `confidence: float`；ReviewSuggestions.verdict 用 `Literal["satisfied","revised","unsatisfied"]`；SemanticConvention.rotation/origin/unit 用 Literal 枚举）
  - [ ] `decisions.py` 提供四个纯函数 + 模块级懒加载 `_get_llm_client()`；统一捕获 `LLMUnavailableError/LLMParseError` 返回 None；统一 `logger.info("llm_decision.{name}", model=..., status="ok"|"fallback", elapsed=...)`
  - [ ] `SystemState` 一次性新增 `retrieval_plan: dict[str, RetrievalPlan]` / `semantic_map: dict[str, SemanticConvention]` / `quality_explanation: QualityExplanation | None` / `review_suggestions: ReviewSuggestions | None` / `llm_usage: list[dict]`（全部 pydantic 模型或原生类型，msgpack 可序列化）
  - [ ] 验证：`tests/unit/intelligence/test_decisions.py`——LLM 成功返回 schema 实例；monkeypatch 抛 `LLMUnavailableError` / `LLMParseError` 时返回 None 且不抛异常、日志含 fallback

## L2 ② 检索策略规划

- [x] Task 2: 检索策略规划（修改 `src/rdi/graph/nodes/retrieve_data.py`）
  - [x] `node_retrieve_single` 在 L245 query 构造处前调用 `decisions.plan_retrieval(...)`，入参含 req_type/description/keywords/object_name/context_keywords/fallback_sources/候选源清单
  - [x] 成功：LLM `queries` 置前插入现有 queries 列表（L313-344 之前），`preferred_sources` 在 `sorted_adapters`（L303-309）排序 key 中置于 fallback_sources 之后、Hermes 优先级之前
  - [x] 失败（None）：query 构造与源排序完全保持现状；provenance 追加 `[ts] retrieve_data: 检索策略 LLM 降级，使用规则兜底 ({错误类型})`
  - [x] 成功时 `retrieval_plan[req_id]` 与 `llm_usage` 写入返回值
  - [x] 验证：`tests/unit/graph/test_retrieve_data.py` 新增——LLM 返回 plan 时 query 列表以 LLM queries 开头；LLM 不可用时行为与现有用例一致（不回归）

## L3 ④ 数据语义统一

- [x] Task 3: 数据语义统一（修改 `src/rdi/skills/grasp_parse.py`、`src/rdi/skills/registry.py`、`src/rdi/graph/nodes/assemble.py`）
  - [x] `GraspSkill.process` L210 未知数据集约定检查处：先调用 `decisions.unify_semantics(...)`（入参含数据摘要 [字段名/dtype/shape/样本值]、dataset_name 线索、CanonicalGrasp 字段说明）；成功时把 `SemanticConvention` 临时并入 DATASET_CONVENTIONS 查找（`{**DATASET_CONVENTIONS, **dynamic}`），流程继续走 `_parse_generic` → `standardize_grasps`
  - [x] `_get_field`（L66-70）按 `field_map` 重映射源字段名；`standardize_grasps` 按动态约定执行换算（LLM 只产出约定，不直接计算）
  - [x] 约定写入 ParsedItem.warnings + state.semantic_map；`needs_human_review=True` 时标记该 req
  - [x] registry/节点层把 semantic_map 透传到 state（assemble 消费）
  - [x] assemble：`units.json`（L365-376）增强为 `semantic_map.json`——原 units/coordinate_frame/timestamp_epoch 保留，追加 semantic_type/rotation/origin/field_map/confidence/is_llm
  - [x] 失败（None）：保持现状（未知数据集 → success=False → MissingItem），不改变现有降级行为
  - [x] 验证：`tests/unit/skills/test_grasp_parse.py`（未知数据集 + LLM 成功 → 产出 CanonicalGrasp 且 field_map 生效；LLM 失败 → 现状降级不回归）、`tests/unit/graph/test_assemble.py`（semantic_map.json 落盘且含原字段）

## L4 ⑤ 质量报告与解释

- [x] Task 4: 质量报告解释（修改 `src/rdi/graph/nodes/assemble.py`）
  - [x] QualityReport 构建后调用 `decisions.explain_quality(...)`，入参含 QualityReport 六字段 + manifest_files 摘要 + missing_items + validation_issues + runtime_check + revision_history
  - [x] 成功：写包目录 `quality_explanation.md`（markdown：summary/strengths/risks/recommendations/usage_guidance + 溯源"由 LLM 基于 manifest.json 生成"）；manifest.files 追加该条目（format=md, source=LLM 生成）；state `quality_explanation` 与 `llm_usage` 写入返回值
  - [x] 失败（None）：规则模板渲染自然语言段落，文件头标注"规则模板生成（LLM 不可用）"，文件与 manifest 条目仍生成
  - [x] 验证：`tests/unit/graph/test_assemble.py` 新增——成功/降级两种路径下 quality_explanation.md 均落盘、manifest 含条目、成功路径文件含"LLM"标注

## L5 ⑦ 审查建议

- [x] Task 5: 审查建议（修改 `src/rdi/graph/nodes/human_review.py`）
  - [x] `node_human_review` 在 interrupt()（L182）之前调用 `decisions.suggest_review(...)`，入参含 quality_report/missing_items/validation_issues/retrieval_errors/revision_history 摘要
  - [x] 成功：interrupt payload 增加 `suggestions`（verdict/issues/rationale/confidence）；state `review_suggestions` 与 `llm_usage` 写入返回值
  - [x] 失败（None）：规则生成——有 validation_issues 或 missing_items → verdict="revised" 且 issues 逐项列出，否则 "satisfied"；suggestions 同样进入 payload 并标注规则生成
  - [x] human_review 既有分支逻辑（satisfied/revised/unsatisfied 三路、_MAX_REVIEW_ROUNDS、retry_req_ids）零改动
  - [x] 验证：`tests/unit/graph/test_human_review.py` 新增——suggestions 进入 interrupt payload（monkeypatch interrupt 捕获）；LLM 失败时建议为规则结果；既有用例不回归

## L6 前端工作区式改造

- [x] Task 6: 工作区式前端（修改 `src/rdi/frontend/app.py`）
  - [x] `build_app` 4 Tab 改为三栏：顶部状态条（run_id/状态徽章/阶段进度）+ 左栏（模式/目标/论文/本地文件/审查控件/运行按钮，模式默认值改 `"真实流程"`）+ 中栏（阶段决策看板）+ 右栏（provenance/目录树/manifest/semantic_map.json/llm_usage）
  - [x] 中栏面板：检索（RetrievalPlan queries/preferred_sources/reason + LLM|fallback 标注）、转换（SemanticConvention + needs_human_review 标黄）、打包（quality_explanation 渲染）、审查（ReviewSuggestions verdict/issues/rationale）
  - [x] `run_workflow`/`resume_workflow` 的 state→UI 映射函数扩展新字段；`build_demo_state` 补 LLM 决策字段演示占位
  - [x] 验证：前端冒烟（`uv run python -m rdi.frontend.app` 启动 + 手工走查五阶段面板）；`tests/unit/frontend/` 不回归

## 回归

- [x] Task 7: 全量回归与端到端验证
  - [x] `uv run pytest tests/ -m "not integration"` 全量通过（772 passed / 1 skipped / 9 deselected，无回归）
  - [x] `uv run ruff check src tests` 与 `uv run ruff format --check src tests` 通过（All checks passed；133 files already formatted）
  - [x] 端到端：真实流程（banana 复合目标，默认真实模式）运行，核对——检索面板有 RetrievalPlan、semantic_map.json 含语义字段、quality_explanation.md 存在、审查面板有 suggestions、前端默认"真实流程"（证据见 `data/output_packages/package-20260812-144215` 与 `package-20260812-152555`）

# Task Dependencies

- [Task 2]/[Task 3]/[Task 4]/[Task 5] 依赖 [Task 1]（schema/决策层函数是四个决策点的前提）
- [Task 6] 依赖 [Task 2]-[Task 5]（面板消费其 state 字段与落盘产物）
- [Task 7] 依赖全部任务

# 共享文件冲突提示（禁止并行编辑同一文件）

- `src/rdi/graph/state.py`：仅 Task 1
- `src/rdi/graph/nodes/assemble.py`：Task 3（semantic_map.json）与 Task 4（quality_explanation.md）——两者改动段落不同（L365 附近 vs L342 附近），但同文件建议串行或同一子代理一次完成
- `src/rdi/skills/grasp_parse.py`：仅 Task 3
- `src/rdi/skills/registry.py`：仅 Task 3
- `src/rdi/frontend/app.py`：仅 Task 6
- `src/rdi/intelligence/`：仅 Task 1 新增
