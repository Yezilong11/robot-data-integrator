# 二轮测试总结 与 一轮复核报告

> 生成时间：2026-08-22T21:45:00+08:00
> 范围：问题集 122 题全量（一轮 63 + 二轮 59），5 位执行成员 A/C/D/E/F
> 依据：`records/*/record.json`、`records/_management/*`（progress.csv / quality_report.json / statistics_summary.md 已于 2026-08-22T21:31 由 `scripts/manage_test_records.py all` 重新对齐）

---

## 0. 一句话结论

二轮测试（59 新题）全部完成，全量 122 题可用率 59.0%；50 个 FAIL 中绝大多数为**可修复的系统性实现缺陷**（内容有效性把关缺失、语义错配、依赖未落盘、校验收口失守），非环境不可控。**但 P0 可用数据包 7/12 未达验收线（目标 ≥8），且全部 122 题实质复核仅 2 题，出口验收未通过。**

## 1. 全量统计总览（122 题）

| 指标 | 数值 |
|---|---:|
| 题目总数 / 已执行 | 122 / 122 |
| 已判定 / 已复核 | 122 / **2** |
| PASS / 降级通过(PWF) / FAIL | 16 / 56 / 50 |
| 通过率 / 降级率 / 失败率 | 13.1% / 45.9% / 41.0% |
| **可用率（PASS+PWF）** | **59.0%** |
| 记录平均完整率 | 97.3%（≥90% 达标） |
| 截图合规率 | **14.8%**（严重不足） |
| 校验 ERROR 数 | 414 |
| P0 可用数据包 | 7/12（目标 ≥8，**未达标**） |
| 失败原因 TOP3 | P2_RETRIEVE(20)、P3_SOURCE(10)、P4_FORMAT(10) |

分层表现（来源 `quality_report.json` dimensions）：
- **按源**：paperswithcode 100%（3/3）最优；mujoco 33.3%、google_scanned 37.5%、graspnet 42.9%、isaac 42.9% 垫底。
- **按需求类型**：paper 85.7%、sensor_data 75.0%、robot_urdf 62.9% 较好；sim_config 38.1%、mesh 37.5%、grasp 40.0% 是短板。
- **按语种**：EN 65.3% vs ZH 54.8%。

## 2. 二轮测试结果（59 新题）

| 成员 | 分配 | PASS | PWF | FAIL | 可用率 |
|---|---:|---:|---:|---:|---:|
| A | 12 | 0 | 1 | 11 | 8.3% |
| C | 12 | 1 | 7 | 4 | 66.7% |
| D | 12 | 0 | 4 | 8 | 33.3% |
| E | 12 | 0 | 7 | 5 | 58.3% |
| F | 11 | 2 | 2 | 7 | 36.4% |
| **合计** | **59** | **3** | **21** | **35** | **40.7%** |

- 提交完备：59/59 均有 record.json（F 的 11 题 8/22 补齐）。
- 与一轮对比：可用率 98.4%（Day6 口径）→ 40.7%，纯 PASS 仅 3/59。符合"二轮全量摸底、接受高 FAIL"预期，但暴露修复优先级需重整。
- 备注：A 报告 12 题含 P5_RUNTIME 空包（ss_code_github_001）；C 报告 66.7% 为本轮最高，主要差异在重试/源优先级执行度。E 报告另覆盖一轮遗留题 ms_004（FAIL P3_SOURCE）与 ms_007（PWF）。

## 3. 一轮复核状态（63 题）

本轮对一轮 63 题进行了复核核查，要点如下：

| 项目 | 现状 |
|---|---:|
| record.json 覆盖 | 63/63 |
| 当前判定分布 | PASS 13 / PWF 35 / **FAIL 15** |
| 当前可用率 | 76.2%（Day6 曾统计 98.4%，差异见下） |
| 实质复核记录（reviewer+reviewed_at） | **仅 2/63**（ms_007、ms_008，由 A 复核） |
| 带复跑证据（evidence_rerun.json） | 13 题（ss_github_004/005、ss_mujoco_002~005、ss_isaac_001/002、ss_ycb_002~005） |

**重要发现**
1. **一轮统计口径漂移**：Day6（8/20 00:46）统计"63 题全复核、FAIL 仅 1"，但 8/20 白天起一轮记录被复测覆盖（executed_at 更新为 8/20 15:00–17:30 及 8/21），复核标记丢失，且 15 题被判 FAIL。**统计文件已重新生成对齐到 record.json 实际状态。**
2. **一轮 15 个 FAIL**：ss_huggingface_002、ss_dexgrasp_001/003、ss_google_scanned_001/003、ss_mujoco_003/004、ss_ycb_001/002、ms_001/002/003/004/006/008（多为 P2_RETRIEVE、P6_VALIDATE、P3_SOURCE、P4）。其中 ms_004、ms_007 已在 E 二轮报告中被指出为修复未验证项。
3. **记录质量欠账**：C 报告指出的一轮校验错误（ss_ycb_001/002/003、ss_robotiq_002/003 等）经本次全量校验确认存在，且范围更大（414 ERROR 覆盖一轮+二轮，见 §5）。
4. **复核缺口关系**：当前 59 题二轮记录均为"待复核"，加之计划中"F 复核 A/D、A 复核 C/E/F"的设计，复核工作量仍集中待办。

## 4. FAIL 根因聚类（50 项归并）

| 聚类 | 覆盖 | 典型题 | 修复方向 |
|---|---|---|---|
| **降级占位/摘要冒充数据**（元数据或摘要当交付物） | ~11 | ms_012、ss_grasp_dexgrasp_002、ss_graspnet_003、ss_zenodo_007、ss_policy_hf_001、ss_sensor_github_002、ms_014、ss_dataset_graspnet_001、ss_grasp_ycb_001 | 内容有效性把关：文件大小/格式白名单、摘要拒收；retrieve 未真正下载必须 error + fallback_reason |
| **内容/语义错配**（目标资产不符） | ~9 | ss_isaac_003、ms_009、ss_mujoco_007/008、ss_mesh_ycb_008、ms_004、ss_google_scanned_005 | 适配器无目标资产时禁止固定返回默认资产；目标关键词语义校验前置 |
| **源级超时/未命中→空包**（P2_RETRIEVE） | ~20 | ms_001/002/003/006、ss_google_scanned_001/003、ss_ieee_004、ss_isaac_005、ss_ycb_001/002 | 1 轮即停转降级；源覆盖缺口评估；空包快速失败 |
| **URDF mesh 依赖缺失** | ~5 | ms_009、ss_kinova_001/003、ss_urdf_github_001、ms_011 | 解析 `<mesh filename>` 收集落盘；xacro 展开 |
| **github/HF markdown 摘要不可消费** | ~3 | ss_zenodo_006、ss_graspnet_005、ss_huggingface_006 | DatasetSkill 消费 markdown 或显式降级 |
| **单源题多解析 / LLM 无兜底** | ~2 | ss_graspnet_004、ss_code_github_001 | parse_goal 失败重试/熔断；字符串→数组归一化 |
| **横切：校验盲区**（validate 只查结构，FAIL 包仍 complete） | 横切 | 几乎全部 FAIL | 语义匹配与内容可用性校验纳入 re-validate |

## 5. 记录质量审计（`manage_test_records.py all`，414 ERROR）

主要 ERROR 类型（按数量排序）：
1. **截图不合规**：大量"每题至少 4 张截图""FAIL 必须包含报错截图"；部分截图文件缺失（ms_004、ms_007、ss_kinova_004、ss_arxiv_007、ss_mujoco_007、ss_policy_github_001、ss_sensor_zenodo_001 等）。截图合规率仅 14.8%。
2. **schema 字段取值非法**：`parse_goal.vs_expected`、`validate.runtime_check`、`package.status`、`package.file_count`——一轮旧记录与部分二轮新记录未按 1.0 schema 填写（如 ms_011、ss_mujoco_008 原将 dict 填入 runtime_check，已修正为 "not_run"）。
3. **检索字段缺失**："检索未成功时必须填写 error""降级必须填写 fallback_reason"（PWF/FAIL 记录大面积缺失）。
4. **枚举非法**：`req_type` / `source` / `quality` 出现题设外值（多解析/源偏移的直接证据）。
5. **PASS 判定与降级证据矛盾**：多条"存在降级时不能判 PASS""PASS_WITH_FALLBACK 必须有降级证据"。

> 说明：WARNING 类（package 路径在本机不存在、格式按纪要 §2.4 显式降级放行）不计入 ERROR，但数据包均在各执行机本地，出口前需人工复核数据包完整性。

## 6. 出口验收检查（Day6-8 口径）

| 检查项 | 结果 |
|---|---:|
| 问题集结构合法 | ✅ |
| 任务分配完整 | ✅ |
| 全部题目已执行 | ✅ |
| 记录完整率 ≥ 90% | ✅（97.3%） |
| P0 可用 ≥ 8/12 | ❌（7/12） |
| 全部记录已判定并复核 | ❌（复核 2/122） |
| 没有记录质量错误 | ❌（ERROR 414） |

## 7. 整改路线建议（按优先级）

1. **P0（阻断出口）**：补齐复核（122 题 reviewer/reviewed_at）；P0 的 5 个不可用题优先修复至 ≥8；截图合规整改（14.8%→100%）。
2. **P1（核心正确性）**：内容有效性把关（摘要/占位拒收）+ 适配器资产校验（禁默认错配，5 题）+ mesh 依赖收集落盘 + 超时 1 轮即降级。
3. **P2（一致性与口径）**：一轮 15 FAIL 处置（复测或挂账）；统一记录 schema（vs_expected/runtime_check/package 字段）；检索失败字段补齐（error/fallback_reason）。
4. **P3（工程化）**：单源多解析熔断、markdown 摘要消费、LLM 调用兜底。

## 8. 数据文件

- 判定/执行明细：`records/_management/progress.csv`（122 行，最新）
- 质量报告：`records/_management/quality_report.json`（2026-08-22T21:31）
- 统计摘要：`records/_management/statistics_summary.md`（2026-08-22T21:31）
- 逐题记录：`records/<case_id>/record.json`（122 个）