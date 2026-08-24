# Day 2 · F 质量核查与统计

> 最新口径已同步至 `records/_management/`，并对应更新到本目录。

## 快照结论

| 指标 | 结果 |
|---|---:|
| 问题集 | 63（单源 55，多源 8） |
| 已执行 / 已判定 / 已复核 | 63 / 63 / 63 |
| PASS / PASS_WITH_FALLBACK / FAIL | 14 / 48 / 1 |
| 可用率 | 98.4% |
| 记录完整率 | 100.0% |
| 截图合规率 | 100.0% |
| P0 可用数据包 | 11/11 |

## 重点变化

- `ms_008` 已完成真实执行并判定为 `FAIL / P2_RETRIEVE`，对应证据已落在 `records/ms_008/`。
- 全库统计已刷新到最新提交口径，`deliverables/day2/F/` 与 `records/_management/` 保持一致。
- 目前没有未闭环的统计错误；历史 `ms_004` 失败已在更早修订中处理为 `PASS_WITH_FALLBACK`。

## 交付口径

- 统计口径：以 `records/_management/progress.csv`、`quality_report.json`、`statistics_summary.md` 为准。
- 证据口径：真实截图与记录以 `records/<case_id>/` 为准，不使用生成图。
