# Checklist — 第三次联调（implement-third-integration）

## 基础
- [x] Task 1: `PackageManifest` 含 `runtime_check`/`data_source_quality`/`revision_history`，`ManifestFile` 含 `data_source_quality`，现有 393+ 测试不破坏
- [x] Task 2: `BaseAdapter.get_cache_path`/`is_cached` 存在；Franka/YCB/GraspNet 走统一缓存；缓存命中不触发网络（mock 测试）

## 真实 grasp 数据路径
- [x] GraspNet 按 `object_name` 定位 `grasp_label/` 下 `.npz` 并可缓存
- [x] DexGrasp 可定位单个 `.pkl` 并缓存
- [x] YCB-Video 提供 grasp 标注 fallback（`.mat`/`.json`）
- [x] `GraspSkill` 能解析真实 `.npz`/`.pkl` 为 `CanonicalGrasp`，`metadata` 标注 `data_source_quality`；synthetic fallback 保留并标注 `fallback`
- [x] `scripts/_probe_adapters.py` 中 GraspNet/DexGrasp/YCB-Video 至少一个返回单个真实 grasp 文件（非 metadata JSON）—— 真实网络探活 0/3 → 1/3：DexGrasp 经 GitHub raw 兜底返回真实 `.npy`（banana 174954B）；GraspNet（仅 tar 归档）与 YCB（标注源 401 私有）仍降级，原因与 mock 证据见报告

## sim_config 真实场景
- [x] `_FALLBACK_SCENES` 含 `unitree_go2`、`franka_emika_panda/scene.xml` 并标注关键词
- [x] 命中真实 XML 时 `SimConfigSkill` 直接返回 XML bytes（不重建）
- [x] 最小 MJCF fallback 含地面、相机、灯光
- [x] 输入 "Franka Panda in MuJoCo" 时 MuJoCoAdapter 返回真实 scene.xml

## LLM 目标解析稳定化
- [x] prompt 含 10+ 组 few-shot（Franka/Kinova/UR5 × YCB/EGAD/ModelNet × MuJoCo/Isaac/PyBullet）
- [x] `parse_goal` 规则后处理覆盖 `robot`/`机器人`→ROBOT_URDF、`模型`/`物体`→MESH、`抓取`→GRASP、`simulation`→SIM_CONFIG
- [x] 无法识别需求标记 `UNKNOWN` 并记录 warning
- [x] 10 个常见组合至少 9 个正确产出四类 DataReq（单元测试覆盖）

## human_review 闭环
- [x] `state` 含 `revised_goal`、`query_cache` 字段
- [x] `revised` → 反馈转目标 → `parse_goal`；`unsatisfied` → `retrieve_data`；`satisfied` → `END`
- [x] 循环上限（3 次）生效，每次循环清空旧 `retrieval_results`
- [x] manifest `revision_history` 记录版本关联 —— human_review 在 revised/unsatisfied/强制结束分支写入（state.revision_history），assemble 挂到 PackageManifest，单元测试断言非空
- [x] 单元测试覆盖三种 decision 分支

## 数据包目录结构化
- [x] 端到端生成数据包含 `robots/`、`objects/`、`grasps/`、`sim_config/` 子目录
- [x] manifest `files[].path` 与磁盘目录结构一致

## 真实可运行性验证
- [x] `mujoco` 作为可选依赖安装（pyproject + uv.lock）
- [x] `validate.py` 对 SIM_CONFIG 执行 `mj_step` 验证并写入 `runtime_check`；验证失败 severity=ERROR
- [x] MuJoCo 能加载 sim_config 并运行一步 `mj_step`（集成测试）

## Hermes 源选择
- [x] 统计升级为「源-需求类型-成功率」二维
- [x] `retrieve_data` 基于 Hermes 优先级动态排序，失败时尝试更高成功率源
- [x] 单元测试验证 Hermes 根据历史统计调整优先级

## 前端进度可视化
- [x] 前端表格展示每个 DataReq 的阶段（解析中/检索中/成功/失败/降级）、失败原因、fallback 来源
- [x] 展示数据包目录结构与 `validation_issues`

## 集成测试与回归
- [x] `tests/integration/test_third_integration.py` 覆盖 5 个中英文目标，mock 下至少 4/5 全绿，断言四类文件、无 ERROR、grasp/sim_config 至少一个 real
- [x] `pytest` 全绿（546 passed / 1 skipped / 9 deselected）、`ruff check` 通过；`ruff format --check` 仅剩 12 个既有三联文件未格式化（已记录）；`mypy` 仅剩 3 个既有错误（非三联引入，已记录）
- [x] `scripts/_probe_adapters.py` 14/15 fetch 成功且 GRASP 专项至少一个源返回真实 grasp 文件（DexGrasp npy，real_grasp_count=1；GraspNet 仅 tar 归档、YCB 标注源 401，原因见报告）
- [x] `docs/third_integration_report.md` 输出三联报告
