# 修复 sim_config 与 grasp 真实数据获取 Checklist

- [x] `MuJoCoAdapter.search("MuJoCo panda")` 返回 `franka_emika_panda` 场景
- [x] `IsaacSimAdapter.search` 支持多 token query
- [x] `SimConfigSkill` 在 adapter 无有效 XML 时能生成最小 MJCF XML
- [x] `parse_convert` 向 `SimConfigSkill` 传入 URDF/mesh 路径上下文
- [x] `GraspSkill` 能解析 GraspNet metadata JSON 并返回 synthetic grasp
- [x] `GraspSkill.generate_synthetic_grasps` 生成符合 `CanonicalGrasp` 结构的数据
- [x] 端到端目标生成包含 `.urdf`、`.stl`、`.xml`、`.json` 的数据包
- [x] 输出包 `validation_issues` 中无 ERROR 级别问题
- [x] `uv run pytest` 全绿
- [x] `uv run ruff check src tests` 无错误
- [x] `uv run ruff format --check src tests` 无错误
