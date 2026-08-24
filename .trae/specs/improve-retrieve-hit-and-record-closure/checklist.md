# Checklist

## 检索候选预筛
- [x] 语义函数公共封装：`semantic_score` 暴露、`_semantic_mismatch` 内部改调且行为不变（validate 既有单测全绿）（spec: 检索候选语义预筛）
- [x] 预筛接入：GRASP/MESH/ROBOT_URDF/SIM_CONFIG + 术语非空时按命中得分选候选 fetch（spec: 多候选中存在语义匹配项）
- [x] 全候选零重叠保持原行为并加「候选语义零重叠」诊断（spec: 全候选零重叠保持不变）
- [x] 非启用类型/术语为空直取 search_results[0]，零开销（spec: 非启用类型/术语为空保持原行为）
- [x] 不改变 success/missing/error 判定边界，C4-pre is_format_allowed 位置不变

## FAIL error 回填
- [x] `backfill-errors` 子命令：结构化依据回填 + 无依据标记待人工（不虚构）（spec: FAIL error 自动回填）
- [x] 幂等：重复执行不覆盖既有 error；有回填/待人工计数输出；默认 dry-run、--apply 才写回

## 回归
- [x] `uv run pytest tests/ -q` 全量通过（871 passed, 1 skipped, 9 deselected；含新增用例，validate 既有用例不回归）
- [x] `manage_test_records.py all` 记录校验 ERROR 412 条均为既有类型，无本规格引入的新错误与副作用