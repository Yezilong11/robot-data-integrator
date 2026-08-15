# Day4 C 运行问题与解决方案（run_summary_day4）

> 角色：C｜日期：2026-08-15｜说明：Day4 执行收尾（ms_005 执行 + 单源核对 + 数据源可用性初稿）过程中遇到的问题、根因、解决方案与提交 A 的裁定项

## 一、执行过程概述

按 `Day4-C执行收尾计划.md` 执行：ms_005 多源题（前端真实流程 + 中间态/最终态截图）→ 单源 33 题收尾核对 → IEEE 豁免确认 → 数据源可用性初稿（探活重跑 + 执行观察）。

**交付物**：`deliverables/day4/C/`（ms_005 record+截图+差异记录、data_source_availability.md、本文件）。代码改动仅 P1 的 parse_goal 去重修复（1 个函数 + 测试，全量测试 762 passed 无回归）。

## 二、遇到的问题与解决方案

### P1：ms_005 包状态 failed（LLM 重复生成 ROBOT_URDF → 类型错配缺失）【已修复】

**现象（首轮 15:22）**：`Franka Panda stacks YCB blocks in PyBullet` 运行完成（154s），但 `pkg=package-20260815-152522 status=failed`：落盘 2 文件（`robots/req_000.urdf` panda.urdf + `objects/req_001.stl`），缺失 1 项（req_002：robot_urdf 期望 CanonicalRobot，实际返回 markdown，类型错配）。

**根因**：LLM 对本目标解析出 **3 个需求（ROBOT_URDF ×2 + MESH）**——核心需求 ROBOT_URDF/MESH 均命中落包，但**同类型重复生成的第二个 ROBOT_URDF** 检索命中 markdown（源返回 README），类型错配写入 `missing_items`，整包被判 failed。

**修复（parse_goal 需求去重，最小改动）**：`src/rdi/graph/nodes/parse_goal.py` 新增 `_dedupe_requirements`——同一目标内按 `(req_type, object_name)` 合并完全等价需求（保留第一条），去重后重编号 req_id。仅合并"同类型 + 同物体"需求，不同物体的同类型需求（如 banana/apple 的 GRASP）仍各自保留，不丢失信息。影响面：仅 LLM 输出含重复需求时生效，正常 case 需求数不变。配套测试 4 条（RED→GREEN），全量测试 **762 passed（0 failed）** 无回归。

**修复后验证（15:58 重跑）**：`pkg=package-20260815-155903 status=complete`，`total_requirements=2, fulfilled=2, missing=0`（ROBOT_URDF + MESH），证据 `ms_005/evidence_v2.json`。verdict=PASS_WITH_FALLBACK（文件 is_fallback 显式标记，降级可追溯）。

### P2：progress.csv 与 Day3 实际执行脱节（31 行 C 题仍记"未执行"）

**现象**：`records/_management/progress.csv`（2026-08-14 快照）中 C 行 34 题仅 3 题"已判定"，31 题"未执行"；但 Day3-C 已实际执行 43 单元（FAIL=0）。

**根因**：Day3 交付物写于 `deliverables/day3/C/`，未回写共享进度表。

**解决方案**：本日同步建议（供 F 更新，C 不直接改 F 文件）：
- 30 题（day3/C 有 record）→ `已判定`，verdict 取 record，executed_at 取 record；
- ss_arxiv_001/ss_github_001/ss_huggingface_001（records/ 已有）→ `已判定`；
- ms_005 → `已判定/PASS_WITH_FALLBACK`（本轮执行）；
- 顺带执行的非 C 归属题（mujoco/ycb/isaac 共 10 题）→ 归口确认后由 D/F 处理。

### P3：探活 GRASP 专项发现 graspnet/ycb 仍无真实 grasp 文件

**现象**：GRASP 探活 graspnet 返回 json 元数据（567B）、ycb 返回 obj（1.4MB，非 grasp 格式），仅 dexgrasp 返回真实 npy（174KB）。

**根因**：graspnet tar 死路径（无法单文件获取）、ycb 无 grasp 标注数据，本地 `local_dataset_root` 未配置。

**解决方案**：维持显式降级口径（PASS_WITH_FALLBACK）；建议 Day5+ 补本地数据集目录（已列遗留问题）。

### P4：ms_005 题设源（franka/ycb）未直接命中

**现象**：ms_005 的 URDF 经 github 兜底、mesh 经 fuel 兜底，未命中题设源 franka/ycb；而探活显示 franka fetch OK（panda.urdf）。

**根因**：多需求场景候选源选择/优先级与单源探活场景不同，或 franka 源未进入 ms_005 的候选源列表（题设 sources 注入逻辑）。

**解决方案**：如实记录（is_fallback）；差异写入 ms_005/diff_notes.md，提交 A 核对候选源注入逻辑。

## 三、单源收尾核对结论

- C 33 题全覆盖：30 题（day3/C record）+ 3 题（records/ 共享库 ss_arxiv_001/ss_github_001/ss_huggingface_001）✅
- IEEE 3 题豁免记录确认：record notes 均含"无 API Key，豁免 blocked-by-user（P7_ENV），实际经 arxiv 兜底转 complete" ✅
- 非 C 归属题（mujoco 5 / ycb mesh 3 / isaac 2）已在 day3/C 顺带执行，归口待 D/F 确认，无重复执行 ✅

## 四、数据源可用性要点（详见 data_source_availability.md）

- 15 源 search 全 OK；fetch 14/15 OK（唯一 ieee 无 Key 阻塞）
- 8 源 fetch 缺陷 + HF 404 已在 Day3 修复中解决（探活对比见初稿 §一）
- 降级源：graspnet/ycb（GRASP 元数据）、isaac（最小 MJCF）、ieee（blocked）

## 五、提交 A 的裁定项

1. ~~**ms_005 重复需求缺口**~~ **已解决**：parse_goal 去重修复后包状态 complete（P1），无需裁定；如评审要求可复核去重策略（按 req_type+object_name 合并）。
2. **ms_005 题设源未命中**：franka/ycb 未进入候选源（github/fuel 兜底），核对候选源注入逻辑（非本轮改动范围）。
3. **progress.csv 回写**：确认 C 行按 §二 P2 建议刷新（F 执行）。

## 六、环境与工具

- 前端实例：`uv run python -m rdi.frontend.app`（127.0.0.1:7860）
- 浏览器：Playwright + Edge headless
- 探活：`uv run python scripts/_probe_adapters.py`（证据 `data/probe_adapters_results.json`）
- 临时脚本：`scripts/_day4_ms005.py`、`scripts/_day4_check.py`、`scripts/_day4_observe.py`（跑完即删）
