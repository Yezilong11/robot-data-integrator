# Tasks

> 依据 `spec.md`。文件冲突组：`retrieve_data.py`（Task 1 独占）、`ycb.py`（Task 2 独占）、`registry.py+组装层`（Task 3 独占）——三块互不冲突，可并行。Task 4 收口。

## A 多源预算共享软 deadline

- [x] Task 1: retrieve_data.py 预算改共享软 deadline（文件独占）
  - [x] 1.1 新增纯函数 `_compute_source_cap(source_budget, deadline, now) -> float`（L152-159），源循环前初始化 `deadline = time.monotonic() + settings.per_req_timeout`（L469-471）
  - [x] 1.2 每源 `per_source_cap = _compute_source_cap(...)`；`<=0` 跳过该源并向 search_failures 追加"预算耗尽：总预算已到点"诊断；超时文案改为 `本源上限 {source_budget:.2f}s / 剩余 {remaining:.2f}s`（L592-593，无既有断言依赖旧文案）
  - [x] 1.3 需求级 `per_req_timeout` 外层包裹不变；success/missing/error 判定不变
  - [x] 1.4 单测（test_retrieve_data.py +2）：纯函数覆盖快源释放/剩余收紧/总预算到点（cap=0）；集成级断言慢源被本源上限超时中止后后续 Zenodo 源继续执行成功且文案含上限/剩余

## B 场景组装接线

- [x] Task 2: 组装层注入兄弟需求路径（先核实架构，再接线；`registry.py` + 组装调用方）
  - [x] 2.1 架构核实：parse_convert.py 第二遍循环（L283-307）专门处理 SIM_CONFIG 项，第一遍非 SIM_CONFIG 项累积于节点局部 `parsed_data`，兄弟 ParsedItem 同函数调用内可达；`ParsedItem.output_path` 存在
  - [x] 2.2 结论：**接线已存在**——`_build_sim_config_context`（L117-145）已取同批次 ROBOT_URDF 项 output_path 为 `urdf_path`、构造 `objects/{req_id}.stl` 为 `mesh_path`（D4 相对路径修正，比 spec 字面引用更正确）；无兄弟需求零注入。按 ponytail 不改已正确接线的生产代码（registry/parse_convert/sim_config 仅读）
  - [x] 2.4 单测补 3 条：SimConfigSkill `_fallback_to_mjcf(urdf_path, mesh_path)` 引用临时 urdf/mesh 路径（如实锁定：generate_minimal_mjcf 仅写路径引用不读文件内容）；registry context 透传 urdf_path/mesh_path 两条（含无 context 零注入）

## C ycb cup↔mug 语义别名

- [x] Task 3: ycb.py search 语义别名（文件独占）
  - [x] 3.1 确认 `_FALLBACK_OBJECTS` 含 025_mug（title "Mug"）与 search token 匹配逻辑
  - [x] 3.2 新增 `_SEMANTIC_ALIASES = {"cup": "mug"}` + `_normalize_terms`（小写/分词/别名双向归一，query 与条目共用）；`_search_fallback` 由纯子串判定改为 token 交集判定（顺带修复多词 query 无法命中 fallback 的问题）
  - [x] 3.3 别名声仅命中判定：返回 025_mug 不变；无匹配仍抛 AdapterCatalogError 含"仅收录"
  - [x] 3.4 单测（tests/unit/adapters/test_ycb.py +4）："YCB cup mesh"命中 025_mug 且 title=="Mug"；单词 "cup" 命中；"saucer"（无别名）不误命中抛"仅收录"；"teapot" 抛"仅收录"

## 回归

- [x] Task 4: 定向 + 全量回归（依赖 Task 1-3）
  - [x] 4.1 定向 `test_retrieve_data.py test_ycb.py test_registry.py test_sim_config.py` → 96 passed
  - [x] 4.2 `uv run pytest tests/ -q` → **894 passed, 1 skipped, 9 deselected**（新增 9 项；既有 retrieve/ycb/registry/sim_config 用例零回归）

# Task Dependencies

- [Task 4] 依赖 [Task 1/2/3]
- [Task 2] 内部 2.1 先核实、2.2/2.3 二选一

# 并行执行建议

- Task 1（retrieve_data.py）与 Task 2（registry+组装层）与 Task 3（ycb.py）三块独立并行
- Task 4 收口