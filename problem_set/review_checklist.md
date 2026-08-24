# 问题集 v1.0 评审清单

> 状态：已签收（通过）。F 已完成结构校验与代码枚举对齐，63 题结构校验全绿（0 ERROR），A 于 2026-08-12 签收。

## A 必查

- [x] 63 道题规模合适，55/8 的单源与多源比例获准。
- [x] 11 道 P0：`ss_arxiv_001`、`ss_github_001`、`ss_huggingface_001`、`ss_huggingface_002`、`ss_graspnet_002`、`ss_franka_001`、`ss_robotiq_001`、`ss_ycb_001`、`ss_mujoco_001`、`ms_001`、`ms_002`。
- [x] P0 验收口径确认为 PASS 与 PASS_WITH_FALLBACK 都算“可用数据包”，验收线 ≥ 2/3（≥ 8/11）。
- [x] `expected.format` 指最终记录中核验的实际文件格式，而不是只看文件扩展名文本。
- [x] 单源题若实际使用其他来源，必须显式标为 fallback；未标记则判 FAIL。
- [x] 多源题一次只保留一份正式记录；交叉复测用 notes 记录复测人，避免多人覆盖同一 `record.json`。

## 已发现的系统风险

1. 前端目前不能锁定指定 Adapter，单源题只能通过记录实际 `source` 来核验是否命中目标源。
2. `PAPER`、`CODE`、`DATASET` 当前没有对应的转换 Skill，可能检索成功但最终打包缺失。
3. `validate` 节点仍是骨架实现，当前固定返回 0 个问题，不能代替 D 的 URDF/Mesh/MJCF 手动可加载性验证。
4. `assemble` 节点仍生成占位 manifest 和占位输出目录，真实数据包完整性必须人工核验。
5. 前端把 review 决策作为运行前输入，尚未形成真正的 LangGraph interrupt/resume 交互。

## 签收

- 评审结论：`通过`
- A：A（组长）
- 日期：2026-08-12
- 裁定说明：63 题（55 单源 + 8 多源）结构校验 0 ERROR；11 道 P0、验收线 ≥8/11 确认；ms_007/ms_008 已恢复为多源端到端题（ms_007=ycb+graspnet+dexgrasp，ms_008=franka+mujoco+github）。5 项系统风险保留在 Day 执行期间持续跟踪。
