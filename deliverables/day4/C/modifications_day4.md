# Day4 C 修改文档（modifications_day4）

> 角色：C（数据工程师）｜日期：2026-08-15｜范围：仅 Day4 期间对项目与交付物的修改
> 对照依据：`Day4_执行收尾.md` C 章节两条任务

## 一、Day4 C 任务总览（对照 Day4_执行收尾.md）

| Day4_执行收尾.md C 任务 | 本日执行内容 | 状态 |
|---|---|---|
| 1. 完成数据源类全部单源题，补测遗漏源（如 IEEE 未配 Key 的降级记录） | 核对 C 33 题全覆盖（30 在 day3/C + 3 在 records 库）；IEEE 3 题豁免记录确认；探活补测 15 源（含 GRASP 专项） | ✅ 完成 |
| 2. 交叉多源题全部完成，汇总数据源可用性初稿（基于探活 + 执行观察） | ms_005 执行两轮（failed→complete）；产出数据源可用性初稿（15 源，探活 + 执行观察双证据） | ✅ 完成 |

## 二、代码修改（仅 1 处，最小改动）

### 2.1 parse_goal 重复需求去重（ms_005 包 failed 根因修复）

- **文件**：`src/rdi/graph/nodes/parse_goal.py`
- **内容**：新增 `_dedupe_requirements`（+27 行）——按 `(req_type, object_name)` 合并同一目标内完全等价需求（保留第一条），去重后重编号 req_id；在 node_parse_goal 的 object_name 填充后接入
- **动机**：ms_005 首轮 LLM 生成 ROBOT_URDF×2 + MESH，重复 ROBOT_URDF 检索命中 markdown → 类型错配缺失 → 整包 failed
- **影响面**：仅 LLM 输出含重复需求时生效；不同物体的同类型需求（banana/apple GRASP）仍保留，不丢信息
- **测试**：`tests/unit/graph/nodes/test_parse_goal.py`（+71，4 条去重测试 RED→GREEN）；`tests/unit/test_parse_goal.py`（+27，_make_result 支持多类型 + 适配 req_id 重编号测试）
- **验证**：全量测试 **762 passed / 0 failed**（此前 758 + 新增 4）

### 2.2 临时脚本（已删除，非交付物）

`_day4_ms005.py`（首轮执行）、`_day4_ms005_v2.py`（修复后重跑）、`_day4_check.py`（单源核对）、`_day4_observe.py`（执行观察聚合）、`_day4_backend_shots.py`（后端产物渲染截图）——跑完即删，未纳入交付。

## 三、执行工作与证据

### 3.1 ms_005 两轮执行（任务 2）

| 轮次 | 时间 | 包状态 | 需求 | 证据 |
|---|---|---|---|---|
| 首轮（修复前） | 15:22，154s | **failed**（missing=1：重复 ROBOT_URDF 类型错配） | 3（ROBOT_URDF×2+MESH） | `ms_005/evidence.json` |
| 重跑（修复后） | 15:58，57s | **complete**（missing=0） | 2（ROBOT_URDF+MESH） | `ms_005/evidence_v2.json` |

截图：中间态 4 + 最终态 4（前端）+ backend 4（后端实际产物：manifest / 目录结构 / URDF / STL）。

### 3.2 单源收尾核对（任务 1）

- C 33 题全覆盖：30 题（day3/C record）+ 3 题（records/ 共享库 ss_arxiv_001/ss_github_001/ss_huggingface_001）
- IEEE 3 题（ss_ieee_001/002/003）record notes 均含"无 API Key，豁免 blocked-by-user（P7_ENV），实际经 arxiv 兜底转 complete"
- 非 C 归属题（mujoco 5 / ycb mesh 3 / isaac 2）已在 day3/C 顺带执行，归口待 D/F 确认

### 3.3 探活补测（任务 2 输入）

- 重跑 `scripts/_probe_adapters.py`：15 源 construct/search 全 OK；fetch 14/15 OK（唯一 ieee 无 Key，P7_ENV）
- 与 08-12 基线对比：8 源 fetch 缺陷 + HF 404 已在 Day3 修复中解决
- GRASP 专项：dexgrasp 真实 npy；graspnet/ycb 元数据降级（显式可追溯）

## 四、交付物清单（deliverables/day4/C/）

```
deliverables/day4/C/
├── modifications_day4.md          # 本文件（修改文档）
├── data_source_availability.md    # 数据源可用性初稿（任务 2 核心产出）
├── run_summary_day4.md            # 运行问题与解决方案（P1-P4 + 裁定项）
└── ms_005/
    ├── record.json                # 权威执行记录（pkg=complete、PASS_WITH_FALLBACK）
    ├── evidence.json              # 首轮 failed 证据（修复前对照）
    ├── evidence_v2.json           # 修复后 complete 证据
    ├── diff_notes.md              # 与 A 首测 ms_001/002 差异记录
    └── screenshots/
        ├── intermediate/          # 中间态 4 张（前端）
        ├── final/                 # 最终态 4 张（前端）
        └── backend/               # 后端实际产物 4 张（manifest/目录/URDF/STL）
```

## 五、任务与产出对照表

| Day4_执行收尾.md C 任务 | 产出/证据 | 验收点 | 状态 |
|---|---|---|---|
| 1. 单源题完成 + IEEE 补测 | 33 题核对结果（三、3.2）、IEEE 豁免 notes、探活补测（三、3.3） | 全部有 record+截图；IEEE 降级显式可追溯 | ✅ |
| 2. 多源完成 + 可用性初稿 | ms_005（record+evidence_v2+diff_notes+截图）、data_source_availability.md | ms_005 pkg=complete；初稿覆盖 15 源双证据 | ✅ |
| 出口：全部 case 已执行（进度表全绿） | progress.csv 回写建议（P2，F 执行） | 提交 F 更新 | ⏳ 待 F |
| 出口：记录字段完整率 ≥90% | record.json 模板齐全（12 张截图清单） | 自查达标 | ✅ |
| 出口：截图规范达标 | 8 前端 + 4 后端截图，命名 NN_stage.png | 达标（FAIL 必截报错口径满足） | ✅ |

## 六、遗留与提交 A 项

1. **ms_005 题设源未直接命中**：franka/ycb 未进候选源（github/fuel 兜底，is_fallback），建议 A 核对候选源注入逻辑（非本轮改动范围）
2. **progress.csv 回写**：确认按 §run_summary_day4 P2 建议刷新（F 执行）
3. **graspnet/ycb 无真实 grasp 文件**：维持显式降级口径，建议 Day5+ 补本地数据集目录
