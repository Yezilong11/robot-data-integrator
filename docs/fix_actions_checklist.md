# 二轮测试修复行动清单（Fix Actions Checklist）

> 生成：2026-08-22 | 依据：`.trae/documents/二轮测试问题修复计划.md`（P0/P1/P2）、`records/_management/*` 统计
> 状态口径：progress.csv（含 round 列，round=1 63 题 / round=2 59 题，共 122 题）
> 本条清单为**成员管理动作**（P2-C），代码修复（P0/P1/P2-A/B）已落地并配套单测，见 `fix-round2-test-issues` 规格。

---

## 1. 截图缺失清单（合规 14.8% → 100%，按成员分派补交）

合规口径（与 `manage_test_records.py` 一致）：record.json `screenshots` ≥ 4 条；FAIL 记录还必须含报错截图。当前 122 题中仅 18 题合规（14.8%）。

| 成员 | 承担题数 | 合规 | 缺失 | 其中 0 张 |
|---|---:|---:|---:|---|
| A | 15 | 1 | 14 | 3 |
| C | 46 | 12 | 34 | 34 |
| D | 35 | 0 | 35 | 35 |
| E | 14 | 4 | 10 | 0 |
| F | 12 | 1 | 11 | 0 |
| **合计** | **122** | **18** | **104** | **72** |

**补交要求**：每题按模板补足 4 张（input/progress/package/validation，FAIL 另加报错截图），登记回 record.json `screenshots` 后由复核人核销。

### A 需补（14）：ms_001、ms_002、ms_006、ss_kinova_001、ss_allegro_005、ss_graspnet_003、ss_mujoco_009、ss_google_scanned_004、ss_github_006、ss_zenodo_007、ss_code_github_001、ss_grasp_dexgrasp_002、ss_urdf_github_001、ms_012
- 其中 0 张（全缺）：ms_001、ms_002、ms_006

### C 需补（34）：ss_arxiv_001~005、ss_github_001~005、ss_huggingface_001~005、ss_zenodo_001~005、ss_paperswithcode_001~003、ss_ieee_001、ss_dexgrasp_001~005、ss_graspnet_001~002、ss_ycb_004、ss_ycb_005、ms_005
- 全部为 0 张（全缺）

### D 需补（35）：ss_franka_001~003、ss_robotiq_001~003、ss_allegro_001~003、ss_google_scanned_001~003、ss_mujoco_001~005、ss_isaac_001~002、ss_ycb_001~003、ms_003、ss_kinova_003、ss_isaac_003、ss_mujoco_006、ss_ieee_002、ss_google_scanned_006、ss_arxiv_006、ss_dexgrasp_006、ss_sensor_github_002、ss_policy_hf_001、ss_mesh_ycb_008、ms_009、ms_014
- 全部为 0 张（全缺）

### E 需补（10）：ms_004、ss_kinova_004、ss_isaac_004、ss_ieee_003、ss_franka_004、ss_arxiv_007、ss_ycb_006、ss_dataset_hf_002、ms_010、ms_015

### F 需补（11）：ss_allegro_004、ss_isaac_005、ss_mujoco_008、ss_ieee_004、ss_franka_005、ss_huggingface_006、ss_ycb_007、ss_sensor_zenodo_002、ss_grasp_ycb_001、ss_dataset_graspnet_001、ms_011

## 2. 一轮补正清单（既有记录错误，分派 D 补正并复核）

round=1 中除截图外的记录内容错误（`quality_report.json` 非截图类 ERROR），需按题补正 record.json 后在复核环节核销。列表以目标成员分组：

| 成员 | 需补正题（问题摘要） |
|---|---|
| D | ss_ycb_001 / ss_ycb_002（quality 非法、status 非法、package.status 非法、vs_expected/runtime_check 取值非法） |
| D | ss_robotiq_001~003（vs_expected='exact'、quality unknown、runtime_check='not_required'、可用判定/可加载性缺失） |
| D | ss_franka_001~003、ss_allegro_001~003（同上 vs_expected/runtime_check/可加载性问题） |
| D | ss_mujoco_001~005（vs_expected='exact' 等；ss_mujoco_003/004 另缺 FAIL 分类） |
| D | ss_google_scanned_001~003（vs_expected/runtime_check/package.status 非法） |
| D | ss_isaac_001~002（vs_expected='exact' / 可用判定） |
| D | ms_003（source 非法、package.status 非法） |
| E | ms_004（quality unknown、缺 fallback_reason、format CanonicalGrasp 未降级标记） |
| C | ss_huggingface_002（出现非预期 req_type: robot_urdf） |

> 注：Plan 原列“ss_robotiq_002/003”纳入上表 D 组；其问题为 vs_expected/quality/runtime_check 取值非法，与 ss_robotiq_001 同构。

## 3. 一轮 15 个 FAIL 处置表

round=1 共 63 题、15 FAIL。按“先回归、后挂账”处置：

| 题 | 成员 | 分类 | 处置 |
|---|---|---|---|
| ss_huggingface_002 | C | P2_RETRIEVE | **回归优先**：P1-B 解析 / P1-A 路由修复后重跑 |
| ss_ycb_001 | D | P2_RETRIEVE | 回归（补正后按 P0 补位路径重跑） |
| ss_ycb_002 | D | P2_RETRIEVE | 回归 |
| ms_001 | A | P2_RETRIEVE | 回归（P0 补位候选①） |
| ms_002 | A | P2_RETRIEVE | 回归（P0 补位候选②） |
| ms_003 | D | P2_RETRIEVE | 回归 + 补正记录（source/package.status） |
| ms_004 | E | P3_SOURCE | 回归 + 补正记录（降级证据） |
| ms_006 | A | P2_RETRIEVE | 回归 |
| ms_008 | F | P2_RETRIEVE | 回归（P2-B 台账核查后复核） |
| ss_dexgrasp_001 | C | P6_VALIDATE | 回归（P0-A 内容校验后判定） |
| ss_dexgrasp_003 | C | P6_VALIDATE | 回归（P0-A 内容校验后判定） |
| ss_google_scanned_001 | D | P2_RETRIEVE | 回归（P0-C 资产缺失显性化后判定） |
| ss_google_scanned_003 | D | P2_RETRIEVE | 回归（超时/降级路径验证） |
| ss_mujoco_003 | D | P4 | 回归（缺失分类填 P4_FORMAT）+ 补正 |
| ss_mujoco_004 | D | P4 | 回归（缺失分类填 P4_FORMAT）+ 补正 |

> 挂账条件：回归仍 FAIL 且属源级超时/单点缺失的，如实挂账并给出原因（不伪造成功）。

## 4. 复核分配（122 题 reviewer/reviewed_at 补齐）

当前已复核仅 2 题，缺口 120 题。交叉复核规则：**F 复核 A/D、A 复核 C/E、C/E 互核 F，全部经组长终审**。

| 执行成员 | 复核人 | 题数 |
|---|---|---|
| A | F | 15 |
| D | F | 35 |
| C | A | 46 |
| E | A | 14 |
| F | C/E（互核） | 12（em 由 C 与 E 分领后互校） |
| 全部 | 组长终审 | 122 |

复核动作：逐题核对 verdict 与证据链（parse_goal/retrieve/validate/package）、降级原因与 fallback_reason、截图合规、台账 round 归属；完成后回填 record.json `reviewer` / `reviewed_at`。

## 5. P0 补位（7/12 → ≥8）

P0 共 12 题、当前可用 7（PASS/PASS_WITH_FALLBACK），缺口 5 题（均 FAIL）：

| P0 FAIL 题 | 成员 | 分类 | 补位路径 |
|---|---|---|---|
| ss_huggingface_002 | C | P2_RETRIEVE | 回归（P1） |
| ss_ycb_001 | D | P2_RETRIEVE | 回归（P1 + 补正） |
| ms_001 | A | P2_RETRIEVE | 回归（P1） |
| ms_002 | A | P2_RETRIEVE | 回归（P1） |
| ss_kinova_001 | A | P4_FORMAT | 回归（A2 预算不变前提下复核下载/格式） |

**优先回归队列**（计划 §4.2 代表性题，先跑）：ss_graspnet_004、ss_graspnet_005、ss_zenodo_006、ss_google_scanned_005、ms_009、ms_011、ss_mujoco_008、ss_franka_005。其中达成任一 P0 FAIL 转可用即可达标（8/12），*推荐先冲 ms_001 / ms_002 / ss_huggingface_002*。

## 附：执行顺序建议

1. 成员补交截图（第 1 节）＋补正记录（第 2 节）
2. 优先回归队列跑批（第 5 节末队列）→ 更新 verdict
3. 15 FAIL 逐题定案（第 3 节处置）
4. 交叉复核 + 组长终审（第 4 节），回填 reviewer
5. 重跑 `manage_test_records.py all` 生成台账与统计，核对可用率/合规率回升（修复前基准：可用率 59.0%、截图合规 14.8%）