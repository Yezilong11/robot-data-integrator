# Tasks

## 阶段 1：基础（可并行）
- [x] Task 1: 扩展数据包清单模型：`PackageManifest` 增加 `runtime_check`、`data_source_quality`、`revision_history` 字段；`ManifestFile` 增加 `data_source_quality`；`StandardResult`/`ParsedItem` 支持 `data_source_quality` 标注；同步更新受影响测试。
- [x] Task 2: BaseAdapter 统一本地缓存：在 `src/rdi/adapters/base.py` 增加 `get_cache_path(item_id)` / `is_cached(item_id)` / `save_to_cache()`，缓存目录 `data/cache/<source>/`；Franka、YCB、GraspNet fetch 优先走缓存；用 mock 测试验证缓存命中不触发网络请求。

## 阶段 2：核心能力（可并行，依赖阶段 1 的 Task 2）
- [x] Task 3: 真实 grasp 数据路径：
  - [x] 3.1 `graspnet.py`：支持按 `object_name` 定位 `grasp_label/` 下对应 `.npz`（`list_files` 基础上增加物体名匹配），下载后缓存到 `data/cache/graspnet/`
  - [x] 3.2 `dexgrasp.py`：类似定位单个 `.pkl` 并缓存
  - [x] 3.3 `ycb.py`：增加 YCB-Video grasp 标注（`.mat`/`.json`）fallback 路径
  - [x] 3.4 `grasp_parse.py`：支持真实 `.npz`/`.pkl` 解析为 `CanonicalGrasp`（移除对 graspnetAPI 的强制依赖，不可用时用现有近似重建并降 completeness）；`metadata` 标注 `data_source_quality`（real/synthetic/fallback）
  - [x] 3.5 新增 sample `.pkl` 样本到 `tests/unit/skills/sample_data/grasp/`；更新/新增单元测试覆盖 npz/pkl 真实路径、synthetic fallback、缓存命中
- [x] Task 4: sim_config 真实场景命中：
  - [x] 4.1 `mujoco.py`：`_FALLBACK_SCENES` 增加 `unitree_go2`、`franka_emika_panda/scene.xml` 等，标注适用关键词
  - [x] 4.2 `sim_config.py`：Adapter 返回真实 XML 时直接返回 XML bytes（不重建）；fallback `generate_minimal_mjcf` 增加 `<camera>`
  - [x] 4.3 `isaac.py`：增加官方场景到 MJCF/USD 映射或明确提示
  - [x] 4.4 更新单元测试：真实 XML 直通路径、fallback 含地面+相机且可加载
- [x] Task 5: LLM 目标解析稳定化：
  - [x] 5.1 `goal_parsing.py`：增加 10+ 组 few-shot，覆盖 Franka/Kinova/UR5 × YCB/EGAD/ModelNet × MuJoCo/Isaac/PyBullet
  - [x] 5.2 `parse_goal.py`：后处理补全关键词（`robot`/`机器人`→ROBOT_URDF、`模型`/`物体`→MESH、`抓取`→GRASP、`simulation`→SIM_CONFIG），无法识别标记 `UNKNOWN` 并记录 warning
  - [x] 5.3 新增/更新单元测试覆盖 10+ 目标表述与全部强制映射分支
- [x] Task 6: Hermes 源-需求类型统计：
  - [x] 6.1 `experience_db.py`：`source_stats` 升级为「源-需求类型」二维统计（update/query 方法）
  - [x] 6.2 `strategy.py`：`get_source_priority(req_type, ...)` 基于二维统计排序
  - [x] 6.3 `retrieve_data.py`：接入动态排序并在失败时尝试更高成功率源
  - [x] 6.4 更新单元测试验证 Hermes 根据历史统计调整优先级

## 阶段 3：图级改造（可并行，依赖阶段 1 + 阶段 2）
- [x] Task 7: human_review 真实闭环：
  - [x] 7.1 `state.py`：增加 `revised_goal`、`query_cache` 字段
  - [x] 7.2 `human_review.py`：`revised` 时调 LLM 把反馈转为修正目标；`unsatisfied` 时生成更具体检索建议；写入 `state.user_feedback` 与 `revision_history`；限制最大循环次数
  - [x] 7.3 `builder.py`/`edges.py`：条件边改为 `revised`→`parse_goal`、`unsatisfied`→`retrieve_data`、`satisfied`→`END`，统一 decision 取值
  - [x] 7.4 单元测试覆盖三种 decision 分支与循环上限
- [x] Task 8: 数据包目录结构化：`assemble.py` 按 req_type 映射 `robots/`、`objects/`、`grasps/`、`sim_config/`、`policies/`、`resources/`，`req_id` 作文件名前缀；manifest `files[].path` 同步为子目录相对路径；更新测试。
- [x] Task 9: 真实可运行性验证：
  - [x] 9.1 `pyproject.toml` 增加 `mujoco` 可选依赖并 `uv lock`（本地安装）
  - [x] 9.2 `validate.py`：SIM_CONFIG 用 `mujoco.MjModel.from_xml_string` + `mj_step` 验证，写入 `validation_issues` 与 `runtime_check`（mujoco 不可用时降级为 XML 解析并标注）
  - [x] 9.3 新增集成测试覆盖运行时验证

## 阶段 4：前端（依赖阶段 3）
- [x] Task 10: 前端进度可视化：`app.py` 以表格展示每个 DataReq 的阶段（解析中/检索中/成功/失败/降级）、失败原因、fallback 来源；展示数据包目录结构与 `validation_issues`。

## 阶段 5：测试与验收
- [x] Task 11: 集成测试与全量回归：
  - [x] 11.1 新增 `tests/integration/test_third_integration.py` 覆盖 5 个中英文目标，mock parse_goal 与 Adapter，断言四类文件、无 ERROR、grasp/sim_config 至少一个 real
  - [x] 11.2 全量回归：`uv run pytest`、`ruff check/format`、`mypy` 全绿（mypy 遗留 3 个既有错误，见报告）
  - [x] 11.3 更新 `scripts/_probe_adapters.py` 覆盖新 grasp 路径，验证至少一个源返回真实 grasp 文件（真实网络下 0/3，原因见报告）
  - [x] 11.4 更新 `docs/third_integration_report.md` 输出三联报告

## 阶段 6：验收修复（checklist 未达标项）
- [x] Task 12: human_review 写入 manifest revision_history：human_review 节点在 revised/unsatisfied 决策时构造 revision 记录（revision 序号、feedback、timestamp），写入 state 的 revision_history（如 state 无此字段则新增）；assemble 节点把 `state.revision_history` 挂到 `PackageManifest.revision_history`；补充单元测试断言 manifest 记录版本关联。
- [x] Task 13: 真实 grasp 探活修复：让 `scripts/_probe_adapters.py` 的 GRASP 专项在真实网络下至少一个源返回单个真实 grasp 文件（非 metadata JSON）。当前 0/3 原因：GraspNet/DexGrasp 的 grasp_label 封装在大体积 tar/hdf5 中、YCB-Video 标注仓库 `ll4ma-lab/ycb-video-annotations` 404。修复方向（任选其一，先做可行性验证）：
  - 修复 YCB-Video grasp 标注 URL 为一个真实可达的源（GitHub/HF 上搜一个含 `.mat`/`.json` grasp 标注的公开仓库并验证 URL 可达）；
  - 或找到另一个真实网络下可单文件下载的真实 grasp 数据源（如含单 `.npz` 的公开镜像）；
  - 若外部环境确实无法解决（如实联网验证后），在报告与 checklist 中记录阻塞原因与 mock 证据，不伪装成功。
  - [x] 13.1 实测可达源：DexGraspNet 官方 GitHub 仓库 `PKU-EPIC/DexGraspNet` 的 `data/dataset/*.npy` 单物体 grasp 文件（banana/mug/bottle/camera/plant/plate，各约 175–212KB），raw.githubusercontent.com 与 cdn.jsdelivr.net 双通道 HTTP 200，经 numpy 验证为 205 个 grasp 样本（手部关节 qpos + scale）
  - [x] 13.2 `dexgrasp.py`：`_fetch_grasp` 在 HF 仓库树无单文件时新增 GitHub raw 兜底（`_find_dexgrasp_raw_file` 按规范化物体名查 `_DEXGRASP_DATASET_FILES`，`_download_dexgrasp_raw` 下载 .npy 并缓存，失败静默降级 metadata）；`_GRASP_EXTS`/fmt 映射/`_file_metadata` 支持 .npy
  - [x] 13.3 `_probe_adapters.py`：`REAL_GRASP_FORMATS` 加入 `npy`
  - [x] 13.4 `ycb.py`：更新死路径注释（实测 401，保留静默降级 mesh 行为）；YCB 无法修复原因记录在报告
  - [x] 13.5 单元测试：`test_dexgrasp.py` 新增 raw 兜底成功（format=npy、URL 含 raw.githubusercontent.com/PKU-EPIC/DexGraspNet、缓存命中）+ 失败静默降级两个测试
  - [x] 13.6 真实网络探活验证：GRASP 专项 0/3 → **1/3**（DexGrasp 返回 `npy` 174954B，GraspNet 仍 metadata JSON、YCB 仍降级 mesh），全部 40 个 adapter 单元测试通过

# Task Dependencies
- Task 1（manifest 扩展）：无
- Task 2（Adapter 缓存）：无
- Task 3（grasp 路径）依赖 Task 2
- Task 4（sim_config）依赖 Task 1（data_source_quality 标注）、无缓存依赖
- Task 5（LLM 稳定化）：无
- Task 6（Hermes 统计）：无
- Task 7（human_review 闭环）依赖 Task 1（revision_history）、Task 5（反馈转换/重新解析）
- Task 8（目录结构化）依赖 Task 1（manifest path）
- Task 9（运行时验证）依赖 Task 4（真实 XML 路径）
- Task 10（前端可视化）依赖 Task 7、Task 8、Task 9
- Task 11（集成测试与回归）依赖全部
- Task 12（revision_history 写入）依赖 Task 1、Task 7
- Task 13（真实 grasp 探活修复）依赖 Task 3、Task 11

# 并行执行建议
- 阶段 1：Task 1、Task 2 并行
- 阶段 2：Task 3、Task 4、Task 5、Task 6 并行（涉及文件互不重叠）
- 阶段 3：Task 7、Task 8、Task 9 并行
- 阶段 4：Task 10
- 阶段 5：Task 11（先 11.1，再 11.2-11.4）
- 阶段 6：Task 12、Task 13 并行（涉及文件互不重叠）
