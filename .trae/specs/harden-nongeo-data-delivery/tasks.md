# Tasks

## 阶段一：语义校验补牙齿（validate / parse_goal）

- [x] Task 1: 扩展语义校验类型白名单
  - [x] 1.1 `_SEMANTIC_REQ_TYPES` 加入 `DataReqType.DATASET / SENSOR_DATA / POLICY_MODEL`（validate.py）
  - [x] 1.2 单测：日食音频型错配 → content_validity ERROR；术语空跳过；几何四类零回归
- [x] Task 2: DataReq 增加 semantic_terms 字段
  - [x] 2.1 `DataReq.semantic_terms: list[str]`（goal.py）
  - [x] 2.2 确认 record/parse_goal 落盘序列化兼容（extra=forbid 则仅图内流转不落盘）
- [x] Task 3: parse_goal LLM 提炼 semantic_terms（形态 A）
  - [x] 3.1 目标解析 prompt（`build_goal_parsing_prompt`）要求输出 semantic_terms（从 description 提炼语义约束词）
  - [x] 3.2 LLM 调用流程落 semantic_terms（LLM 失败为空，fail-open）
  - [x] 3.3 `_extract_semantic_terms` 优先读 `req.semantic_terms`，空回退现有提取
  - [x] 3.4 单测：LLM 失败 fail-open；semantic_terms 优先级；无 semantic_terms 时零回归

## 阶段二：文件选择器 + 体积护栏 + 下载/引用（adapters / skills）

- [x] Task 4: 新增 select_target_file 组件
  - [x] 4.1 新建 `src/rdi/adapters/selectors.py`：`select_target_file(tree, req_type)`，扩展名白名单 + 名字信号优先级表（POLICY/SENSOR/DATASET/GRASP）
  - [x] 4.2 单测：四类型选择/排序/无候选返回空
- [x] Task 5: huggingface adapter 补 tree + 下载/引用
  - [x] 5.1 POLICY 分支接 HF tree API 列文件 → select_target_file 定位权重
  - [x] 5.2 复用 `_head_content_length` 预检：≤max_fetch_bytes 下载落盘；超限构造 RawReference
  - [x] 5.3 单测：tree→定位→（下载|引用）三分支
- [x] Task 6: zenodo adapter 补 files[] + 下载/引用
  - [x] 6.1 fetch 时从 record `files[]` 提取文件树 → select_target_file
  - [x] 6.2 预检 + 下载落盘 / RawReference
  - [x] 6.3 单测：files[]→（下载|引用）
- [x] Task 7: github adapter 补 contents 定位 + 下载/引用
  - [x] 7.1 通用分支 contents API 列文件 → select_target_file
  - [x] 7.2 预检 + 下载 / RawReference
  - [x] 7.3 单测：contents→（下载|引用）
- [x] Task 8: fallback 产物富文本指引
  - [x] 8.1 dataset/sensor/policy 三个 skill 的 _fallback_result 产物扩展为含 download_guide 结构（status/reason/file_url/file_size/method_hint/selected_by/alternatives）
  - [x] 8.2 单测：降级产物含 download_guide 字段

## 阶段三：指引交付 + 校验锚点（assemble / explain）

- [x] Task 9: explain 注入未下载项清单
  - [x] 9.1 `explain_quality` prompt 注入未下载项上下文（URL/体积/原因/wget 命令/目标路径）
  - [x] 9.2 规则兜底模板自动 append"获取指引"段（wget 命令恒在）
- [x] Task 10: assemble 完整性校验锚点
  - [x] 10.1 任一 downloaded=false 项必须存在 download_guide.json + explain 说明，缺则完整性 ERROR
  - [x] 10.2 单测：缺 download_guide → ERROR；完整 → 通过

## 阶段四：回归与台账

- [x] Task 11: 回归验证
  - [x] 11.1 `uv run pytest tests/ -q` 全绿（950 passed, 1 skipped, 9 deselected）
  - [x] 11.2 42 题离线验证：950 单测覆盖各环节 + validate-records 无本 spec 引入的回归；真实网络全量重放属人工扩展验收（仓库无离线 replay 命令）
  - [x] 11.3 日食音频案（ss_dataset_hf_002）专项复跑：带 semantic_terms 语义错配 → mismatch 非空被拦截；无术语 fail-open；非语义类型零回归；MESH 命中不误报
  - [x] 11.4 台账 backfill-errors dry-run 归因：50 FAIL 中 18 条可自动回填、32 条待人工补正（含 ss_dataset_hf_002）；--apply 写台账留人工验收
- [x] Task 12: 验收严口径台账判定（checklist 第 11 项缺口补充）
  - [x] 12.1 `manage_test_records.py` 记录校验增加规则：manifest 存在 downloaded=false 主文件项时 verdict 必须为 FAIL（PASS/PASS_WITH_FALLBACK 提示严口径违规），与 D9 一致性校验
  - [x] 12.2 单测：超限主文件 + verdict=PASS_WITH_FALLBACK → ERROR；verdict=FAIL → 通过

# Task Dependencies

- Task 2 依赖 Task 1（semantic_terms 字段先行，白名单校验才有术语来源）；Task 3 依赖 Task 2
- Task 5/6/7 相互独立，可并行；均依赖 Task 4（selectors）
- Task 8 依赖 Task 5/6/7（download_guide 数据来源于 adapter 引用信息）
- Task 9/10 依赖 Task 8；Task 11 依赖全部