# ms_005 差异记录（与 A 的 ms_001/002 对比）

> 角色：C｜执行时间：2026-08-15 15:58:12（去重修复后重跑，最终）｜输入：`Franka Panda stacks YCB blocks in PyBullet`

## 一、本 case 执行结果（最终）

| 维度 | 结果 |
|---|---|
| 解析需求 | ROBOT_URDF（req_000）、MESH（req_001）——**LLM 重复生成的第二个 ROBOT_URDF 已由 parse_goal 去重合并** |
| 落包产物 | `robots/req_000.urdf`（panda.urdf，github，is_fallback=true，completeness 80%）、`objects/req_001.stl`（fuel 块状物 mesh，is_fallback=true，completeness 100%） |
| 缺失项 | 无（missing=0） |
| 包状态 | `package-20260815-155903` **status=complete**（首轮 failed 见 evidence.json，修复后 complete 见 evidence_v2.json） |
| 判定 | **PASS_WITH_FALLBACK**（文件显式 is_fallback 标记，降级可追溯） |

## 二、与 A 首测 ms_001/002 的差异

| 对比项 | A 的 ms_001/002 | C 的 ms_005 |
|---|---|---|
| target | Franka Panda grasps YCB banana in MuJoCo / 中文表述 | Franka Panda stacks YCB blocks in PyBullet |
| 题设源 | franka;ycb;mujoco | franka;ycb |
| 期望需求 | robot_urdf;mesh;grasp;sim_config（4 类） | robot_urdf;mesh（2 类） |
| 实际解析 | 多需求组合 | ROBOT_URDF + MESH（2 需求，与题设一致） |
| 命中源 | —（A 首测） | github（URDF）+ fuel（mesh），题设源 franka/ycb 未直接命中 |

## 三、结论与建议

1. **重复需求问题已解决**：parse_goal 新增 `_dedupe_requirements`（按 req_type+object_name 合并完全等价需求），ms_005 首轮的"ROBOT_URDF ×2"已合并为 1 条，包状态由 failed 转 complete。
2. **LLM 随机性确认**：需求粒度受 LLM 随机性影响（首轮 3 需求含重复、本轮 2 需求），但去重兜底后结果与题设一致；最终结果以本轮为准。
3. **题设源未直接命中（保留观察）**：franka/ycb 源本地数据缺失，URDF 经 github 兜底、mesh 经 fuel 兜底（均 is_fallback）——显式降级达标；候选源注入逻辑仍建议 A 复核（非本轮目标）。
4. **残留差异**：本 case 比 ms_001/002 少 grasp/sim_config 需求（题设本就不同），不属异常。
