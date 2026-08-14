# Day 7｜F 复盘与改进建议初稿

## 已观察事实

1. 记录字段和截图整体完成度较高，但 reviewer 字段全部缺失，说明“执行完成”和“质量复核”没有形成闭环。
2. `ms_004` 将真实 mesh 超时与显式 grasp 降级同时呈现，失败分类为 `P2_RETRIEVE`，分类口径可追溯。
3. package 使用执行机绝对路径，跨机器复核不便，应优先改为仓库相对路径或 manifest 内的可复制证据。
4. 问题集规模曾出现旧文档口径，统计必须固定以 `problem_set.json` 为单一来源。

## 改进清单

| 优先级 | 改进项 | 指向 |
|---|---|---|
| P0 | 所有已判定记录补 reviewer/reviewed_at；补齐 P0 缺口 | records / 验收流程 |
| P1 | package 路径改为相对路径，增加跨机校验 | package/manifest |
| P1 | 将 P0 总数、目标和比例从问题集自动读取 | statistics tool |
| P2 | 在进度表加入“待复核原因”和“补测截止时间” | progress.csv |
| P2 | 将旧文档中的题目规模标注为历史口径 | docs |
