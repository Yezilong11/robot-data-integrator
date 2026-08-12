# Tasks

> 范围：将设计稿 [ui-redesign-mockup.html](../../../docs/ui-redesign-mockup.html) 落地到 Gradio `app.py`，不换技术栈。
> 原则：所有改动集中在 `src/rdi/frontend/app.py`（单文件），任务**串行**执行；每个任务交付可验证改动 + 对应测试更新。

- [x] Task 1: 黑底橙调主题 CSS 注入
  - [x] 在 `app.py` 定义主题 CSS 常量（配色变量：背景 `#0d1117`/`#010409`、边框 `#30363d`、文字 `#e6edf3`、主色橙 `#f78166`、琥珀 `#d29922`、绿 `#3fb950`）
  - [x] `build_app` 的 `gr.Blocks(css=...)` 注入全局 CSS，覆盖 Gradio 默认浅色主题（背景、卡片、按钮、输入框、文字色）
  - [x] 保留并复用现有 `_DECISION_CSS` 中「LLM 生成/规则兜底」徽章配色语义，迁移到橙色主题
  - [x] 验证：`uv run python -m rdi.frontend.app` 启动后页面为深色 + 橙色主色（人工走查）

- [x] Task 2: 新增纯逻辑视图渲染函数（可单测）
  - [x] 新增 `render_file_tree_html(state)`：基于 `package_tree` / `manifest_tree` 生成 VSCode 风格文件树 HTML（目录可折叠标记、缩进引导、类型图标、文件名）
  - [x] 新增 `render_workflow_html(state)`：基于 `_board_completed` / `stage_progress` 生成灯带式 5 节点 HTML（done/current/pending 状态类）
  - [x] 新增 `render_llm_analysis_html(state)`：抽取当前阶段的 LLM 思考文本（retrieval_plan.reason / semantic_map / quality_explanation.summary / review_suggestions.rationale），输出含「LLM 生成/规则兜底」来源标注、不含 confidence 数字的 HTML
  - [x] 新增 `render_target_output_html(state)`：单行汇总 + 可展开文件清单 HTML
  - [x] 新增 `render_inspector_html(state, tab)`：检查器 4 tab 的内容 HTML（详情 / manifest / 语义 / LLM 调用）
  - [x] 验证：`tests/unit/frontend/test_views.py` 新增——各渲染函数输出含关键标记（节点状态类、LLM 来源标注、文件路径、不出现 confidence）

- [x] Task 3: `build_app` 布局重构
  - [x] 用 `gr.Blocks` 搭建「顶部状态条 + 活动栏 + 左栏面板 + 中栏（flex 最大）+ 右栏检查器 + 底部状态栏」结构
  - [x] 活动栏用 `gr.Tabs`（或等效组件）承载 6 个入口，CSS 改造为左侧竖排图标栏，顺序：资源管理器 / 数据检索 / 决策 / 审查 / 日志 / 设置
  - [x] 左栏 6 个面板对应内容：资源管理器=文件树、数据检索=数据需求状态表（`build_req_status_table`）、决策=四决策点原始数据、审查=审查决定+反馈+missing_items、日志=provenance+llm_usage、设置=运行模式+本地文件注入
  - [x] 中栏：灯带工作流（`render_workflow_html`）+ LLM 分析（`render_llm_analysis_html`，主体）+ 目标输出（`render_target_output_html`）+ 底部目标输入条
  - [x] 右栏检查器：`gr.Tabs` 4 个 tab，内容来自 `render_inspector_html`
  - [x] 底部状态栏：`build_status_bar` + LLM 调用次数 + 耗时
  - [x] 验证：`uv run python -m rdi.frontend.app` 启动，走查三栏比例与六面板切换

- [x] Task 4: 交互联动
  - [x] 活动栏 6 入口点击切换左栏对应面板（Gradio 原生 tab 切换 + CSS，或 state 驱动显隐）
  - [x] 目标输入条：`＋` 按钮触发 PDF 上传入口（`gr.File`）；目标输入框 `gr.Textbox` 绑定目标
  - [x] 运行/继续运行合并：单按钮点击回调，首跑中断后返回 `gr.update(value="继续运行")` 切换按钮文字，再点击走 `resume_workflow`
  - [x] 保留 `run_workflow` / `resume_workflow` 14 元组输出契约，确保各视图组件正确订阅对应输出
  - [x] 验证：真实流程走查——运行→节点点亮→审查中断按钮变「继续运行」→提交后流程走完

- [x] Task 5: 测试更新 + 全量回归
  - [x] 更新 `tests/unit/frontend/test_decision_board.py`：`build_decision_board` 断言改为新组合视图（灯带/LLM 分析/目标输出），`_decision_source`/`build_status_bar`/`semantic_map_json` 断言保留
  - [x] 保留 `tests/unit/frontend/test_progress.py` 全部纯逻辑断言（`build_req_status_table`/`manifest_tree`/`summarize_state`/`stage_progress_view` 等）不回归
  - [x] 运行 `uv run pytest tests/unit/frontend/ -q` 全绿
  - [x] 运行 `uv run pytest tests/ -m "not integration" -q` 全量回归无回归

# Task Dependencies

- Task 2 依赖 Task 1（渲染函数需主题 CSS 类名约定）
- Task 3 依赖 Task 2（布局复用渲染函数）
- Task 4 依赖 Task 3（交互绑定到布局组件）
- Task 5 依赖 Task 2-4 全部完成

建议执行顺序：Task 1 → Task 2 → Task 3 → Task 4 → Task 5（全串行，共享 `app.py`）

# 共享文件冲突提示

- 全部任务均涉及 `src/rdi/frontend/app.py`，**禁止并行**，必须串行由同一实现链完成。
