# Tasks

> 依据 `spec.md`。文件冲突组：`kinova.py`（Task 1 独占）、`sim_config.py`（Task 2 独占）、`isaac.py`（Task 3 独占）——三个文件互不冲突，可并行。

## kinova 资产缺失显性化

- [x] Task 1: kinova `_download_assets` 与本地路径资产缺失透传
  - [x] 1.1 对齐 base.py `_download_xml_with_assets`/`_local_assets_from_xml` 的 assets_missing 元数据键与形态（键名 `metadata["assets_missing"]`，list[str] 引用路径）
  - [x] 1.2 `kinova.fetch` 网络分支：`_download_assets` 改为返回 `(assets, missing)`，缺失清单写入 `RawData.metadata["assets_missing"]`（无缺失不写键）；本地分支由 base `_local_assets_from_xml` 既有 R3 逻辑覆盖，两条路径行为一致
  - [x] 1.3 全部成功无 assets_missing，行为不变；无新依赖

- [x] Task 2: kinova 资产单测（新建 `tests/unit/adapters/test_kinova_assets.py`）
  - [x] 2.1 网络部分失败 → assets_missing 含缺失清单、成功资产仍入 assets
  - [x] 2.2 全部成功 → 无 assets_missing 键
  - [x] 2.3 本地挂载缺 mesh（tmp_path 镜像 + monkeypatch local_datasets）→ assets_missing 同样产生且无网络调用

## isaac 收录与降级诚实化

- [x] Task 3: sim_config 降级产物语义诚实标记（新建 `tests/unit/skills/test_sim_config_honesty.py`）
  - [x] 3.1 确认降级结果结构；落点选定 `StandardResult.warnings`（ParsedItem/StandardResult 均 extra=forbid，warnings 是唯一不破坏序列化的现成通道）
  - [x] 3.2 新增 `DEGRADED_SCENE_NOTE`，`_fallback_to_mjcf` 的 warnings 追加；直通/重建分支无标记
  - [x] 3.3 8 条单测：python/解析失败/未知降级含标记；mjcf/xml 直通与重建无标记；registry 透传；validate 产生独立 WARNING（issue_type=degraded_scene）且不误报占位 ERROR
  - [x] 3.4 validate.py 新增 `_sim_config_degraded_scene`，带标记项经既有 warning 通道呈现

- [x] Task 4: IsaacLab 收录存在性核实（先核实，后按结果编码）
  - [x] 4.1 实证：本地挂载为零；GitHub API contents（release/3.0.0-beta2）200 返回 28 文件清单；raw 逐候选——ur5/ur5e/ur10/ur16e 等 404/ReadError，**UR5/UR5e 确定不存在**；真实存在 `universal_robots.py`（UR10/UR10e，7265B 实证）、`kinova.py`（Gen3 7-Dof/Jaco2，5831B 实证）
  - [x] 4.2 补录真实存在条目：`universal_robots`（UR10/UR10e）、`kinova`（Gen3/Jaco2），id 与 fetch URL `robots/{id}.py` 对齐；新增 2 条 search 单测（ur10/kinova gen3 命中），未知 query 仍抛 AdapterCatalogError
  - [x] 4.3 UR5/UR5e 如实挂账不补收录（不虚构）
  - [x] 4.4 SIM_CONFIG 语义错配回退单测：req 含 'ur5' vs ParsedItem franka（SIM_CONFIG）→ 检出 content_validity ERROR，与 GRASP/MESH/ROBOT_URDF 一致；`SIM_CONFIG` 已在 `_SEMANTIC_REQ_TYPES` 启用（未改动集合）

## 回归

- [x] Task 5: 定向 + 全量回归（依赖 Task 1-4）
  - [x] 5.1 定向 `-k "semantic or sim_config or kinova or isaac"` → 95 passed
  - [x] 5.2 `uv run pytest tests/ -q` → **885 passed, 1 skipped, 9 deselected**（644s；新增 14 项用例，既有 kinova/isaac/mujoco/sim_config/validate 用例零回归）

# Task Dependencies

- [Task 2] 依赖 [Task 1]
- [Task 5] 依赖全部
- [Task 3]、[Task 4] 文件块独立，可与 [Task 1/2] 并行

# 并行执行建议

- 文件块 A：Task 1→2（kinova.py）
- 文件块 B：Task 3（sim_config.py）
- 文件块 C：Task 4（isaac.py + 核实 + 单测）
- 三块并行，Task 5 收口