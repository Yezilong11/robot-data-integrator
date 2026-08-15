# Day3 C 执行记录（数据源类 + 多源交叉）—— 项目优化后重跑

> 角色：C（数据工程师）｜日期：2026-08-15｜执行方式：前端真实流程（Playwright 驱动 Gradio，全页截图）
> 依据：`Day3-C执行中段与多源交叉计划.md`（批 1 + 批 2 + 批 3 + ms_004 交叉）
> 前置：项目已按 ad2581f 优化（arxiv fmt=json 降级消费适配 + 检索源级子预算），Day2-C 已 1 PASS / 2 PASS_WITH_FALLBACK

## 一、执行总览

- 本轮执行 43 个执行单元（批 1 二十题 + 批 2 十九题 + 批 3 三题 + ms_004 交叉），全部产出 `record.json` + 8 张全页截图（中间态 4 + 最终态 4）
- 四维观测（parse_goal / retrieve / validate / package）写入各 `record.json`，汇总于 `_progress.jsonl`
- **执行过程问题**：执行中 dashscope 免费额度耗尽（LLM 403）导致批 2 后半程 19 题首次运行解析出 0 需求；用户提供新 key 后已补跑全部 19 题（详见 `run_summary_issues.md` §二 P1）

## 二、Verdict 分布（43 题）

| verdict | 数量 | 说明 |
|---|---|---|
| PASS | 5 | ss_github_004 / ss_github_005 / ss_huggingface_003 / ss_graspnet_001 / ss_ycb_005 |
| PASS_WITH_FALLBACK | 16 | 降级源成功（arxiv 系 4、pwc 2、zenodo 系 3、github_003、huggingface_004、ycb_003、mujoco 003/004/005、isaac_001） |
| FAIL / P3_SOURCE | 12 | 数据源 fetch 失败（dexgrasp 系 5、ycb 001/002/004、graspnet_002、huggingface_002/005、ms_004） |
| FAIL / P2_RETRIEVE | 4 | 检索全源失败（paperswithcode_002、ieee 001/002/003） |
| FAIL / P4_FORMAT | 6 | 类型错配/格式解析失败（github_002、zenodo_002/004、mujoco_001/002、isaac_002） |

- 批 1（20 题）：**PASS/PASS_WITH_FALLBACK 13 题，FAIL 7 题**（较优化前批 1 仅 3 题 PASS 级大幅改善）
- 批 2（19 题）：PASS 2 / PASS_WITH_FALLBACK 5 / FAIL 12
- 批 3（3 题）：IEEE 全部 FAIL / P2_RETRIEVE（arxiv/pwc 检索超时 + ieee 无 key，非预期 P7_ENV，如实记录）
- 交叉（1 题）：ms_004 FAIL / P3_SOURCE（ROBOT_URDF 成功落包，MESH/GRASP 缺失）

## 三、关键观测

### 3.1 目标解析（parse_goal）—— 优化大幅生效

- **grasp/抓取 歧义误判基本消除**：前轮 14 题 P1_PARSE（grasp 过度放大）本轮全部消失；`检索 YCB 抓取数据集`→DATASET、`检索机械臂关节数据集`→SENSOR_DATA、`检索 robot grasp dataset`→DATASET 均正确。
- 剩余 vs=mismatch/partial 集中在**多需求场景**：github_002（ROBOT_URDF+CODE）、mujoco_001/002、isaac_002（多解析 ROBOT_URDF/SIM_CONFIG/CODE）——LLM 对"仿真/场景/URDF"类目标仍倾向补出 ROBOT_URDF 需求。

### 3.2 数据检索（retrieve）—— 优化生效

- **arxiv 系 4 题 + pwc 2 题全部转为 PASS_WITH_FALLBACK**：PDF 超阈值 → fetch 显式降级 metadata JSON → PaperSkill `fmt=json` 消费适配成功落包（is_fallback=true, completeness 60%, 缺失 0）。**P4_FORMAT 高频根因消除**。
- **dexgrasp/ycb/graspnet 系仍 FAIL/P3_SOURCE**：GraspNet/YCB 源返回元数据 JSON（未找到真实 npz）——源侧 fetch 阻塞仍在（属 8 源 fetch 缺陷范畴）。
- **mujoco_003/004/005 改善为 PASS_WITH_FALLBACK**：SIM_CONFIG 正确解析且 mujoco_menagerie 命中（70/1/70 文件），仅 mujoco_001/002 因多解析 ROBOT_URDF 类型错配 FAIL。
- **ieee 系行为变化**：本轮 arxiv 检索超时（非 PDF 打开失败）→ P2_RETRIEVE；ieee 无 key 记 unknown。

### 3.3 质量校验（validate）与打包（package）

- 有产物 case：mujoco_003/005（70 文件）、mujoco_002（15 文件）、isaac_002（1 文件）、ms_004（1 URDF）、arxiv/pwc/zenodo 系（1 文件）等
- 无产物 case：P3_SOURCE/P2_RETRIEVE 类统一 `status=failed / file_count=0 / missing_items=1`

## 四、目录结构

```
day3/C/
├── README.md                 # 本文件（执行汇总）
├── _progress.jsonl           # 43 题 verdict 汇总（case_id/verdict/vs/req/files/missing/error_type）
├── rootcause_c_20260814.json # FAIL 根因汇总（指向具体 adapter/节点）
├── run_summary_issues.md     # 运行问题与解决方案（含 LLM 403 事件）
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
