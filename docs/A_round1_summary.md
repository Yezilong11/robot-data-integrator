# A 负责一轮 3 题前端全流程复测汇总报告

- **执行人**：A
- **执行日期**：2026-08-21（22:34–23:04）
- **执行方式**：前端真实流程测试（http://127.0.0.1:8000/，输入目标 → 点击运行 → human_review 中断 → 点击「继续运行」（satisfied）→ 提取最终结果）
- **LLM 引擎**：qwen3.7-plus（dashscope.aliyuncs.com/compatible-mode/v1）
- **分支/提交**：feat/integration-v3 @ 5ec31d7
- **数据记录**：`records/ms_001/record.json`、`records/ms_002/record.json`、`records/ms_006/record.json` 均已覆盖更新为二轮口径；观测数据取自 `data/output_packages/package-*/manifest.json` 与 `/api/result/{task_id}`

---

## 一、总体统计

| 判定 | 数量 | 占比 | 用例 |
|---|---|---|---|
| PASS | 0 | 0% | - |
| PASS_WITH_FALLBACK | 0 | 0% | - |
| FAIL | 3 | 100% | ms_001、ms_002、ms_006 |

- 全部 3 题 FAIL 分类均为 **P2_RETRIEVE**（必要需求检索失败），无一为系统崩溃——前端全流程均可正常运行至终态。
- 复测结论与一轮对比：3 题一轮均为 PASS_WITH_FALLBACK，本轮全部降级为 FAIL。

---

## 二、逐题测试明细

| # | case_id | 目标输入 | 判定 | 数据源（最终） | 文件数 | run_id / 数据包 | 异常摘要 |
|---|---|---|---|---|---|---|---|
| 1 | ms_001 | Franka Panda grasps YCB banana in MuJoCo | FAIL(P2) | github + mujoco | 70 | 20260821-223404-4c1099f1 / package-20260821-224303 | **缺 mesh + grasp**：ycb 未收录 banana、google_scanned 404、graspnet 未收录；dexgrasp pkl 反序列化失败（unpickling stack underflow）。URDF 降级 github、sim_config mujoco 命中 |
| 2 | ms_002 | 我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉 | FAIL(P2) | github + huggingface + mujoco | 71 | 20260821-224458-0ff1f599 / package-20260821-225320 | **缺 mesh**：ycb/graspnet 未收录 banana。grasp 降级 huggingface 拿到 CanonicalGrasp json（题设 expected NPZ）；URDF 降级 github |
| 3 | ms_006 | 用 Franka 在 MuJoCo 里抓取香蕉 | FAIL(P2) | github + mujoco | 70 | 20260821-225457-baf1e164 / package-20260821-230436 | **缺 mesh + grasp**：ycb/graspnet 未收录 banana、grasp 检索超时。URDF 降级 github、sim_config mujoco 命中 |

---

## 三、发现的问题与初步分析

### 1. 【严重 P3_SOURCE】YCB banana mesh 全源未收录，3 题同源 FAIL（ms_001/002/006）
- 现象：三题对 banana mesh 的需求全部失败——ycb 适配器仅收录 20 个已知目标未含 banana（「有源但未收录」）、graspnet 仅收录 2 个已知目标、google_scanned 的 `Banana for Scale` tip/files 404。这是本轮复测 3 题全 FAIL 的共同根因。
- 分析：与 D 一轮复测发现的 YCB 覆盖问题一致（D 的 ss_ycb_001/002 同样因未收录失败）。banana 是 YCB 核心物体却无法获取，属于硬编码已知目标枚举覆盖不全。
- 建议：ycb 适配器接入 YCB 官方模型仓库动态枚举或扩充常见物体清单；google_scanned 404 时改走 zip 直下兜底。

### 2. 【P3_SOURCE / P5】grasp 需求命中极不稳定，同目标三种结果（ms_001/002/006）
- 现象：ms_001 dexgrasp pkl 反序列化失败（`unpickling stack underflow`）；ms_002 降级 huggingface 拿到 CanonicalGrasp json（题设 expected.format 为 NPZ，格式不符）；ms_006 检索超时（per_req_timeout）。三题三种结局，均未产出符合题设的 NPZ 抓取数据。
- 分析：dexgrasp 适配器对 pkl 的反序列化缺少容错（stack underflow 说明读取逻辑或文件不完整）；grasp 降级链路格式无白名单校验。
- 建议：修复 dexgrasp pkl 解析；对 grasp 交付增加 expected_format 白名单校验，格式不符应 FAIL 而非交付。

### 3. 【P5】franka 专用源 raw.githubusercontent 直连超时（3 题一致）
- 现象：3 题 URDF 需求均 franka 源 36s 超时，降级 github（AndrejOrsula/panda_gz_moveit2）才命中，且仅 URDF 单文件。
- 分析：与 D 一轮复测 ss_franka_001/003 现象完全相同；raw 直连在当前网络下不稳定。
- 建议：franka 源默认走 jsdelivr CDN（D 的 ss_franka_002 走 CDN 正常 19 文件），raw 直连作备选。

### 4. 【正面】mujoco 源稳定，sim_config 3/3 真实命中
- 现象：3 题 sim_config 需求全部由 mujoco 适配器真实命中 mujoco_menagerie franka_emika_panda scene.xml（scene.xml + panda.xml + 67 个 STL/OBJ assets，共 69 文件，quality=real，无降级）。
- 结论：sim_config 链路（robot_urdf/mesh/grasp 之外的第四类需求）当前最可靠。

---

## 四、结论

- 前端全流程（输入 → 运行 → 人工审查中断 → 继续 → 打包）3/3 可正常走通，无崩溃。
- 3/3 FAIL 均为业务性检索失败（P2_RETRIEVE），其中 YCB banana mesh 全源未收录是共同根因。
- 一轮（PASS_WITH_FALLBACK）→ 二轮（FAIL）差异说明：检索结果受源覆盖与网络状态影响大，同一目标多次运行结局可能不同（grasp 尤其明显）。
- **最需优先修复**：YCB 已知目标覆盖不足（问题 1）与 dexgrasp pkl 解析（问题 2），直接决定本组多源抓取类题目的可用性。
