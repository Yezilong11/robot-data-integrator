# 问题集维护说明

`problem_set.json` 是唯一的问题集载体。当前版本包含 63 道题：55 道单源、8 道多源，单源占比 87.3%（策略要求单源主导，≥ 70%）；P0 共 11 道，验收线为“P0 可用数据包 ≥ 2/3（≥ 8/11）”。

## 修改规则

1. 题目增删或期望调整后，先运行 `uv run python scripts/manage_test_records.py validate-problems`。
2. `case_id` 不得复用；已产生记录的 case 不得直接改题意，应新增 case。
3. `source` 和 `expected.req_types` 使用代码枚举的实际值，均为小写。
4. A 完成评审后，在 `review_checklist.md` 填写签收信息。
5. 题目变更后运行 `uv run python scripts/manage_test_records.py all`，同步进度表和统计文件。

当前代码实际包含 15 个 `DataSource`，问题集已全部覆盖。README 中“16 种数据源”的表述是过时计数。
