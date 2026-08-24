# Tasks

> 依据 `spec.md`。执行顺序：先复用函数暴露（Task 1）→ 检索预筛（Task 2）→ 脚本回填（Task 4 与 Task 2 文件不冲突）。文件冲突组：`validate.py`（Task 1）、`retrieve_data.py`（Task 2/3）串行。

## 检索候选预筛

- [x] Task 1: validate.py 语义函数暴露为可复用公共函数
  - [x] 1.1 新增公共 `semantic_score(req, name, url, desc) -> int`（复用 _extract_semantic_terms/_term_in，拼装与 _item_identity_text 一致）；`_semantic_mismatch` 改调公共函数，行为不变（validate 既有单测全绿）
  - [x] 1.2 导出公共别名 `SEMANTIC_REQ_TYPES`（非下划线），无新依赖
  - [x] 1.3 同文件暴露，未移动实现、未新增模块

- [x] Task 2: retrieve_data.py 候选预筛接入（依赖 Task 1）
  - [x] 2.1 新增纯函数 `_pick_semantic_candidate(search_results, req_type, req)`：前 5 候选按 title/url/desc 用 semantic_score 打分
  - [x] 2.2 最高分 >0 选最优候选；全 0 → fetch search_results[0] 且向 search_failures 追加「候选语义零重叠」诊断
  - [x] 2.3 非启用类型/术语为空/非法 req_type 直取首个、无诊断；success/missing/error 判定与 C4-pre is_format_allowed 位置不变

- [x] Task 3: 预筛单测（`tests/unit/graph/test_retrieve_candidate_preselection.py`）
  - [x] 3.1 第 2 候选含 banana → fetch 选第 2 个
  - [x] 3.2 全候选零重叠 → 仍选索引 0 且诊断含「语义零重叠」
  - [x] 3.3 PAPER 类型与术语为空 → 选索引 0、无诊断（4 项用例全过）

## FAIL error 回填

- [x] Task 4: manage_test_records.py 新增 `backfill-errors` 子命令
  - [x] 4.1 对 verdict=FAIL 且 error 缺失的记录，按 retrieve 容器 error → items[*].error → error_message/message → result.error 顺序提取摘要，去重、截断 200 字符
  - [x] 4.2 无依据记录标记「需人工补正错误原因」WARNING，不写回
  - [x] 4.3 幂等（已有 error 跳过不覆盖）；默认 dry-run、`--apply` 才写回；输出回填/待人工计数；`--records` 可指向副本目录

- [x] Task 5: 回填命令验证
  - [x] 5.1 临时副本（ms_001 + ss_arxiv_007）：dry-run 不写盘；--apply 后 ms_001 回填原文、ss_arxiv_007 保持；二次 --apply 幂等
  - [x] 5.2 真实台账 dry-run：可回填 18 条、待人工 32 条，真实记录零改动

## 回归

- [x] Task 6: 全量回归与清单核对（依赖 Task 1-5）
  - [x] 6.1 `uv run pytest tests/ -q` 全量通过（871 passed, 1 skipped, 9 deselected；含新增 4 项预筛用例 + 既有 validate/retrieve 用例不回归）
  - [x] 6.2 复跑 `manage_test_records.py all`：记录校验 ERROR 412 条均为既有类型（截图/补正/降级证据等），无本规格新增错误；progress.csv/quality_report.json/statistics_summary.md 正常重生成

# Task Dependencies

- [Task 2] 依赖 [Task 1]
- [Task 3] 依赖 [Task 2]
- [Task 6] 依赖全部

# 并行执行建议

- Task 1 → Task 2/3（retrieve_data.py 与 manage_test_records.py 文件独立，Task 4/5 可与 Task 2 并行）
- Task 6 收口