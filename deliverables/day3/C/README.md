# Day3 C 执行记录（数据源类 + 多源交叉）

> 角色：C（数据工程师）｜日期：2026-08-14｜执行方式：前端真实流程（Playwright 驱动 Gradio，全页截图）
> 依据：`Day3-C执行中段与多源交叉计划.md`（批 1 + 批 2 + 批 3 + ms_004 交叉）

## 一、执行总览

- 本轮执行 43 个执行单元（Day2 已执行 ss_arxiv_001/ss_github_001/ss_huggingface_001，见 `records/`）
- 每个 case 均产出 `record.json` + 8 张全页截图（中间态 4 张 + 最终态 4 张）
- 四维观测（parse_goal / retrieve / validate / package）写入各 `record.json`，汇总于 `_progress.jsonl`

## 二、Verdict 分布（43 题）

| verdict | 数量 | 说明 |
|---|---|---|
| PASS | 4 | 有产物且无缺失（ss_github_002 / ss_huggingface_002 / ss_ycb_005 / ms_004） |
| PASS_WITH_FALLBACK | 2 | 降级源成功（ss_mujoco_004 / ss_ycb_003） |
| P1_PARSE | 14 | LLM 解析目标与期望 req 不符（grasp/抓取歧义误判为主） |
| P2_RETRIEVE | 6 | 检索超时（dexgrasp 系 5 题 + huggingface_005） |
| P3_SOURCE | 5 | 数据源 fetch 失败（github_004 / graspnet_002 / ycb_001/002/004） |
| P4_FORMAT | 9 | PDF 打开/解析失败（arxiv 系 4 + paperswithcode 2 + ieee 3） |
| FAIL | 3 | mujoco_002/003/005（SIM_CONFIG 有产物但 ROBOT_URDF 类型错配） |

- 批 1（20 题）：arXiv 4 FAIL(P4_FORMAT)、GitHub 2 PASS + 2 FAIL、HF 1 PASS + 3 FAIL、Zenodo 5 FAIL(P1_PARSE)、PapersWithCode 3 FAIL
- 批 2（19 题）：YCB 3 FAIL + 1 FALLBACK + 1 PASS、DexGrasp 5 FAIL(P2_RETRIEVE)、MuJoCo 3 FAIL + 1 FALLBACK、GraspNet 2 FAIL、Isaac 2 FAIL(P1_PARSE)
- 批 3（3 题）：IEEE 全部 FAIL(P4_FORMAT，实际命中 arxiv fallback 后 PDF 打不开)
- 交叉（1 题）：ms_004 PASS（ROBOT_URDF 成功，MESH/GRASP 缺失）

## 三、关键观测

### 3.1 目标解析（parse_goal）

- **grasp/抓取 歧义误判（P1_PARSE 主因）**：`检索 YCB 抓取数据集`（期望 DATASET）被判为 GRASP；`检索 robot grasp dataset`（期望 DATASET）被判为 GRASP；`检索机械臂关节数据集`（期望 SENSOR_DATA）被判为 GRASP；`检索抓取策略权重仓库` 类同样受影响。LLM 对"抓取/grasp"关键词过度放大。
- `检索 mujoco_menagerie 中 franka 的真实场景`（期望 SIM_CONFIG）被判为 PAPER；`获取 Franka 的 Isaac Sim 场景配置`（期望 SIM_CONFIG）被判为 ROBOT_URDF。

### 3.2 数据检索（retrieve）

- **arxiv 系全部 P4_FORMAT**：检索命中真实论文（quality=real），但 fetch 后 PDF 无法打开（`无法打开 PDF: Failed to open stream`），文件数 0。
- **dexgrasp 系全部 P2_RETRIEVE**：检索超时（`超过 per_req_timeout 秒`），源为 graspnet。
- **mujoco_002/003/005 部分成功**：SIM_CONFIG 需求有产物（15/69/15 文件），但 LLM 额外解析出 ROBOT_URDF 需求导致类型错配 → 整体 FAIL。
- **ieee 系实际命中 arxiv**：无 IEEE Key 时 LLM 将源解析为 arxiv（fallback），随后 PDF 打不开 → P4_FORMAT（非预期 P7_ENV，如实记录实际行为）。

### 3.3 质量校验（validate）与打包（package）

- 有产物 case：github_002（19 文件）、huggingface_002（2 文件）、ycb_005（1 文件）、isaac_001（20 文件）等
- 无产物 case 统一记录 `status=failed / file_count=0 / missing_items=1`

## 四、目录结构

```
day3/C/
├── README.md                 # 本文件（执行汇总）
├── _progress.jsonl           # 43 题 verdict 汇总（case_id/verdict/vs/req/files/missing/error_type/elapsed）
├── rootcause_c_20260814.json # FAIL 根因汇总（指向具体 adapter）
├── run_summary_issues.md     # 运行问题与解决方案
└── <case_id>/                # 每题：
    ├── record.json           # 四维观测 + verdict + 截图清单
    └── screenshots/
        ├── intermediate/     # 01_parse_goal / 02_retrieve / 03_validate / 04_package
        └── final/            # 同上 4 张
```

## 五、出口标准对照

- [x] 单源题累计：Day2 3 题 + Day3 42 题 = 45 题全部有 record + 截图（C 侧 43 执行单元）
- [x] ms_004 交叉测试完成并有差异记录（与 A 首测对比见 `run_summary_issues.md`）
- [x] FAIL 根因初判汇总（`rootcause_c_20260814.json`）
- [x] 存疑 case 提交 A（见 `run_summary_issues.md` 待裁定清单）
