# Checklist

## A 多源预算共享软 deadline
- [x] 快源提前完成 → 剩余时间释放给后续源（`_compute_source_cap` 剩余收紧 + 集成级断言后续源继续执行）（spec: 快源提前完成释放时间）
- [x] 慢源达子预算上限即中止、继续后续源（集成级断言超时中止后 Zenodo 源成功）（spec: 慢源不拖死其余）
- [x] 累计达 per_req_timeout → 剩余源跳过并记录「预算耗尽」、需求级超时语义不变（spec: 总预算到点即停）
- [x] 单测覆盖快源释放/慢源中止/总预算到点三场景，success/missing/error 判定不变

## B 场景组装接线
- [x] 组装架构已核实：parse_convert 第二遍循环兄弟可达，`_build_sim_config_context` 已注入 urdf_path/mesh_path（接线已存在，生产代码未改）；mesh_path 用 D4 相对路径（比 spec 字面更正确）（spec: 场景组装接线）
- [x] 无兄弟需求时零注入、行为不变（registry context 单测锁定）（spec: 无兄弟需求）
- [x] SimConfigSkill `_fallback_to_mjcf(urdf_path, mesh_path)` 能力有单测锁定（引用临时 urdf/mesh 路径）

## C ycb cup↔mug 语义别名
- [x] query "YCB cup mesh" → 命中 025_mug，title 仍 "Mug"（spec: 别名命中）
- [x] 无别名 key（saucer）不误命中；未知 query（teapot）仍抛"仅收录"（不改变未收录语义）

## 回归
- [x] `uv run pytest tests/ -q` 全量通过（**894 passed, 1 skipped, 9 deselected**；retrieve/ycb/registry/sim_config 既有用例零回归）