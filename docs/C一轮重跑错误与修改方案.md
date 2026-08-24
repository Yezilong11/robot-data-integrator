# C 角色一轮重跑：错误清单与修改方案

> 生成时间：2026-08-20
> 场景：按 `assignment_overview.md` 中为 C 分配的一轮 34 题，全部以真实流程（LLM 解析 → 真实 Adapter 检索 → Skill 处理 → 校验 → 打包）重跑，记录覆盖写入 `robot-data-integrator/records/<case_id>/record.json`（未截图）。
> 结论：34/34 记录齐全，全量检查 0 ERROR；判定分布 PASS 3 / PASS_WITH_FALLBACK 28 / FAIL 3。

---

## 1. 执行结果总览

| 项 | 值 |
|---|---|
| 重跑题数 | 34（C 一轮全量） |
| 记录落盘 | `robot-data-integrator/records/<case_id>/record.json`，34/34 齐全、无多余目录 |
| 判定分布 | PASS 3 / PASS_WITH_FALLBACK 28 / FAIL 3 |
| 全量检查（结构/字段/口径一致性） | 0 ERROR |
| 批量脚本 | `robot-data-integrator/scripts/rerun_c_round1.py` |
| 逐题进度 | `robot-data-integrator/records/_rerun_c_round1_progress.jsonl` |

PASS 3：`ss_github_001`（code）、`ss_zenodo_003`（dataset）、`ss_graspnet_001`（dataset）。
FAIL 3：`ss_huggingface_002`、`ss_dexgrasp_001`、`ss_dexgrasp_003`。

---

## 2. FAIL 类错误（记录已判 FAIL，需代码修复）

### 2.1 ss_dexgrasp_001 / ss_dexgrasp_003 —— 真实 `.npy` 抓取文件无法消费（P5_RUNTIME）

- **现象**：两轮重跑一致失败。检索成功（`source=dexgrasp`、真实 `.npy` 文件约 175KB 已下载），但 validate 报 1 个 error（“Grasp 数据缺少必要字段”），落包 0 文件，包状态 missing。
- **影响 case**：`ss_dexgrasp_001`（banana）、`ss_dexgrasp_003`（mug）。同类 `ss_dexgrasp_002/004/005`（apple/bottle/scissors）走 HF 元数据降级路径正常（PASS_WITH_FALLBACK）。
- **根因**：`robot-data-integrator/src/rdi/adapters/dexgrasp.py` 的 raw GitHub 兜底 `_find_dexgrasp_raw_file`（新增于一轮之后）成功下载 `PKU-EPIC/DexGraspNet` 官方 `data/dataset/` 下的单物体 `.npy` 抓取文件（如 `ddg-gd_banana_poisson_002.npy`），但下游 **GraspParseSkill 只能消费 `npz/pkl/json`，无 `.npy` 消费分支**（`robot-data-integrator/src/rdi/skills/grasp_parse.py`）。`.npy` 数据（手部关节 qpos + scale 结构）无法生成 `ParsedItem` → validate 判 error → 整题 FAIL。一轮时这两题走的是 HF 元数据降级（metadata JSON + is_fallback）→ PASS_WITH_FALLBACK，属流水线能力缺口而非数据缺失。
- **修改方案**（推荐 A，可选叠加 C）：
  - **方案 A（推荐，改动最小）**：GraspParseSkill 增加 `.npy` 消费分支 —— 用 `numpy.load` 读取 npy 数组，按 DexGraspNet 单物体 grasp 标注约定（205 个样本，每个含手部关节 qpos 与 scale）转换为 `CanonicalGrasp`（translations/rotations 或 grasps）结构，`data_source_quality=real`。需配套单元测试（`tests/unit/skills/test_grasp_parse.py`）。
  - **方案 C（兜底）**：`.npy` 下载后若 Skill 仍无法消费，Adapter 显式降级为 metadata JSON（`is_fallback=true` + `fallback_reason` 注明“真实 npy 已下载但格式不可消费”），保证包可用（恢复一轮 PASS_WITH_FALLBACK 形态）。
  - 组合建议：先 A，A 未覆盖的物体再走 C，避免静默降级与整题失败两个极端。

### 2.2 ss_huggingface_002 —— LLM 过度解析导致题设外需求拖垮整包（P2_RETRIEVE）

- **现象**：两轮重跑一致失败。“检索 ACT 机器人操作策略”被解析为 `robot_urdf + policy_model + dataset` 三条需求；题设外 `robot_urdf`（REQUIRED 优先级）命中 github 但返回 markdown 格式不属 robot_urdf 白名单 → missing → 整包 failed（`status=error`，落 2 文件）。核心需求 `policy_model` 实际成功（huggingface）。
- **影响 case**：`ss_huggingface_002`。
- **根因**：`robot-data-integrator/src/rdi/graph/nodes/parse_goal.py` 依赖 LLM 输出 + 关键词归一化；LLM 对“ACT 机器人操作策略”引申出“机器人模型/数据集”需求，且补充需求为 REQUIRED 优先级。校验节点 `validate.py` 对 REQUIRED 缺失记 error，装配 `_derive_package_status` 直接判 failed。
- **修改方案**（推荐 A + B）：
  - **方案 A（提示词约束）**：`build_goal_parsing_prompt`（`robot-data-integrator/src/rdi/intelligence/prompts/goal_parsing.py`）增加约束：目标明确为策略/权重/模型权重检索时，只生成 `policy_model` 核心需求，不得引申 robot_urdf/dataset。
  - **方案 B（优先级口径）**：题设外补充需求（`req_type ∉ expected`）的 `priority` 归一化为 RECOMMENDED/OPTIONAL，缺失时不触发整包 failed —— 与判定口径纪要 §7“补充需求不应成为阻塞项”一致。涉及 `parse_goal.py` 后处理与 `validate.py` 缺失判定。
  - 方案 C（记录侧）：判定口径上“核心需求命中即判可用，题设外失败记 WARNING”，需同步 `manage_test_records.py` 校验规则与口径纪要。

---

## 3. 环境/外部依赖类遗留（非记录错误，暂无需改代码）

### 3.1 IEEE 无 API Key（已知 blocked-by-user）

- **现象**：运行期 `UserWarning: IEEE API Key 未配置`；`ss_ieee_001` 兜底命中 arxiv，记录中显式标记 `is_fallback=true + fallback_reason`（源偏移），判 PASS_WITH_FALLBACK。
- **结论**：项目已确认 IEEE 为 blocked-by-user（外部依赖未提供 key），非代码范畴问题。当前兜底+显式降级路径行为正确，无需改动；后续提供 `IEEE_API_KEY` 后可恢复 IEEE 直接命中。

### 3.2 Embedding 服务偶发超时导致整题中断

- **现象**：运行期 2 次 `LLMUnavailableError: Embedding 调用失败: Request timed out. | model=text-embedding-v3`，发生在 retrieve 成功之后、记录生成之前，整题无输出（`ss_github_002`、`ss_zenodo_003` 各一次），重跑即恢复。
- **根因**：`robot-data-integrator/src/rdi/graph/nodes/retrieve_data.py` 的 `node_retrieve_single` 中 `hermes.record_experience(...)`（success 与 missing 两处调用点）**未包 try/except**；其内部 `ExperienceDB` 走 `get_embedding`（`hermes/experience_db.py`），embedding 超时直接把 `LLMUnavailableError` 冒泡到图外。对比：同文件的 `hermes.inject_experience` 已按 D3 口径做过 try/except 降级，`record_experience` 遗漏。
- **修改方案**：与 D3 的 `inject_experience` 一致，将两处 `hermes.record_experience(...)` 调用包进 `try/except Exception`（降级为不记录经验，不影响主链路）；或在 `HermesEngine.record_experience` 内部吞掉 embedding 异常。推荐前者（与现有降级模式一致）。需单测覆盖 embedding 超时路径。

---

## 4. 记录侧遗留（非错误，待确认处理）

| 项 | 说明 | 建议 |
|---|---|---|
| 孤儿截图目录 | 原 `records/ss_arxiv_001`、`ss_github_001`、`ss_huggingface_001` 下残留历史 `screenshots/`，新记录 `screenshots` 为空（按要求未截图） | 确认后可删除，或保留作历史备份 |
| 历史辅助文件 | `records/records.zip`、`c_case_observations_20260812.json`、`progress_c_cases_20260812.json`、`records/probe/` 本轮未动 | 如需归档可移入备份目录 |

---

## 5. 本轮已修复的记录映射问题（完成项，供追溯）

重跑过程中发现并修复的**记录生成层**问题（脚本 `rerun_c_round1.py`，不影响流水线代码）：

1. `retrieve[].format` 原取 manifest canonical 格式（`CodeRepoSummary`/`DatasetSummary`），改为取 `RawData` 原始格式（`markdown`/`json`/`npy` 等），与一轮口径一致。
2. `retrieve[].quality` 原透传 `data_source_quality`（多为 unknown），改为降级项记 `fallback`、非降级成功项记 `real`。
3. 核心需求命中非题设源（源偏移）时，显式置 `is_fallback=true` 并生成 `fallback_reason`（口径纪要 §7），消除“静默降级”。
4. `package.fallback_explicit` 合并检索级降级标记，与 retrieve 项一致。
5. 全量检查器仅对题设核心需求校验格式/质量，题设外补充需求按口径放行。

---

## 6. 修复优先级建议

| 优先级 | 项 | 说明 |
|---|---|---|
| P0 | 2.1 dexgrasp `.npy` 消费（方案 A+C） | 直接消除 2 个 FAIL，恢复真实数据可用性 |
| P0 | 3.2 embedding 超时降级 | 偶发但中断整题，修复成本极低 |
| P1 | 2.2 parse_goal 过度解析（方案 A+B） | 消除 1 个 FAIL；属 LLM 解析鲁棒性 |
| P2 | 4. 孤儿截图/历史文件清理 | 记录整洁性，无功能影响 |
