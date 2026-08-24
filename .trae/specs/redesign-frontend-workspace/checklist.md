# Checklist

## Task 1: 黑底橙调主题 CSS 注入
- [x] 黑底橙调主题 CSS 已注入（Gradio 6.0 通过 `launch(css=...)` 传入）
- [x] 配色变量与设计稿一致（背景 `#0d1117`/`#010409`、边框 `#30363d`、文字 `#e6edf3`、主色橙 `#f78166`）
- [x] 现有「LLM 生成 / 规则兜底」徽章语义迁移到橙色主题后仍可区分

## Task 2: 纯逻辑视图渲染函数
- [x] `render_file_tree_html` 输出 VSCode 风格树（缩进/类型图标/文件名）
- [x] `render_workflow_html` 输出灯带 5 节点（done/current/pending 状态类）
- [x] `render_llm_analysis_html` 输出思考文本 + 来源标注，且不含 confidence 数字
- [x] `render_target_output_html` 输出单行汇总 + 可展开文件清单
- [x] 检查器 4 tab 内容可用（详情由 `render_inspector_html` 生成，manifest/语义/LLM 调用由 Gradio 组件承载）
- [x] `tests/unit/frontend/test_views.py` 存在且通过

## Task 3: build_app 布局重构
- [x] 顶部状态条 + 活动栏（gr.Tabs 6 面板）+ 左栏 + 中栏 + 右栏检查器结构完整
- [x] 活动栏 6 入口顺序正确（设置位于日志下方，不沉底）
- [x] 中栏占比最大、左右侧栏较小（scale 比例 1:2:1）
- [x] 中栏含灯带 + LLM 分析主体 + 目标输出 + 底部目标输入条
- [x] 右栏检查器 4 tab 可用

## Task 4: 交互联动
- [x] 活动栏 6 入口点击可切换左栏对应面板（gr.Tabs 原生切换）
- [x] 「＋」按钮可展开 PDF 上传入口
- [x] 运行/继续运行合并为单按钮，中断后文字切换为「继续运行」，可继续
- [x] `run_workflow` / `resume_workflow` 14 元组输出契约未破坏

## Task 5: 测试更新 + 全量回归
- [x] `tests/unit/frontend/test_decision_board.py` 断言更新为新组合视图
- [x] `tests/unit/frontend/test_progress.py` 纯逻辑断言全部保留通过
- [x] `uv run pytest tests/unit/frontend/ -q` 全绿（37 passed）
- [x] `uv run pytest tests/unit -q` 全量回归无回归（766 passed, 1 skipped）
