# 第三次联调报告

> 报告日期：2026-08-09
> 对应目标：在前两次联调基础上补齐**真实 grasp 数据路径**、**sim_config 真实场景命中**、**Hermes 源选择统计**、**human_review 闭环**与**数据包目录结构化**，并通过 5 个中英文目标的端到端集成测试与全量回归验收。
> 联调 Spec：`.trae/specs/implement-third-integration/spec.md`
> 任务清单：`.trae/specs/implement-third-integration/tasks.md`

---

## 1. 执行摘要

### 目标

第三次联调在「真实 URDF/mesh/sim_config/grasp 数据包」链路（第二联调成果）基础上，解决以下验收缺口：

1. 真实 grasp 数据：GraspNet/DexGrasp 按物体名定位单个 `.npz`/`.pkl`，YCB-Video 提供 grasp 标注 fallback。
2. sim_config 真实场景：`mujoco_menagerie` 真实 MJCF 场景直通，运行时用 MuJoCo `mj_step` 验证。
3. Hermes 经验库：源-需求类型二维统计驱动 `retrieve_data` 动态源排序。
4. human_review 闭环：satisfied / revised / unsatisfied 三路闭环与循环上限。
5. 数据包目录结构化：`robots/`、`objects/`、`grasps/`、`sim_config/` 子目录。
6. 端到端验收：5 个中英文目标（Franka/UR5/Kinova × YCB/EGAD × MuJoCo/Isaac/PyBullet）在 mock 下全部跑通，全量回归绿。

### 达成结果

- **11.1 端到端集成测试**：新增 `tests/integration/test_third_integration.py`，参数化覆盖 5 个目标，mock parse_goal 与 Adapter fetch（返回真实感 URDF/STL/npz/MJCF 字节），断言四类文件齐全、无 ERROR 级校验问题、grasp/sim_config 至少一个 `data_source_quality == "real"`、manifest 与磁盘一致、`runtime_check` 已写入。**5 passed in 4.14s（5/5 全绿，超过 4/5 验收线）**。
- **11.2 全量回归**：`pytest` 全量 **546 passed / 1 skipped / 9 deselected**；集成全量 **13 passed**；`ruff check` 通过；本次引入的 mypy 类型错误 23 个已全部修复；`ruff format` 本次改动文件全部格式化。
- **11.3 Adapter 探活**：常规探测 **14/15 fetch 成功**（IEEE 因未配置 API Key 跳过）；GRASP 专项探测覆盖 GraspNet/DexGrasp/YCB 三源。修复后（Task 13）**真实网络下 1/3 返回单个真实 grasp 文件**：DexGrasp 新增 GitHub raw 兜底（`PKU-EPIC/DexGraspNet` 的 `data/dataset/*.npy`，banana 174,954B，`is_real_grasp=true`）；GraspNet-1Billion/DexGraspNet 的标注封装在大体积 tar 归档中（HF 镜像无单文件）、YCB 标注仓库 401 私有（死路径），两源仍降级——如实记录，并以单元/集成测试中的真实 npz/pkl 解析证据佐证（详见 §3.3）。
- **11.4 本报告**：全部数字来自实际运行结果。
- **验收修复（Task 12/13）**：human_review 修订记录真实写入 manifest `revision_history`（state → assemble 链路，含单元测试）；真实 grasp 探活由 0/3 提升至 1/3（DexGrasp 真实 `.npy`）。

---

## 2. 各任务完成情况

### 2.1 阶段 1-4 交付回顾（本次验收范围内）

| Task | 内容 | 状态 |
|---|---|---|
| Task 1 | `PackageManifest` 增加 `runtime_check`/`data_source_quality`/`revision_history`；`ManifestFile`/`ParsedItem` 支持 `data_source_quality` | ✅ |
| Task 2 | `BaseAdapter` 统一本地缓存（`data/cache/<source>/`） | ✅ |
| Task 3 | GraspNet/DexGrasp 按 `object_name` 定位真实 `.npz`/`.pkl` 并缓存；YCB-Video 标注 fallback；`GraspSkill` 解析真实 npz/pkl → `data_source_quality="real"`，metadata JSON → `"fallback"` | ✅ |
| Task 4 | MuJoCo 真实 scene.xml 命中直通；最小 MJCF fallback 含地面/相机/灯光 | ✅ |
| Task 5 | LLM 目标解析 few-shot 与规则后处理（`robot`/`抓取`/`simulation` 等强制映射） | ✅ |
| Task 6 | Hermes「源-需求类型-成功率」二维统计与动态源排序 | ✅ |
| Task 7 | human_review 三路闭环（satisfied/revised/unsatisfied）与循环上限 3 次 | ✅ |
| Task 8 | 数据包按 `robots/ objects/ grasps/ sim_config/ policies/ resources/` 目录结构化 | ✅ |
| Task 9 | MuJoCo 运行时验证（`MjModel.from_xml_string` + `mj_step`）写入 `runtime_check` | ✅ |
| Task 10 | 前端进度表格（阶段/失败原因/fallback 来源）+ 目录结构与校验问题展示 | ✅ |
| Task 12 | human_review 修订记录写入 manifest `revision_history`（state → assemble 链路，revised/unsatisfied/强制结束三分支） | ✅ |
| Task 13 | 真实 grasp 探活修复：DexGrasp GitHub raw 兜底（`PKU-EPIC/DexGraspNet` 单物体 `.npy`），GRASP 专项 0/3 → 1/3 | ✅ |

### 2.2 Task 11.1：端到端集成测试（`tests/integration/test_third_integration.py`）

**5 个端到端目标（参数化）**：

| # | case_id | 目标（goal） | 断言结果 |
|---|---|---|---|
| 1 | `franka_ycb_banana_mujoco` | Franka Panda grasps YCB banana in MuJoCo | ✅ pass |
| 2 | `franka_ycb_banana_mujoco_zh` | 我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉 | ✅ pass |
| 3 | `kinova_egad_mug_isaac` | Kinova Gen3 picks up EGAD mug in Isaac Sim | ✅ pass |
| 4 | `ur5_robotiq_ycb_apple_mujoco` | UR5 with Robotiq 2F-85 grasps YCB apple | ✅ pass |
| 5 | `franka_ycb_blocks_pybullet` | Franka Panda stacks YCB blocks in PyBullet | ✅ pass |

运行：`uv run pytest tests/integration/test_third_integration.py -q` → **5 passed in 4.14s**。

**每个目标断言**：

1. 数据包包含四类文件：`robots/`、`objects/`、`grasps/`、`sim_config/` 各至少一个；
2. `validation_issues` 无 ERROR 级；
3. grasp 与 sim_config 中至少一个文件 `data_source_quality == "real"`；
4. sim_config 来源真实度符合预期（MuJoCo 直通真实 XML → `"real"`；Isaac YAML / PyBullet Python 非 MJCF 输入由 `SimConfigSkill` 降级最小 MJCF → `"fallback"`，由真实 grasp npz 满足第 3 条断言）；
5. manifest `files[].path` 与磁盘文件一致；
6. `PackageManifest.runtime_check` 非空且状态 ∈ {passed, skipped}。

**mock 策略**（避免网络）：`parse_goal._get_llm_client` → 固定返回四类 DataReq；`retrieve_data.select_adapter` → 按 req_type 返回返回固定 RawData 的 mock Adapter（样本字节来自 `tests/unit/skills/sample_data/` 真实 URDF/STL/npz/MJCF）；HermesEngine → Mock；`assemble.settings.output_dir` → tmp_path。

**测试编写过程中修复的缺陷**：

- `TypeError: No synchronous function provided to "retrieve_data"`：异步节点必须用 `await graph.ainvoke(state)`（LangGraph 异步 API），测试改为 async 模式。
- `data_source_quality` 传递链缺口：`SkillRegistry.process_retrieval_result` 未将 Skill 输出的 quality 透传到 `ParsedItem`，`assemble` 也未透传到 `ManifestFile`（见 §2.3 本次修复）。
- 动态创建 mock Adapter 类时类体无法捕获闭包变量（`NameError: source is not defined`），改为占位 + 创建后赋值。

### 2.3 Task 11.2：全量回归（含本次修复）

**全量回归数字**：

| 检查项 | 命令 | 结果 |
|---|---|---|
| lint | `uv run ruff check src tests` | ✅ All checks passed! |
| format（本次改动文件） | `uv run ruff format <本次改动文件>` | ✅ 全部已格式化 |
| format（全量） | `uv run ruff format --check src tests` | ⚠️ 110 已格式化，12 个既有三联改动文件未格式化（非本次引入，见 §4） |
| 类型检查 | `uv run mypy src` | ⚠️ 26 → 3（本次三联引入的 23 个已修复；遗留 3 个既有错误，见 §4） |
| 全量测试 | `uv run pytest -q` | ✅ 538 passed, 1 skipped, 9 deselected in 31.91s |
| 集成全量 | `uv run pytest tests/integration -q -o addopts=""` | ✅ 13 passed in 4.29s |

**本次为修复 mypy 而做的改动**（全部为第三次联调改动文件，均通过单元测试验证无回归）：

- `src/rdi/adapters/_graspnet_objects.py`：`return path` → `return str(path)`（Any → str | None）。
- `src/rdi/adapters/graspnet.py`、`dexgrasp.py`：`_find_file_by_ext` 同理修复。
- `src/rdi/adapters/ycb.py`：缓存分支 `cached` 先收窄再赋值；`_request` 返回值加 `# type: ignore[no-any-return]`；`_pick_mesh_path` 两处 `return str(path)`。
- `src/rdi/adapters/franka.py`：两处缓存分支 `cached` 收窄。
- `src/rdi/adapters/mujoco.py`：`_FALLBACK_SCENES` 联合类型用 `cast(str, ...)` 收窄（TC006 要求引号形式）。
- `src/rdi/graph/nodes/retrieve_data.py`：`fetch(..., req_type=...)` 为 GraspNet/DexGrasp 扩展参数，调用处加 `# type: ignore[call-arg]`。
- `src/rdi/graph/nodes/validate.py`：`yourdfpy`/`mujoco` import 加 `# type: ignore[import-untyped]`，删除 5 处已失效的 `type: ignore`。

**data_source_quality 传递链修复**（本次新增改动，直接支撑集成测试断言）：

- `src/rdi/skills/registry.py`：装配 `ParsedItem` 时透传 `res.data_source_quality`。
- `src/rdi/graph/nodes/assemble.py`：`ManifestFile` 增加 `data_source_quality=item.data_source_quality or "fallback"`。

### 2.4 Task 11.3：`scripts/_probe_adapters.py` GRASP 专项探测

- 新增 `GraspProbeResult` 数据类、`GRASP_PROBE_CASES`（GraspNet/DexGrasp 以 `req_type=GRASP` + `object_name="banana"` 调用 fetch；YCB 以物体 id 调用）。
- 新增 `probe_grasp()`：search 取真实 item_id → `fetch(item_id, req_type=GRASP, object_name=...)` → 按 format 白名单 `{npz, pkl, mat}` 判定是否为真实 grasp 文件。
- 新增 `format_grasp_table()` 与 JSON 证据输出（`data/probe_adapters_results.json` 含 `grasp_probe_results` 与 `real_grasp_count`）。
- 同时清理了脚本原有的 5 个 lint 问题（F401 ×2、UP041 ×3，`ruff check --fix`）。

---

## 3. 验证结果

### 3.1 代码质量检查

| 检查项 | 命令 | 结果 |
|---|---|---|
| lint | `uv run ruff check src tests` | passed |
| 类型检查 | `uv run mypy src` | 3 errors（全部为既有，非本次三联改动引入，见 §4） |
| 格式 | `uv run ruff format --check src tests` | 12 files would be reformatted（全部为既有三联改动文件） |

### 3.2 测试

| 指标 | 数值 |
|---|---|
| 全量 pytest（默认排除 integration 标记） | 546 passed / 1 skipped / 9 deselected |
| 集成全量（`-o addopts=""`） | 13 passed in 4.29s |
| 三联集成测试单文件 | 5 passed in 4.14s |
| 失败 | 0 |

### 3.3 Adapter 探活（真实网络，2026-08-09）

**常规探测**（15 源）：**14/15 fetch 成功**。唯一失败：IEEE（本地未配置 `IEEE_API_KEY`，脚本按设计跳过）。Arxiv/GitHub/HuggingFace/Zenodo/PapersWithCode/DexGrasp/GoogleScanned/GraspNet/YCB/Franka/Allegro/Robotiq/MuJoCo/Isaac 全部 construct + search + fetch 通过。

**GRASP 专项探测**（新增，`req_type=GRASP`，物体名 banana；Task 13 修复后）：

| # | 源 | item_id | 物体 | fetch | 格式 | 大小 | 真实grasp |
|---|---|---|---|---|---|---|---|
| 1 | graspnet | DravenALG/GraspNet-1Billion | banana | OK | json | 567B | 否 |
| 2 | dexgrasp | GaussionZhong/DexGrasp-Anything | banana | OK | **npy** | 174954B | **是**（raw 兜底） |
| 3 | ycb | 011_banana | — | OK | obj | 1431169B | 否 |

**结果：真实网络下 1/3 返回单个真实 grasp 文件，达成「至少一个源」的验收线。** 命中的是 **DexGrasp**：

- 调研实测 `PKU-EPIC/DexGraspNet` 官方仓库 `data/dataset/*.npy`（banana/mug/bottle/camera/plant/plate 各约 175–212KB）经 `raw.githubusercontent.com` 与 `cdn.jsdelivr.net` 双通道 HTTP 200 可达，numpy 验证为 shape=(205,) 的真实 grasp 标注（手部关节 qpos + 物体 scale）。
- `dexgrasp.py` 新增 GitHub raw 兜底：HF 仓库树无单文件时按物体名查 `_DEXGRASP_DATASET_FILES` 映射下载 `.npy` 并缓存，失败静默降级 metadata JSON。
- GraspNet 与 YCB 仍降级，原因如下：

1. **GraspNet-1Billion**：HF 镜像仓库文件树中 `grasp_label/` 下的 `.npz` 均封装在按场景组织的大体积 `.tar` 归档内，无按物体名命名的单文件，`_find_object_grasp_file` 无法命中 → 回退 metadata JSON（降级路径，符合设计）。
2. **DexGrasp HF 仓库**（`GaussionZhong/DexGrasp-Anything`）：仓库无单个 `.pkl`/`.npz` 抓取文件 → raw 兜底前为 metadata JSON（现由 raw 兜底覆盖）。
3. **YCB**：`.mat` 抓取标注指向的 HF 仓库 `ll4ma-lab/ycb-video-annotations` **不可访问（实测 401 私有/gated，HF 与 GitHub 均已验证）**，属三联改动引入的死路径，`_fetch_grasp_annotation` 静默降级为 mesh obj。

**真实 grasp 解析能力已由测试覆盖（离线证据）**：

- `tests/unit/skills/test_grasp_parse.py::test_real_npz_marks_real`：真实 `sample_labels.npz` → `CanonicalGrasp` 且 `data_source_quality="real"` ✅
- `tests/unit/skills/test_grasp_parse.py::test_real_dexgrasp_pkl_marks_real`：真实 `sample_dexgrasp.pkl` → `"real"` ✅
- `tests/unit/skills/test_grasp_parse.py::test_synthetic_fallback_marks_fallback`：metadata JSON → `"fallback"` ✅
- 集成测试 mock 以真实 npz 字节走通「GRASP 检索 → 解析 → real 标注 → manifest」全链路 ✅

即：**「解析真实 npz/pkl → real 标注」的链路已端到端可用且有测试；「从公共仓库网络获取单个真实 grasp 文件」受上游数据组织方式与死路径限制，为已知缺口**（详见 §4）。

---

## 4. 已知问题与风险

| 问题/风险 | 影响 | 当前状态 |
|---|---|---|
| GraspNet-1Billion 真实标注封装在大体积 tar/hdf5 中，HF 镜像无按物体名的单文件 | GRASP 探活无法从该源拿到单个真实 grasp 文件 | 已降级为 metadata JSON（不触发整数据集下载，符合安全设计）；已由 DexGrasp raw 兜底满足「至少一个真实 grasp 源」验收线；GraspNet 场景级获取留待后续 |
| YCB 抓取标注仓库 `ll4ma-lab/ycb-video-annotations` 不可访问（实测 401 私有/gated，HF/GitHub 均验证） | YCB GRASP 标注 `.mat` 路径为死路径，静默降级为 mesh | 需更换为真实可访问的 YCB-Video 标注镜像（如 `ycb-benchmarks/ycb-video-toolbox` 或自托管）；已记录待修复 |
| `mypy src` 遗留 3 个既有错误（非本次三联改动引入，文件相对 HEAD 无改动）：`skills/dataset_parse.py:150`、`skills/code_parse.py:209`（`IO[bytes] | None` 未收窄）、`adapters/google_scanned.py:144`（`no-any-return`） | 类型检查未全绿 | 按任务约定「非本次引入不扩大改动面」记录，建议后续单独清理 |
| `ruff format --check` 剩余 12 个既有三联改动文件未格式化（`frontend/app.py`、`goal_parsing.py`、`grasp_parse.py`、`test_dexgrasp.py`、`test_graspnet.py`、`test_isaac.py`、`test_ycb.py`、`test_progress.py`、`test_assemble.py`、`test_human_review.py`、`test_validate.py`、`test_strategy.py`） | 格式检查未全绿（纯格式，无行为差异） | 为三联既有改动欠账，非本次引入；本次已格式化自身改动的全部文件 |
| Isaac/PyBullet 目标 sim_config 为最小 MJCF fallback（`data_source_quality="fallback"`） | 仿真场景简单，未复用真实 IsaacLab/PyBullet 资产 | 受限于上游非 MJCF 输入；由真实 grasp real 满足验收断言，已在测试中显式声明预期 |
| IEEE API Key 未配置 | 常规探活 14/15 | 仅影响单一源，脚本已跳过并记录 |

---

## 5. 下一步建议

1. **修复 YCB 标注死路径**：将 `_GRASP_ANNOTATION_REPO` 指向真实可访问的 YCB-Video 标注源（当前候选 `ll4ma-lab/ycb-video-annotations` 实测 401 私有），或改为本地/自托管镜像，恢复 GRASP `.mat` 真实路径；修好后重新跑 GRASP 专项探活。
2. **GraspNet 场景级获取**：评估按「物体 id → 场景列表 → 单帧 npz」二级下载方案（GraspNet 官方以场景组织数据），或将常用物体的标注抽离为镜像仓库（DexGrasp 已通过 `PKU-EPIC/DexGraspNet` raw 兜底打通单文件路径，可作参照）。
3. **清理既有 mypy/format 欠账**：单独一次改动处理 `dataset_parse.py`/`code_parse.py`/`google_scanned.py` 的 3 个类型错误与 12 个未格式化文件。
4. **稳定真实 LLM 目标解析**：持续扩充 few-shot 与 schema 约束，覆盖更多中英文句式与机器人/物体名变体。
5. **HERMES 经验库冷启动**：为「源-需求类型」统计提供种子数据，加速 `retrieve_data` 动态排序收敛。

---

## 6. 关键文件清单

| 类别 | 路径 |
|---|---|
| 本报告 | `docs/third_integration_report.md` |
| 联调 Spec / 任务 / 清单 | `.trae/specs/implement-third-integration/{spec,tasks,checklist}.md` |
| 三联集成测试（新增） | `tests/integration/test_third_integration.py` |
| Adapter 探活脚本（更新） | `scripts/_probe_adapters.py` |
| 探活证据 | `data/probe_adapters_results.json` |
| quality 传递链修复 | `src/rdi/skills/registry.py`、`src/rdi/graph/nodes/assemble.py` |
| mypy 修复（三联文件） | `src/rdi/adapters/{_graspnet_objects,graspnet,dexgrasp,ycb,franka,mujoco}.py`、`src/rdi/graph/nodes/{retrieve_data,validate}.py` |
| 真实 grasp 解析 | `src/rdi/skills/grasp_parse.py`、`tests/unit/skills/test_grasp_parse.py`、`tests/unit/skills/sample_data/grasp/` |
| sim_config 真实路径 | `src/rdi/adapters/mujoco.py`、`src/rdi/skills/sim_config.py` |
| Hermes 统计 | `src/rdi/hermes/{experience_db,strategy}.py` |
| human_review 闭环 | `src/rdi/graph/nodes/human_review.py`、`src/rdi/graph/{edges,builder}.py` |
| 数据包目录结构化 | `src/rdi/graph/nodes/assemble.py`、`src/rdi/models/manifest.py` |
| 运行时验证 | `src/rdi/graph/nodes/validate.py`（mujoco `mj_step`） |
| 前端可视化 | `src/rdi/frontend/app.py` |
