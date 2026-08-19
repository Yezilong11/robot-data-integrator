# Robot Data Integrator 稳定性测试问题检查清单 v1.0

## 一、测试前环境检查

### 1. 项目目录检查

- [ ] 当前目录为 v3 或组长指定测试分支目录
- [ ] 目录中存在 `pyproject.toml`
- [ ] 目录中存在 `src/rdi/frontend/app.py`
- [ ] 已创建本地 `.env` 文件
- [ ] `.env` 未上传 GitHub

### 2. 依赖检查

- [ ] 已执行 `uv sync --extra dev`
- [ ] 依赖安装无报错
- [ ] Python 版本为 3.11 或以上
- [ ] 没有 `No module named xxx` 报错

### 3. API Key 检查

- [ ] `llm_model` 能正常输出，例如 `qwen-plus`
- [ ] `bool(settings.llm_api_key)` 输出 `True`
- [ ] `LLM_API_KEY` 已配置
- [ ] `LLM_BASE_URL` 已配置

### 4. 前端启动检查

- [ ] 前端能正常启动
- [ ] 浏览器能打开 `http://127.0.0.1:7860`
- [ ] 页面显示 `Robot Data Integrator`
- [ ] 页面包含：目标输入、进度展示、数据包审查、校验与缺失项
- [ ] 如果 7860 被占用，已关闭旧进程或切换端口

## 二、问题集检查

### 1. `problem_set.json` 结构检查

- [ ] 存在 `schema_version`
- [ ] 存在 `meta`
- [ ] 存在 `problems`
- [ ] 每道题都有 `case_id`
- [ ] 每道题都有 `layer`
- [ ] 每道题都有 `category`
- [ ] 每道题都有 `source`
- [ ] 每道题都有 `target`
- [ ] 每道题都有 `expected`
- [ ] 每道题都有 `priority`

### 2. `case_id` 检查

- [ ] 单源题格式为 `ss_<source>_<序号>`
- [ ] 多源题格式为 `ms_<序号>`
- [ ] 所有 `case_id` 不重复
- [ ] `case_id` 与 `records/<case_id>/` 能对应

### 3. 测试覆盖检查

- [ ] 覆盖 `paper` 论文类
- [ ] 覆盖 `code` 代码类
- [ ] 覆盖 `dataset` 数据集类
- [ ] 覆盖 `robot_urdf` 机器人模型类
- [ ] 覆盖 `mesh` 物体模型类
- [ ] 覆盖 `grasp` 抓取数据类
- [ ] 覆盖 `sim_config` 仿真配置类
- [ ] 覆盖 `policy` 策略模型类
- [ ] 覆盖 `sensor` 传感器数据类
- [ ] 覆盖 `end_to_end` 多源端到端类

## 三、每道题执行前检查

- [ ] 已确认 `case_id`
- [ ] 已复制对应 `target`
- [ ] 已确认是否需要上传 PDF
- [ ] 已确认是否需要本地文件注入
- [ ] 运行模式优先选择真实流程
- [ ] 已准备截图目录 `records/<case_id>/screenshots/`
- [ ] 已准备 `record.json`

## 四、目标输入页检查

### 1. 运行模式

- [ ] 稳定性测试选择真实流程
- [ ] 只测 UI 展示时才选择演示流程
- [ ] 已记录实际运行模式

### 2. 实验目标

- [ ] 已输入测试问题
- [ ] 输入内容与 `problem_set.json` 中 `target` 一致
- [ ] 如果临时修改措辞，已记录到 `record.json` 的 `input` 字段

### 3. PDF 上传

- [ ] 需要 PDF 的 case 已上传 PDF
- [ ] 页面显示 PDF 文件名
- [ ] PDF 文件不是快捷方式或损坏文件
- [ ] 上传 PDF 时，后续 `provenance` 中 `pdf bytes` 应大于 0
- [ ] 不需要 PDF 的 case 可允许 `pdf bytes` 为 0

### 4. 本地文件注入

- [ ] 普通 case 留空
- [ ] 需要本地文件时填写合法 JSON
- [ ] JSON 路径真实存在
- [ ] JSON 格式正确

## 五、进度展示页检查

### 1. `state_summary`

- [ ] 出现 `user_goal`
- [ ] 出现 `iteration_count`
- [ ] 出现 `data_requirements`
- [ ] 出现 `retrieval_errors` 或 `errors` 字段
- [ ] 如果 `state_summary` 为空，记录为异常

### 2. 数据需求状态

- [ ] 表格显示 `req_id`
- [ ] 表格显示 `req_type`
- [ ] 表格显示状态
- [ ] 表格显示数据源
- [ ] 表格显示是否 `fallback`
- [ ] 表格显示失败原因
- [ ] 如果阶段完成但数据需求为空，需要记录为展示不一致或解析异常

### 3. `provenance`

- [ ] 有目标接收记录（如 `received user goal`，以实际输出文本为准）
- [ ] 有 PDF 读取记录（如 `read pdf bytes`，以实际输出文本为准）
- [ ] 有 `parse` / `retrieve` / `validate` / `package` 等流程记录
- [ ] 真实流程不应只出现 `demo package assembled by frontend`
- [ ] 后端失败时应有明确错误信息

### 4. 阶段进度

- [ ] 目标解析阶段有状态
- [ ] 数据检索阶段有状态
- [ ] 解析转换阶段有状态
- [ ] 质量校验阶段有状态
- [ ] 整合打包阶段有状态
- [ ] 如果阶段卡住或失败，需截图记录

## 六、数据包审查页检查

### 1. 数据包目录

- [ ] 生成 package 目录
- [ ] 包含 `manifest.json`
- [ ] 包含 `provenance.log`
- [ ] 包含 `files/` 目录
- [ ] 包含相关数据文件
- [ ] 降级以 manifest 中 `is_fallback=true` / `data_source_quality` 为准（系统不生成 `fallback-package` 目录，目录一律为 `package-*`）

### 2. `manifest`

- [ ] 包含 `package_id`
- [ ] 包含 `goal`
- [ ] 包含 `created_at`
- [ ] 包含 `files`
- [ ] 包含 `missing_items`
- [ ] 包含 `data_source_quality` 或等价来源质量字段
- [ ] 文件数量达到 `expected.min_files`
- [ ] 文件格式符合 `expected.format`
- [ ] 数据来源质量符合 `expected.quality`
- [ ] 没有静默 fallback

## 七、校验与缺失项页检查

### 1. `validation_issues`

- [ ] 能正常显示
- [ ] 无 error 时可考虑 `PASS`
- [ ] 有 warning 但包可用时可考虑 `PASS_WITH_FALLBACK`
- [ ] 有 error 且包不可用时判定 `FAIL`

### 2. `runtime_check`

- [ ] 涉及仿真或机器人资源时检查是否执行
- [ ] URDF / Mesh / MJCF 加载失败需记录
- [ ] 不涉及运行时验证时可为空，并在备注中说明

### 3. `missing_items`

- [ ] 缺失项有 `req_id`
- [ ] 缺失项有 `req_type`
- [ ] 缺失项有 `description`
- [ ] 缺失项有 `reason`
- [ ] 有缺失但 fallback 明确时，优先判定 `PASS_WITH_FALLBACK`
- [ ] 有缺失但无说明时，可能判定 `FAIL`

## 八、human_review 检查

- [ ] 如果流程中断，页面有人工审查提示
- [ ] 能选择 `satisfied` / `revised` / `unsatisfied`
- [ ] `revised` 或 `unsatisfied` 时已填写反馈
- [ ] 点击继续运行后页面有更新
- [ ] resume 失败记录为 `P6_FRONTEND`

## 九、截图检查

每个 case 至少保存以下截图：

- [ ] `01_input.png`：目标输入页，包含输入问题
- [ ] `02_progress.png`：进度展示页，包含 `state_summary` / `provenance`
- [ ] `03_package.png`：数据包审查页，包含目录和 `manifest`
- [ ] `04_validation.png`：校验与缺失项页

失败 case 额外保存：

- [ ] `05_error.png`：页面错误信息
- [ ] `terminal_error.png`：终端报错信息

截图要求：

- [ ] 能看清输入问题
- [ ] 能看清运行状态
- [ ] 能看清错误原因
- [ ] 能看清数据包路径
- [ ] 截图放入 `records/<case_id>/screenshots/`

## 十、`record.json` 检查

- [ ] 包含 `schema_version`
- [ ] 包含 `case_id`
- [ ] 包含 `input`
- [ ] 包含 `executor`
- [ ] 包含 `executed_at`
- [ ] 包含 `env`
- [ ] 包含 `observations`
- [ ] 包含 `screenshots`
- [ ] 包含 `verdict`
- [ ] 包含 `failure_category`
- [ ] 包含 `failure_reason`
- [ ] 包含 `notes`

### 1. `env` 字段应记录

- [ ] `llm_model`
- [ ] `llm_base_url`
- [ ] `mode`
- [ ] `review_decision`

### 2. `observations` 字段应记录

- [ ] `parse_goal`
- [ ] `retrieve`
- [ ] `validate`
- [ ] `package`

### 3. `verdict` 只能填写

- [ ] `PASS`
- [ ] `PASS_WITH_FALLBACK`
- [ ] `FAIL`

### 4. 失败分类只能填写

- [ ] `P1_PARSE`：目标解析失败
- [ ] `P2_RETRIEVE`：检索失败
- [ ] `P3_SOURCE`：数据源不可用
- [ ] `P4_FORMAT`：格式不兼容
- [ ] `P5_RUNTIME`：运行时验证失败
- [ ] `P6_FRONTEND`：前端或流程问题
- [ ] `P7_ENV`：环境问题
- [ ] `P8_OTHER`：其他问题

## 十一、结果判定标准

### 1. `PASS`

- [ ] 数据包生成成功
- [ ] 无 ERROR
- [ ] 文件数量达到要求
- [ ] 文件格式符合预期
- [ ] 数据来源真实或符合 expected
- [ ] `manifest` 记录完整
- [ ] 页面展示正常

### 2. `PASS_WITH_FALLBACK`

- [ ] 数据包可用
- [ ] 存在降级（manifest `is_fallback=true`）或 `missing_items`
- [ ] 降级有显式标记（可追溯）
- [ ] `manifest` 中能追溯原因
- [ ] 页面没有崩溃

### 3. `FAIL`

- [ ] 无数据包
- [ ] 页面崩溃
- [ ] 按钮无响应
- [ ] 后端报错但前端无展示
- [ ] 数据包内容明显错误
- [ ] 文件无法加载
- [ ] 存在静默 fallback
- [ ] 缺少必要记录

## 十二、常见问题处理

### 1. 端口占用

现象：

```text
Cannot find empty port in range: 7860-7860
```

处理：

- 关闭旧终端
- 或切换到 7861 端口

### 2. 依赖缺失

现象：

```text
No module named xxx
```

处理：

- 重新执行依赖安装
- 必要时安装 runtime 依赖

### 3. PDF bytes 为 0

处理：

- 重新上传 PDF
- 确认显示文件名
- 换正常 PDF 复测
- 多次复现记为 `P6_FRONTEND`

### 4. 页面卡住

处理：

- 等待 1-3 分钟
- 查看终端
- 刷新页面
- 重启前端
- 换简单问题复测
- 仍卡住记为 `P6_FRONTEND`

### 5. 后端失败

处理：

- 检查页面是否显示 `errors`
- 检查是否显示 `validation_issues`
- 检查 manifest 是否 `is_fallback=true`
- 前端无提示则记为 `P6_FRONTEND`
- 环境或认证问题记为 `P7_ENV`

## 十三、每日汇总检查

- [ ] 今日执行 case 数
- [ ] `PASS` 数
- [ ] `PASS_WITH_FALLBACK` 数
- [ ] `FAIL` 数
- [ ] `P6_FRONTEND` 数
- [ ] `P7_ENV` 数
- [ ] 最常见失败原因
- [ ] 是否有截图缺失
- [ ] 是否有 `record.json` 缺失
- [ ] 是否有无法复现的问题

每日汇报模板：

```text
今日完成 X 条 case 测试。
PASS：X 条。
PASS_WITH_FALLBACK：X 条。
FAIL：X 条。

主要问题：
1. XXX
2. XXX
3. XXX

E 端观察：
前端启动是否稳定：XXX
真实流程展示是否稳定：XXX
数据包展示是否稳定：XXX
错误兜底是否稳定：XXX
截图与记录是否完整：XXX
```

## 十四、最终交付检查

- [ ] `problem_set/problem_set.json` 存在
- [ ] `records/<case_id>/record.json` 存在
- [ ] 每个 case 都有 screenshots
- [ ] JSON 格式合法
- [ ] `case_id` 对应一致
- [ ] 判定字段完整
- [ ] 失败原因分类完整
- [ ] 截图可读
- [ ] A/F 可以基于 records 做统计
