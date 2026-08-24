# Checklist

## L1 通用决策层
- [x] 新增 `intelligence/decisions.py`：四个决策点纯函数，捕获 `LLMUnavailableError/LLMParseError` 后返回 None（降级）或结构化结果，统一结构化日志（`llm_decision.{name}`，记录 model/status/elapsed）
- [x] 新增 `intelligence/schemas.py`：RetrievalPlan / SemanticConvention / QualityExplanation / ReviewSuggestions 四个 pydantic schema（含 confidence 字段）
- [x] 新增 `intelligence/prompts/{retrieval_plan,semantic_unification,quality_explanation,review_suggestions}.py` 系统提示词
- [x] `SystemState` 一次性新增 `retrieval_plan` / `semantic_map` / `quality_explanation` / `review_suggestions` / `llm_usage` 五个字段（全部 msgpack 可序列化）

## L2 ② 检索策略规划
- [x] `node_retrieve_single` 在 query 构造前调用决策层生成 `RetrievalPlan`；LLM queries 置前 + 现有确定性 queries 兜底在尾部
- [x] `preferred_sources` 影响 `sorted_adapters` 排序（LLM 偏好源权重高于 Hermes 优先级）
- [x] LLM 失败时完全走现状确定性逻辑（query 拼接 + Hermes 排序），provenance 记录"LLM 降级"
- [x] 检索阶段前端面板展示 RetrievalPlan（queries/preferred_sources/reason + LLM|fallback 标注）

## L3 ④ 数据语义统一
- [x] `GraspSkill.process` 未知数据集约定检查处（L210）调用决策层生成 `SemanticConvention`；成功时并入 DATASET_CONVENTIONS 查找（`{**DATASET_CONVENTIONS, **dynamic}`），流程继续走 `_parse_generic` → `standardize_grasps`
- [x] `_get_field` 按 `field_map` 重映射源字段名；换算仍由 `standardize_grasps` 确定性代码执行（LLM 只产出约定，不直接计算）
- [x] 约定写入 ParsedItem.warnings + state.semantic_map；assemble 落盘 semantic_map.json（保留原 units/coordinate_frame/timestamp_epoch，追加 semantic_type/rotation/origin/field_map/confidence/is_llm）
- [x] `needs_human_review=True` 的项在审查面板标黄提示"语义待人工确认"
- [x] LLM 失败时保持现状（未知数据集 → success=False → MissingItem），流程不中断
- [x] 转换阶段前端面板展示 SemanticConvention（semantic_type/rotation/origin/field_map + LLM|fallback 标注）

## L4 ⑤ 质量报告与解释
- [x] assemble 在 QualityReport 构建后调用决策层生成 `QualityExplanation`；写入包目录 `quality_explanation.md`（含"由 LLM 生成"溯源标注）
- [x] manifest.files 追加 quality_explanation.md 条目（format=md）
- [x] 降级：规则模板渲染自然语言段落，文件头标注"规则模板生成（LLM 不可用）"，文件仍存在
- [x] 打包阶段前端渲染 quality_explanation（summary/strengths/risks/recommendations/usage_guidance）

## L5 ⑦ 审查建议
- [x] `node_human_review` 在 interrupt 前调用决策层生成 `ReviewSuggestions`，作为 interrupt payload 的 `suggestions` 字段传入
- [x] 前端审查面板展示 verdict/issues/rationale，用户仍自主决策
- [x] 降级：规则生成（有 validation_issues 或 missing_items→revised 且逐项列出，否则 satisfied），展示标注"规则生成"
- [x] human_review 既有分支逻辑（三路决策/循环上限/retry_req_ids）不改变

## L6 前端工作区式改造
- [x] `build_app` 4 Tab 改为三栏工作区：顶部状态条（run_id/状态徽章/阶段进度）+ 左栏（输入与控制，默认模式改"真实流程"）+ 中栏（随阶段切换的决策看板）+ 右栏（输出详情）
- [x] 中栏五个阶段面板：检索（RetrievalPlan）/转换（SemanticConvention）/校验（沿用）/打包（quality_explanation）/审查（ReviewSuggestions）
- [x] 右栏展示 provenance / 目录树 / manifest.json / semantic_map.json / llm_usage
- [x] `build_demo_state` 同步补 LLM 决策字段演示占位；演示流程产物仍写 DEMO_ROOT 不混入真实包

## 回归
- [x] `uv run pytest tests/ -m "not integration"` 全量通过（772 passed / 1 skipped / 9 deselected，含既有用例无回归）
- [x] 每个决策点新增单测：成功路径 + LLM 不可用降级 + LLMParseError 降级（断言流程不中断、返回确定性结果、provenance 有降级记录）
- [x] `uv run ruff check src tests` 与 `ruff format --check src tests` 通过
- [x] 端到端核对：真实流程（banana 复合目标）运行，验证——检索面板有 RetrievalPlan、semantic_map.json 落盘且含语义字段、quality_explanation.md 存在、审查面板有 suggestions、前端默认"真实流程"
