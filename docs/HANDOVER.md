# 交接文档（2026-08-22）

> 面向新会话的快速接管说明。仓库：`c:\Users\yzl13\Documents\GitHub\robot-data-integrator`
> 技术栈：uv 项目（`uv run pytest` / `uv run python`），Python，测试基线 **894 passed, 1 skipped, 9 deselected**。

## 1. 当前状态快照

- 三个获得批准的 spec 已全部完成并收口（规格文档在 `.trae/specs/`，均已勾选）：
  - `fix-round2-test-issues`（二轮 50 FAIL 七大根因修复，P0 内容有效性把关 + P1 检索/解析 + P2 记录治理）
  - `improve-retrieve-hit-and-record-closure`（检索候选语义预筛 + FAIL error 回填 `backfill-errors` 子命令）
  - `extend-kinova-isaac-format-coverage`（kinova 资产缺失显性化 + isaac 降级诚实标记 + 收录实证扩充）
  - `improve-multi-source-budget-and-scene-assembly`（检索预算共享软 deadline + 场景组装接线确认 + ycb cup↔mug 别名）
- 两次全量回归基线：885 → 894 passed，单调增长零回归。
- **当前无进行中的编码任务**。以下"-4/-5"均为方向，未立项（用户尚未批准）。

## 2. 管线关键事实（新会话必备）

**检索→落包 6 段**：parse_goal（拆需求）→ node_retrieve（逐源 search→语义预筛→fetch，软预算）→ 内容有效性预检（占位/语义错配/mesh 缺失）→ node_parse_convert（非 SIM_CONFIG 先处理、SIM_CONFIG 注入兄弟 urdf_path/mesh_path）→ node_validate（runtime_check/validation_issues）→ node_assemble（按 req_type 落盘 robots/ objects/ grasps/ sim_config/ policies/ resources/ + manifest.json/checksums.txt/provenance.log/semantic_map.json/quality_explanation.md）。

**17 个 adapter**：资产型 9（kinova/isaac/franka/allegro/robotiq/mujoco/ycb/google_scanned/dexgrasp），数据集型 3（huggingface/github/zenodo），内容型（graspnet/sensor/policy），文献型 3（arxiv/ieee/paperswithcode）。

**主要产出格式**：urdf/stl（最常见）+ mjcf(xml)/py(isaac 原始)/obj/dae/png/jpg/json/npz/md/txt/bin。任务数据（grasp/sensor/policy/dataset）命中率低是**源连接+验证+补产三环缺口**，非解析问题。

**关键防骗机制**（勿回退）：占位检测 `_is_metadata_proxy`、语义错配 `_semantic_mismatch`（validate.py）、assets_missing 透传、降级场景标记 degraded_scene、包完整度 `_derive_package_status`。

## 3. 已知问题 / 挂账（新任务候选）

- **落包自洽性 4 点（spec-4 候选，用户已认可方向但未批准）**：①MeshSkill output_path=`objects/{item_id}.stl` 与 assemble 实际落 `objects/{req_id}.stl` 不一致；②`generate_minimal_mjcf` 只写路径引用不校验文件存在（死链风险）；③URDF 内 mesh 引用与落盘路径自洽性仅 kinova 等少数适配器保证；④manifest local_path 与实际磁盘文件无端到端审计。修复方向：端到端"落盘包 trimesh/muJoCo 冒烟加载"单测 + 对齐 ①-④。
- **UR5 收录挂账**：IsaacLab 无 UR5 资产已实证（GitHub API 核实），上游支持后方可补录。
- **kinova 本地挂载资产路径拼接**：`base_dir + package://rest` 与仓库根相对布局不完全对齐（低频，域外）。
- **记录治理**：`manage_test_records.py backfill-errors --apply` 可回填 FAIL error（真实台账 dry-run 已验：可回填 18 / 待人工 32）；`docs/fix_actions_checklist.md` 为成员动作清单（截图补交 104 题等）。

## 4. 进行中的方案讨论（未立项，决策需要用户拍板）

**方向：非几何数据（GRASP/SENSOR/POLICY/DATASET）拿不到的产线方案**（用户要求"满意才执行"）：
- **L1 格式契约**：grasp/sensor/policy 三 skill 各加结构断言（数组形状/坐标系/时间戳/schema），manifest 如实标 `validation: structural-only`。
- **L2 GRASP 几何补产**：从已落盘 STL 派生 canonical grasp（复用 `_serialize_grasps`），**硬门槛为 MuJoCo 物理仿真验证**（夹爪闭合→举起→不掉落，判据：接触力+质心随动），标注 `derived:true / validation_level: contact-simulated (MuJoCo 默认参数) / 未真机验证`；未装 mujoco 的环境如实标 `skipped`。mujoco 已是 runtime extra 可选依赖（validate 已有 load 级用法，缺 physics step 用法）。
- **L3 需求分类不空转**：parse_goal 打标 retrievable/derivable/not-obtainable，不可得直接挂账。
- **决策点（悬而未决）**：L2 验证标准取"MuJoCo 默认参数可复现判定"（推荐）/候选+脚本/放弃 L2——用户尚未同意，勿擅自执行。
- **明确排除**：不接多个杂源铺摊子、不做 policy 论文复现、不做大规模布局生成。

## 5. 常用命令

- 全量回归：`uv run pytest tests/ -q`（~2-10 分钟）
- 定向：`uv run pytest tests/unit/graph/test_retrieve_data.py tests/unit/adapters/test_ycb.py tests/unit/skills/test_registry.py tests/unit/skills/test_sim_config.py -q`
- 台账统计：`uv run python manage_test_records.py all`；error 回填：`uv run python manage_test_records.py backfill-errors --apply`（默认 dry-run）
- ruff：`uv run ruff check src tests`

## 6. 文档索引

- 规格：`.trae/specs/fix-round2-test-issues/`、`improve-retrieve-hit-and-record-closure/`、`extend-kinova-isaac-format-coverage/`、`improve-multi-source-budget-and-scene-assembly/`（均含 spec/tasks/checklist，已勾选）
- 动作清单：`docs/fix_actions_checklist.md`
- 核心代码：图节点 `src/rdi/graph/nodes/`（retrieve_data/parse_convert/validate/assemble）、skill 层 `src/rdi/skills/`（registry.py 装配）、adapter `src/rdi/adapters/`、模型 `src/rdi/models/`