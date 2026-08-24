# LLM 智能决策层 Spec（②④⑤⑦）

## Why

用户判定当前系统"太过欠缺 LLM 元素"：全库仅 parse_goal（目标解析）与 human_review（反馈转换）两处调用 LLM，其余 5 节点 / 15 适配器 / 12 skill 全部为确定性代码。在竞赛场景（2026 挑战杯·科学数据整合，方向 1 维度 A）下，这不足以支撑"AI 应用"的定性。

本阶段实现四个 LLM 决策点，把系统从"确定性流水线"升级为"LLM 理解·规划·评估·解释 + 确定性执行"的双引擎架构：

- **② 检索策略规划**：LLM 根据需求语义生成搜索词组合与源偏好，替代当前"关键词机械拼接"。
- **④ 数据语义统一**：LLM 在"原始格式 → Canonical 中间表示"转换环节动态补全约定（单位/坐标系/字段映射），让既有中间表示机制覆盖未知/异构数据集（用户核心诉求）。
- **⑤ 质量报告与解释**：LLM 把 assemble 产出的纯数字 QualityReport 翻译为自然语言风险解释（summary/risks/recommendations/usage_guidance）。
- **⑦ 审查建议**：LLM 在 human_review 中断前给出"建议决策 + 逐项问题清单 + 理由"，让用户审查不再盲选。

### 铁律（用户明确要求）

1. **LLM 决策错误直接用规则兜底**：任何决策点 LLM 不可用（`LLMUnavailableError`）/解析失败（`LLMParseError`）时，必须降级到确定性逻辑并返回有结果，**绝不让运行中断**。复用 human_review.py `_convert_feedback_to_goal`（L89-97）的降级范式。
2. **数值计算永远留在代码层**：LLM 只做判断/决策/解释（输出语义、映射、说明），所有换算/计算仍由确定性代码执行，保证可复现、可校验。
3. **前端改为工作区式设计**（参考 Trae Work / Kimi Work）：架构层面用"决策面板"凸显 LLM 过程，演示层面同步改造（默认值改"真实流程"列入本 plan 一并执行）。

## What Changes

### L1 通用 LLM 决策层（新增模块）

新增 `src/rdi/intelligence/decisions.py`，统一承载四个决策点：

- 每个决策点一个纯函数，签名模式 `fn(inputs...) -> Model | None`（返回 None 表示降级），内部捕获 `LLMUnavailableError/LLMParseError` 后降级为确定性结果。
- 统一结构化日志：`llm_decision.{name}` 记录 model / 成功 or 降级原因 / 耗时；降级时 provenance 写入"LLM 降级，使用规则兜底"。
- 模块级懒加载 `_get_llm_client()` 单例（复用现有模式），便于测试 monkeypatch。
- `SystemState` 一次性新增字段（全部 pydantic 模型，msgpack 可序列化）：
  - `retrieval_plan: dict[str, RetrievalPlan]`（key=req_id）
  - `semantic_map: dict[str, SemanticConvention]`（key=req_id）
  - `quality_explanation: QualityExplanation | None`
  - `review_suggestions: ReviewSuggestions | None`
  - `llm_usage: list[dict[str, str | float]]`（每次 LLM 决策的调用记录：decision/model/status/elapsed，供前端与报告展示）
- 新增 schema 模型放 `src/rdi/intelligence/schemas.py`（RetrievalPlan / SemanticConvention / QualityExplanation / ReviewSuggestions），提示词放 `src/rdi/intelligence/prompts/` 下对应文件。

### L2 ② 检索策略规划

插入点：[retrieve_data.py](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/graph/nodes/retrieve_data.py#L225-L247) `node_retrieve_single` query 构造处。

- 现状：`query = " ".join(keywords) if keywords else description`（L245），纯机械拼接，中英混排常导致 Adapter 零命中。
- 改造：查询 Adapter 清单与关键词前，调用 LLM 生成 `RetrievalPlan`：
  - 输入：req_type / description / keywords / object_name / context_keywords / fallback_sources / 候选源清单。
  - 输出：`RetrievalPlan { queries: list[str]（按优先级排序的完整搜索词串）; preferred_sources: list[str]; reason: str; confidence: float }`。
  - 落地：`queries` 替换/插入现有 queries 构建逻辑（L313-344，LLM queries 置前、现有确定性 queries 兜底在尾部），`preferred_sources` 重排 `sorted_adapters`（L303-309，LLM 偏好源权重高于 Hermes 优先级）。
  - 降级（None）：完全走现状确定性逻辑，provenance 记录降级。
- 数值/排序等计算仍在代码层；LLM 只产出"搜什么词、优先哪个源"的决策。

### L3 ④ 数据语义统一

插入点：skill 层 [grasp_parse.py](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/skills/grasp_parse.py#L207-L218) `GraspSkill.process` 未知数据集约定检查处（`dataset_name not in DATASET_CONVENTIONS`）。

- 现状：GRASP 链路本就是「先转中间表示再统一处理」——`standardize_grasps`（L113-133）按硬编码 `DATASET_CONVENTIONS`（L50-55，仅 4 个数据集）把各数据集原始抓取统一为 `CanonicalGrasp`；未知数据集在 process L210 直接 success=False，registry（L179）兜底为 MissingItem。
- 改造：process 检测到未知数据集约定时，调用 LLM 生成 `SemanticConvention`（动态约定）：
  - 输入：原始数据摘要（字段名/dtype/shape/样本值）、dataset_name 线索、期望中间表示（CanonicalGrasp 字段）说明。
  - 输出：`SemanticConvention { dataset_name: str; semantic_type: str; rotation: Literal[matrix|quaternion_wxyz|quaternion_xyzw|euler|unknown]; origin: Literal[camera|object_center|world|unknown]; unit: Literal[meter|millimeter|unknown]; field_map: dict[str,str]; confidence: float; needs_human_review: bool }`。
  - 落地：process 内临时并入查找（`{**DATASET_CONVENTIONS, **dynamic}`），流程继续走 `_parse_generic` → `standardize_grasps`；`_get_field`（L66-70）按 `field_map` 重映射源字段名；**换算仍由 `standardize_grasps` 确定性代码执行**（LLM 只产出约定，不直接计算）；约定写入 ParsedItem.warnings + state.semantic_map + 落盘 semantic_map.json（溯源），`needs_human_review=True` 时标记待人工确认。
  - 降级（None）：保持现状（未知数据集 → success=False → MissingItem），不中断。
- 中间表示机制（CanonicalGrasp / standardize_grasps）完全不变；LLM 只动态补全约定表。

### L4 ⑤ 质量报告与解释

插入点：[assemble.py](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/graph/nodes/assemble.py#L342-L357) QualityReport 构建后、manifest 写盘时。

- 现状：quality_report 纯数字，无任何自然语言解读。
- 改造：调用 LLM 生成 `QualityExplanation`：
  - 输入：QualityReport 六字段 + manifest_files 摘要（req_id/format/source/confidence/completeness/data_source_quality/is_fallback）+ missing_items + validation_issues + runtime_check + revision_history 摘要。
  - 输出：`QualityExplanation { summary: str; strengths: list[str]; risks: list[str]; recommendations: list[str]; usage_guidance: str; confidence: float }`。
  - 落地：写入包目录 `quality_explanation.md`（markdown 渲染，含溯源："本解释由 LLM 基于 manifest.json 生成"），manifest 文件列表追加该项（format=md，source=LLM 生成），state 存 `quality_explanation` 供前端直接渲染。
  - 降级（None）：确定性模板渲染——基于数字规则拼自然语言段落（如"满足率 X%，缺失 Y 项，平均置信度 Z"），文件头标注"规则模板生成（LLM 不可用）"。

### L5 ⑦ 审查建议

插入点：[human_review.py](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/graph/nodes/human_review.py#L150-L216) 节点入口（interrupt 之前）。

- 现状：`_build_retrieval_advice`（L100-104）是确定性字符串拼接；用户中断等待时无任何决策参考。
- 改造：`node_human_review` 在 interrupt() 前调用 LLM 生成 `ReviewSuggestions`：
  - 输入：quality_report 摘要 + missing_items + validation_issues + retrieval_errors + revision_history。
  - 输出：`ReviewSuggestions { verdict: Literal["satisfied","revised","unsatisfied"]; issues: list[{req_id; problem: str; action: str}]; rationale: str; confidence: float }`。
  - 落地：写入 state `review_suggestions`，作为 interrupt payload 的一部分（`resume` 的 dict 里带 `suggestions`），前端审查面板展示"LLM 建议：xxx，理由：xxx"，用户仍自主决策。
  - 降级（None）：确定性规则——有 validation_issues 或 missing_items → verdict="revised"（issues 逐项列出缺失/校验项），否则 "satisfied"。
- 不改变 human_review 既有分支逻辑（satisfied/revised/unsatisfied 三路、循环上限、retry_req_ids 语义均不动）。

### L6 前端工作区式改造（Trae Work / Kimi Work 风格）

改造 [app.py](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/src/rdi/frontend/app.py#L702-L785) `build_app` 布局，4 Tab 改为三栏工作区：

- **顶部状态条**：run_id / 包状态徽章（success|failed|demo）/ 阶段进度条（解析→检索→转换→校验→打包→审查）。
- **左栏（上下文 + 控制）**：现有"目标输入"内容收敛至此——模式选择（默认值改 **"真实流程"**）、目标输入、论文上传、本地文件注入、审查决策/反馈控件、运行/继续按钮。
- **中栏（主工作区，随阶段切换的决策看板）**，每个阶段同时展示 LLM 决策与确定性执行结果：
  - 检索阶段：`RetrievalPlan` 面板（queries / preferred_sources / reason，标注 LLM 或 fallback）+ 需求状态表；
  - 转换阶段：ParsedItem 列表 + `SemanticConvention` 面板（semantic_type / rotation / origin / field_map / needs_human_review 标记）；
  - 校验阶段：validation_issues + runtime_check（沿用现有）；
  - 打包阶段：`quality_explanation.md` 渲染（summary/risks/recommendations/usage_guidance）+ manifest 摘要；
  - 审查阶段：`ReviewSuggestions` 面板（verdict / issues 逐项 / rationale）+ 用户决策控件。
- **右栏（输出详情）**：provenance、数据包目录树、manifest.json、semantic_map.json、llm_usage 记录。
- 演示模式保留为"环境保险丝"但不默认；`build_demo_state` 同步补 LLM 决策字段的演示占位。

## Impact

- 受影响 specs：`SystemState`（+5 字段）、`PackageManifest.files`（+quality_explanation.md 条目）、`units.json`→`semantic_map.json` 增强。
- 受影响代码：新增 `intelligence/decisions.py`、`intelligence/schemas.py`、`intelligence/prompts/{retrieval_plan,semantic_unification,quality_explanation,review_suggestions}.py`；修改 `graph/state.py`、`graph/nodes/retrieve_data.py`、`skills/grasp_parse.py`（④动态约定）、`skills/registry.py`（④透传）、`graph/nodes/assemble.py`、`graph/nodes/human_review.py`、`frontend/app.py`（含 run_workflow/resume_workflow 的 state→UI 映射）。
- 用户可见变化：前端变为工作区式三栏；每个 LLM 决策点有可视化面板与 LLM/fallback 标注；数据包新增 quality_explanation.md 与增强版 semantic_map.json；运行默认走真实流程。
- 成本/性能：每次运行新增 LLM 调用 ≈ ②按 req 数 + ④仅未知数据集时触发（已知数据集零开销）+ ⑤×1 + ⑦×1。说明：②④ 失败即降级为现状，不影响运行成败。
- 兼容性：全为加字段/加文件/加配置（兼容）；唯一行为变更 = 前端默认模式改"真实流程"（原"演示流程"）。

## ADDED Requirements

### Requirement: LLM 决策失败必须规则兜底（L1）

The system SHALL 保证每个 LLM 决策点在 LLM 不可用或解析失败时降级到确定性结果，绝不中断运行。

#### Scenario: LLM 不可用
- **WHEN** 任一决策点调用抛 `LLMUnavailableError`
- **THEN** 流程继续，使用规则兜底结果（②现状 query 拼接 / ④未知数据集现状降级 / ⑤规则模板 / ⑦规则 verdict），provenance 记录"LLM 降级"与原因

#### Scenario: LLM 返回非法 JSON
- **WHEN** 任一决策点解析抛 `LLMParseError`
- **THEN** 同上降级路径，不抛异常

### Requirement: 检索策略规划（L2）

The system SHALL 在单需求检索前用 LLM 生成搜索词与源偏好。

#### Scenario: LLM 规划命中率提升
- **WHEN** 检索 banaba 抓取标注（req_type=GRASP, object_name=banana）
- **THEN** retrieval_plan[req_id].queries 含中英混合搜索词与物体名，preferred_sources 影响候选源排序；结果写入 state 且前端可见

#### Scenario: LLM 失败走现状逻辑
- **WHEN** LLM 不可用
- **THEN** query 构造与源排序完全等于当前实现，provenance 记录降级

### Requirement: 数据语义统一（L3）

The system SHALL 在既有「原始格式 → Canonical 中间表示」转换机制上，用 LLM 动态补全未知数据集的转换约定。

#### Scenario: 未知数据集统一表达
- **WHEN** 检索到未知数据集（不在 `DATASET_CONVENTIONS`）的抓取数据
- **THEN** `GraspSkill.process` 调用 LLM 生成 `SemanticConvention`（字段映射/单位/坐标系/旋转表示），`standardize_grasps` 按动态约定转换出 `CanonicalGrasp`；约定写入 state.semantic_map 并落盘 `semantic_map.json`；needs_human_review=True 的项前端标黄提示

#### Scenario: LLM 失败保留现状
- **WHEN** LLM 不可用或解析失败
- **THEN** 未知数据集仍按现状降级（success=False → MissingItem），流程不中断

### Requirement: 质量报告解释（L4）

The system SHALL 为每个数据包生成自然语言质量解释文件。

#### Scenario: 数据包含解释文件
- **WHEN** assemble 生成数据包
- **THEN** 包内含 quality_explanation.md（summary/strengths/risks/recommendations/usage_guidance），manifest.files 含该条目，前端打包阶段渲染

#### Scenario: 解释降级为模板
- **WHEN** LLM 不可用
- **THEN** quality_explanation.md 由规则模板生成并标注"LLM 不可用"，文件仍存在、流程不中断

### Requirement: 审查建议（L5）

The system SHALL 在用户审查中断前给出 LLM 建议决策与逐项问题清单。

#### Scenario: 审查有参考
- **WHEN** 数据包含缺失/校验问题，human_review 中断等待用户
- **THEN** interrupt payload 含 suggestions（verdict/issues/rationale），前端展示；用户可采纳或无视

#### Scenario: 建议降级
- **WHEN** LLM 不可用
- **THEN** suggestions 由规则生成（有缺失/校验问题→revised，否则 satisfied），展示时标注"规则生成"

### Requirement: 工作区式前端（L6）

The system SHALL 将前端改为三栏工作区并默认真实流程。

#### Scenario: 决策可见
- **WHEN** 真实流程运行至检索/转换/打包/审查阶段
- **THEN** 中栏分别展示 RetrievalPlan / SemanticConvention / quality_explanation / ReviewSuggestions 面板，均标注 LLM 或 fallback 来源

#### Scenario: 默认真实
- **WHEN** 页面加载
- **THEN** 模式选择默认值="真实流程"；演示流程仍可选（产物写 DEMO_ROOT 不混入真实包）

## MODIFIED Requirements

### Requirement: 语义约定落盘扩展（L3/L4 基础）

原 `QualityReport` 六数字字段不变；新增并行产物 `quality_explanation.md` 与 state `quality_explanation`。`units.json` 扩展为 `semantic_map.json`（保留原 units/coordinate_frame/timestamp_epoch 字段，追加 LLM 动态约定字段：semantic_type/rotation/origin/field_map/confidence/is_llm）。

#### Scenario: 旧字段保留
- **WHEN** 生成 semantic_map.json
- **THEN** 原 units.json 字段（units/coordinate_frame/timestamp_epoch）仍存在，新增语义字段追加，不破坏既有消费方

## REMOVED Requirements

无删除项。
