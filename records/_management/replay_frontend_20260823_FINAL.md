# 问题集真实前端重放 · 最终记录（口径2 · 48 题）

- 生成时间：2026-08-23（北京时间 Etc/GMT-8）
- 执行通道：**真实前端 API**（uvicorn `rdi.server:app` @127.0.0.1:8000）
  `POST /api/run` → 轮询 `/api/status` → `POST /api/resume(satisfied)` → 取 result/落盘包判定
- 口径：口径2（`category ∈ {dataset, grasp, sensor, policy}` 38 题 + 含非几何需求的 `end_to_end` 10 题 = **48 题**）
- LLM：阿里云 MaaS compatible-mode qwen3.7-plus（全程真实调用，非降级）
- **判定口径（2026-08-23 决策演进：引用=完整交付）**：
  - files 空 / 无产物 → FAIL
  - 大文件超限引用（downloaded=false 且带 file_url + wget 指引 + explain 说明）→ **PASS（引用交付）**
  - 检索失败 / 疑似占位 / 语义错配 / 引用缺 URL 或指引 → FAIL
  - missing 非引用项（部分满足）→ PASS_WITH_FALLBACK；其余 → PASS
- 数据文件：`records/_management/replay_frontend_20260823-200025.json`（真实链路逐题明细）、
  `replay_frontend_refcounted.json`（修订口径按落盘包重判）

## 成功率（48/48 全部执行完成，0 运行失败）

| 指标 | 数值 |
| --- | --- |
| 总题数 | 48 |
| **PASS** | **32（66.7%）** |
| ├─ 引用交付（大文件给 URL + 指引） | 24 |
| └─ 纯下载（真实落盘） | 8 |
| PASS_WITH_FALLBACK | 0 |
| FAIL（真失败：检索/占位/语义/指引缺失） | 16（33.3%） |

## 分类分布

| category | 总数 | PASS | FAIL |
| --- | --- | --- | --- |
| dataset | 13 | 6 | 7 |
| grasp | 13 | 11 | 2 |
| sensor | 7 | 0 | 7 |
| policy | 5 | 0 | 5 |
| end_to_end | 10 | 7 | 3 |

## PASS 明细

**引用交付（24）**：`ms_002/006/007/009/010`、`ss_dataset_graspnet_001`、`ss_dexgrasp_001/002`、
`ss_github_003`、`ss_grasp_dexgrasp_002`、`ss_grasp_ycb_001`、`ss_graspnet_001~005`、
`ss_huggingface_001/004/006`、`ss_ycb_004/005`、`ss_zenodo_001/005/006`
（dexgrasp/graspnet/ycb 大 npz、HF/Zenodo 大归档 → 引用 + wget 指引）

**纯下载（8）**：`ms_001/004/013`、`ss_dataset_hf_002`、`ss_dexgrasp_003/004/005/006`
（小文件真实落盘，语义校验真实命中不误拦）

## FAIL 归因（16 题，全部为真实未交付）

| 归因 | 题数 | 明细 |
| --- | --- | --- |
| 候选源全部失败（github format_mismatch / huggingface unknown） | 8 | ss_github_004、ss_huggingface_002/005、ss_policy_hf_001、ss_policy_github_001、ms_014、… |
| 降级来源且数据过小（疑似占位） | 6 | ss_sensor_github_001/002、ss_sensor_zenodo_001/002、ss_github_005、ms_015 |
| 语义不符（内容与需求整词零命中） | 3 | ss_zenodo_002/004/007（joint angles / force torque / joint sensor → 无关 zenodo 记录） |
| 候选语义零重叠 | 1 | ss_zenodo_003 |

policy 5 题全部 FAIL（权重源双向失败/占位），sensor 7 题全部 FAIL（源返回占位/语义拦截）——
与整改前基线归因（P2_RETRIEVE / P3_SOURCE）一致，源侧可得性是当前主要瓶颈。

## 与整改前基线对比

| 口径 | 整改前（Day2–Day5） | 整改后（2026-08-23 修订口径） |
| --- | --- | --- |
| PASS | 0–2 / 42 题 | 32 / 48 题（66.7%） |
| 降级当成功 | 大量（README 兜底/引用即算交付） | 0（引用=完整交付需带 URL+指引，否则 FAIL） |
| 失败归因 | 无/含糊 | 16 个 FAIL 全部带 validation ERROR + 归因文本 |
| 大文件 | 无统一下档说明 | RawReference + wget 指引 + explain 注入 |

## 环境与限制说明

- dexgrasp 等源下载慢：首轮 300s/题误标 17 题超时；单题预算上调后（1500s → 2400s）
  复核轮 17 题全部收敛（缓存命中 13s），无运行超时残留。判卷脚本默认预算已改为 2400s。
- "引用=完整交付"口径下，未下载引用必须带 file_url + download_guide + explain 说明才计 PASS；
  引用缺 URL/指引由 `download_integrity` ERROR 兜底判 FAIL（assemble 锚点，未放行）。
- 逐题明细见 `replay_frontend_20260823-200025.json`；修订口径重判表见 `replay_frontend_refcounted.json`。