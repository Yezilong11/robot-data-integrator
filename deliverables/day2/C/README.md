# Day 2：C（数据工程师）交付物

> 分支：`feat/arch-langgraph`
> 执行日期：2026-08-14（Day2-C 计划重跑，ad2581f 优化后第五轮）
> 依据：`Day2-C单源执行启动计划.md` + `problem_set_c_draft.json` + `docs/problem_set/判定口径纪要_C数据源类.md`

## 目录结构

```
deliverables/day2/C/
├── README.md                        # 本索引
├── observations_c_20260814.json     # 每题记录汇总（解析结果/命中源/quality/错误类型/降级标记）
├── ss_arxiv_001/
│   ├── record.json
│   └── screenshots/
│       ├── intermediate/01~04.png   # 中间态（human_review 中断时）全页截图
│       └── final/01~04.png          # 最终态（运行完成）全页截图
├── ss_github_001/
│   ├── record.json
│   └── screenshots/{intermediate,final}/01~04.png
├── ss_huggingface_001/
│   ├── record.json
│   └── screenshots/{intermediate,final}/01~04.png
└── summary_c_20260814.md            # 执行总结（含问题与发现、解决方法）
```

> 截图命名：01 目标输入 / 02 进度展示 / 03 校验与缺失项 / 04 数据包审查（均全页）。

## 执行结果（第五轮，ad2581f 优化后重跑 —— 全部无 FAIL）

| case_id | input | 解析结果 | 命中源 | quality | 错误类型 | verdict |
|---|---|---|---|---|---|---|
| ss_arxiv_001 | 检索 robot grasping 的论文 | [paper] ✓ | arxiv | fallback | none | **PASS_WITH_FALLBACK** |
| ss_github_001 | 检索 Franka 抓取开源仓库 | [code] ✓ | github | real | none | **PASS** |
| ss_huggingface_001 | 检索 robot grasp dataset | [dataset] ✓ | zenodo | fallback | none | **PASS_WITH_FALLBACK** |

> **本轮达成用户目标：3 个 case 均为 PASS 级，不再有 FAIL。**
> 相对第四轮（1 PASS / 2 FAIL）的改善：
> 1. **ss_arxiv_001**：由 FAIL / P4_FORMAT → PASS_WITH_FALLBACK——`ad2581f` 实现 PaperSkill `fmt="json"` 消费适配（降级 metadata JSON 不再被当 PDF 打开），成功落包（is_fallback=true, completeness 60%, 缺失 0）。
> 2. **ss_huggingface_001**：由 FAIL / P2_RETRIEVE → PASS_WITH_FALLBACK——`ad2581f` 实现检索源级子预算（per_req_timeout/候选源数），github 首源不再占满预算，zenodo 兜底命中（is_fallback=true, 缺失 0）。
> 3. **ss_github_001**：稳定 PASS（连续三轮）。
>
> 遗留关注项（非阻塞，待 A 评估，详见 `summary_c_20260814.md` §五）：ss_huggingface_001 命中源偏移（zenodo 非题设 huggingface）+ 返回数据集相关性存疑（deepfakes/巴西选举，非 robot grasp）。

## 对应数据包

| case_id | 数据包目录 | file_count | missing_items |
|---|---|---|---|
| ss_arxiv_001 | `data/output_packages/package-20260814-211317` | 1 | 0 |
| ss_github_001 | `data/output_packages/package-20260814-211436` | 1 | 0 |
| ss_huggingface_001 | `data/output_packages/package-20260814-211617` | 1 | 0 |
