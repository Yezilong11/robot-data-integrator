# 前端工作区式改造（落地设计稿） Spec

## Why

现有 Gradio 前端把「输入与控制 / LLM 决策看板 / 输出详情」硬塞进一个三栏 `gr.Row`，所有功能挤在一页导致显示不全；决策看板是五个平铺面板、缺乏过程可视化；数据以纯文本目录树呈现。用户已确认新版设计稿 [ui-redesign-mockup.html](file:///c:/Users/yzl13/Documents/GitHub/robot-data-integrator/docs/ui-redesign-mockup.html)，需将其落地到 Gradio（**不更换技术栈**）。

## What Changes

- **主题**：全局配色改为黑底橙调（GitHub 暗色底 `#0d1117`/`#010409`，橙色主色 `#f78166`，辅以琥珀 `#d29922`/绿 `#3fb950`），通过 Gradio 自定义 CSS 注入。
- **布局**：重构为「活动栏 + 左栏（随活动栏切换的面板）+ 中栏主视图 + 右栏检查器 + 底部状态栏」的工作区形态。
- **活动栏**：6 个入口全部保留且真实可切换——🗂 资源管理器 / ⌕ 数据检索 / ◉ 决策 / ✓ 审查 / ▷ 日志 / ⚙ 设置（设置位于日志下方，不沉底）。
- **中栏**（占比最大）：灯带式工作流（细线挂点，完成逐个点亮、当前呼吸）→ LLM 分析主体（实时显化思考）→ 目标输出（单行汇总，点击展开文件清单）。
- **目标输入条**（常驻中栏底部）：`[＋ 上传 PDF] [目标输入框] [运行/继续运行]`，运行与继续运行合并为单按钮状态切换。
- **文件树**：改为 VSCode 风格（可折叠、缩进引导、类型图标、选中高亮）。
- **检查器**：右栏 4 个 Tab——详情 / manifest / 语义 / LLM 调用。
- **比例**：中栏最大、两侧较小，用 Gradio `scale` 比例实现；**拖拽调宽为 Gradio 原生不支持的能力，明确不在本 spec 范围**（后续可单独评估）。

## Impact

- 受影响代码：`src/rdi/frontend/app.py`（主）、`tests/unit/frontend/*`（测试更新）。
- 兼容性：保留现有纯逻辑函数作为「数据准备层」——`build_req_status_table` / `manifest_tree` / `summarize_state` / `derive_stage_progress` / `stage_progress_view` / `semantic_map_json` / `_decision_source` / `build_status_bar` / `_board_completed` 及各 `_render_*` 决策点渲染逻辑继续复用；改造 `build_app` 布局并新增视图渲染函数。
- **BREAKING（前端内部）**：`build_decision_board` 由「五面板平铺」改为「灯带 + LLM 分析 + 目标输出」组合，其既有 HTML 断言需随测试同步更新。

## ADDED Requirements

### Requirement: 黑底橙调主题

系统 SHALL 通过 Gradio 自定义 CSS 将前端整体呈现为黑底橙调（背景 `#0d1117`/`#010409`、边框 `#30363d`、文字 `#e6edf3`、主色橙 `#f78166`），替代默认浅色主题。

#### Scenario: 主题生效

- **WHEN** 前端启动
- **THEN** 页面背景为深色、主操作/高亮为橙色，与设计稿配色一致

### Requirement: 工作区式布局与活动栏

系统 SHALL 提供「活动栏 + 左栏面板 + 中栏主视图 + 右栏检查器 + 底部状态栏」的工作区布局，中栏在可用宽度中占比最大、左右侧栏较小。

#### Scenario: 三栏比例

- **WHEN** 前端渲染
- **THEN** 中栏宽度明显大于左栏与右栏（通过 `scale` 比例实现）

#### Scenario: 活动栏六入口

- **WHEN** 用户点击活动栏任一图标
- **THEN** 左栏切换到对应面板（资源管理器 / 数据检索 / 决策 / 审查 / 日志 / 设置），且设置图标位于日志图标下方

### Requirement: 灯带式工作流

系统 SHALL 以「一条细线 + 5 个挂点（检索→转换→校验→打包→审查）」呈现工作流进度，完成节点点亮、当前节点呼吸高亮、未开始为灰点。

#### Scenario: 阶段点亮

- **WHEN** 运行到某阶段
- **THEN** 该阶段挂点高亮为当前态，其之前阶段为已完成态，之后阶段为未开始态

### Requirement: LLM 分析主体视图

系统 SHALL 在中栏以「最大占比」实时呈现 LLM 的分析/思考内容，含「LLM 生成 / 规则兜底」来源标注；不展示杜撰的置信度数值。

#### Scenario: 思考内容展示

- **WHEN** 某阶段产出 LLM 决策（reason/summary/rationale 等）
- **THEN** 中栏主体展示对应思考文本，并标注「LLM 生成」或「规则兜底」，不显示 confidence 数字

### Requirement: 目标输出可展开

系统 SHALL 以单行汇总呈现目标输出（如「robot-data-package 已生成」），点击后展开具体产物文件清单。

#### Scenario: 展开产物

- **WHEN** 用户点击目标输出单行
- **THEN** 展开显示数据包内文件清单（路径 + 大小）

### Requirement: 目标输入条（含 PDF 上传与运行合并）

系统 SHALL 在中栏底部常驻目标输入条，包含「＋ 上传论文 PDF」入口、目标输入框、以及「运行/继续运行」合并按钮（流程运行至审查中断时按钮文字由「运行」变为「继续运行」）。

#### Scenario: 上传 PDF

- **WHEN** 用户点击「＋」
- **THEN** 出现 PDF 上传入口，可选择论文 PDF 文件

#### Scenario: 运行与继续运行合并

- **WHEN** 真实流程运行至 human_review 中断
- **THEN** 运行按钮文字切换为「继续运行」，点击后以用户审查决定继续流程

### Requirement: VSCode 风格文件树

系统 SHALL 在「资源管理器」面板以 VSCode 风格呈现数据包目录树（可折叠目录、缩进引导、类型图标、选中高亮）。

#### Scenario: 目录树展示

- **WHEN** 数据包目录存在或 manifest 含文件列表
- **THEN** 资源管理器面板显示带层级缩进与文件类型图标的目录树

### Requirement: 检查器四 Tab

系统 SHALL 在右栏检查器提供「详情 / manifest / 语义 / LLM 调用」四个可切换 Tab。

#### Scenario: 检查器切换

- **WHEN** 用户切换检查器 Tab
- **THEN** 右栏显示对应内容（详情 / manifest.json / semantic_map.json / llm_usage 调用记录）

## MODIFIED Requirements

### Requirement: build_decision_board 视图形态

`build_decision_board` SHALL 由「五面板平铺」改为输出「灯带工作流 + LLM 分析 + 目标输出」的组合视图，继续消费既有决策点数据（retrieval_plan / semantic_map / quality_explanation / review_suggestions / interrupt_payload）。

#### Scenario: 组合视图

- **WHEN** 传入 state
- **THEN** 返回包含灯带节点、LLM 思考文本、目标输出汇总的 HTML

## REMOVED Requirements

### Requirement: 单页平铺五决策面板

**Reason**：五面板平铺导致中栏信息过载、缺乏「先结论后过程」的层次，已被灯带 + 思考 + 输出的组合视图取代。
**Migration**：决策点原始数据迁移至「◉ 决策」面板与「LLM 分析」思考文本，来源标注（LLM 生成/规则兜底）保留。
