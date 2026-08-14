# Day 2｜F 质量核查与统计

## 快照结论

基于当前正式分支 `feat/arch-langgraph` 的 `problem_set/`、`records/` 和管理脚本，已完成当日记录校验与进度刷新。

| 指标 | 结果 |
|---|---:|
| 问题集 | 63（单源 55，多源 8） |
| 已执行 / 已判定 / 已复核 | 7 / 7 / 0 |
| PASS / PASS_WITH_FALLBACK / FAIL | 3 / 3 / 1 |
| 可用率（PASS + fallback） | 85.7% |
| 记录完整率 | 100.0% |
| 截图合规率 | 85.7% |
| P0 可用数据包 | 5/11，未达到 8/11 验收线 |

## 发现与交接

- `ms_004` 为 FAIL，分类码 `P2_RETRIEVE`；mesh 检索超时且 grasp 仅有显式元数据降级。
- 有 6 条记录尚未填写复核人和复核时间，`reviewed=0`，需 A 或指定复核人补齐。
- `ss_github_001`、`ss_mujoco_001`、`ss_ycb_001` 的 package 路径指向执行机绝对路径，已按工具规则降为 WARNING，后续应补可移植路径或 manifest 证据。
- 当前问题集 P0 共 11 题，不能套用旧口径的 8 题总数。

## 执行命令

```text
.\.venv\Scripts\python.exe scripts/manage_test_records.py all
```
