# 修复 sim_config 与 grasp 真实数据获取 Tasks

> 依据：[spec.md](./spec.md)

- [x] Task 1: 修复 MuJoCoAdapter 多 token 搜索
  - [x] SubTask 1.1: 修改 `src/rdi/adapters/mujoco.py`，让 `_search_fallback` 支持 query 中任一 token 命中 id/title/description
  - [x] SubTask 1.2: 同步修改 `src/rdi/adapters/isaac.py` 的 `_search_fallback`
  - [x] SubTask 1.3: 更新 `tests/unit/adapters/test_mujoco.py` 与 `test_isaac.py`

- [x] Task 2: 修复 sim_config 拿不到 MuJoCo XML 的问题
  - [x] SubTask 2.1: 在 `src/rdi/graph/nodes/retrieve_data.py` 中确保 sim_config 的 keywords 包含机器人名/物体名（从 state 中已 retrieve 的 URDF/mesh req 提取）
  - [x] SubTask 2.2: 修改 `src/rdi/skills/sim_config.py`，新增 `generate_minimal_mjcf(urdf_path, mesh_path)` fallback，当 adapter 返回非 XML 或解析失败时，基于已获取 URDF/mesh 生成最小 MuJoCo 场景
  - [x] SubTask 2.3: 更新 `src/rdi/graph/nodes/parse_convert.py` 对 sim_config 调用 Skill 时传入 `urdf_path`/`mesh_path` 上下文
  - [x] SubTask 2.4: 新增集成测试验证 sim_config 最终产出 `.xml`

- [x] Task 3: 修复 grasp 解析失败问题
  - [x] SubTask 3.1: 修改 `src/rdi/skills/grasp_parse.py`，`process` 接收 `format=json` 时解析 metadata，返回基于物体名的 synthetic grasp 列表
  - [x] SubTask 3.2: 在 `GraspSkill` 中新增 `generate_synthetic_grasps(object_name: str, count: int = 5)`，使用规则化位姿（物体上方、Z 朝下）生成 CanonicalGrasp
  - [x] SubTask 3.3: 更新 `src/rdi/graph/nodes/parse_convert.py`，对 grasp 的 metadata JSON 传入 `object_name`
  - [x] SubTask 3.4: 更新 `tests/unit/skills/test_grasp_parse.py`

- [x] Task 4: 端到端验证
  - [x] SubTask 4.1: 运行完整工作流，目标为 "我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉，并测试抓取姿态的稳定性。"
  - [x] SubTask 4.2: 验证输出包包含 `.urdf`、`.stl`、`.xml`、`.json` 且 `validation_issues` 无 ERROR
  - [x] SubTask 4.3: 运行 `uv run pytest` 全绿
  - [x] SubTask 4.4: 运行 `uv run ruff check src tests` 与 `uv run ruff format --check` 无错误

# Task Dependencies

- Task 2 depends on Task 1（sim_config 需要先能命中 MuJoCo XML）
- Task 3 depends on Task 2 可并行（grasp 与 sim_config 独立，但共用端到端验证）
- Task 4 depends on Task 2 and Task 3
