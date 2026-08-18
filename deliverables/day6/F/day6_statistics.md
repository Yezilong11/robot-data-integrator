# Day 6｜F 汇总统计与交付收尾

> 统计来源：`problem_set/problem_set.json`、`records/`、`records/_management/quality_report.json`。
> 统计快照：2026-08-18 14:52 +08:00。

## 总体指标

| 指标 | 结果 |
|---|---:|
| 问题集总数 | 63 |
| 单源 / 多源 | 55 / 8 |
| 已执行 / 已判定 / 已复核 | 63 / 63 / 62 |
| PASS / PASS_WITH_FALLBACK / FAIL | 14 / 48 / 1 |
| PASS 率 / fallback 率 / FAIL 率 | 22.2% / 76.2% / 1.6% |
| 可用率 | 98.4% |
| 记录完整率 | 100.0% |
| 截图合规率 | 100.0% |
| P0 可用数据包 | 11/11（目标 8/11） |

## 失败归因与当前风险

| 分类 | 数量 | case | 结论 |
|---|---:|---|---|
| P7_ENV | 1 | `ms_008` | 真实前端流程缺少模型凭据，未进入目标解析或 human_review；已留错误截图，不作演示模式降级。 |

48 条 PASS_WITH_FALLBACK 均依赖显式 fallback 证据；全库仍有跨机器绝对 package 路径和格式降级 WARNING，当前不构成记录校验 ERROR，但应在后续版本改为可移植产物路径。

## 验收清单

- [x] 问题集与任务分配结构校验通过。
- [x] 全部 63 题已执行和判定。
- [x] P0 可用数据包达到目标。
- [x] 记录完整率和截图合规率达到 90% 以上。
- [x] 记录校验无 ERROR。
- [ ] A 复核 `ms_008` 后，才能通过“全部已判定记录均已复核”的严格验收。

## F 交接

A 只需核对 `records/ms_008/record.json` 与其 5 张截图，并填写 `reviewer`、`reviewed_at`；随后运行：

```text
.\.venv\Scripts\python.exe scripts/manage_test_records.py all --strict
```

若补齐 `OPENAI_API_KEY` 等模型凭据，应重新执行 `ms_008` 的真实流程，完成 run → interrupt → resume，再以新记录替换本次 P7_ENV FAIL。
