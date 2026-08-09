# 第二次联调 Tasks

> 依据：[spec.md](./spec.md) 与 [第二次联调技术指导文档](../../../documents/second-integration-technical-guide.md)

- [x] Task 1: 实现 `CODE` 与 `DATASET` Skill
  - [x] SubTask 1.1: 创建 `src/rdi/skills/code_parse.py`，支持 markdown/json/zip/tar 输入，输出 `CodeRepoSummary`
  - [x] SubTask 1.2: 创建 `src/rdi/skills/dataset_parse.py`，支持 json/tar/zip 输入，输出 `DatasetSummary`
  - [x] SubTask 1.3: 在 `src/rdi/skills/registry.py` 注册 `DataReqType.CODE → CodeSkill` 与 `DataReqType.DATASET → DatasetSkill`
  - [x] SubTask 1.4: 更新 `tests/unit/skills/test_code_parse.py` 与 `tests/unit/skills/test_dataset_parse.py`

- [x] Task 2: 修复真实 URDF 来源
  - [x] SubTask 2.1: 修改 `src/rdi/adapters/franka.py`，返回已展开纯 URDF 字节
  - [x] SubTask 2.2: 同步修改 `src/rdi/adapters/allegro.py` 与 `src/rdi/adapters/robotiq.py`
  - [x] SubTask 2.3: 调整 `src/rdi/adapters/registry.py` 中 `ROBOT_URDF` 候选顺序，将 MuJoCo/Isaac 从 URDF 源移除或移到 SIM_CONFIG
  - [x] SubTask 2.4: 更新对应单元测试并验证 URDF 可被 `URDFSkill` 解析

- [x] Task 3: 修复真实 Mesh 来源
  - [x] SubTask 3.1: 修改 `src/rdi/adapters/ycb.py`，优先拉取 `.obj`/`.stl` 格式
  - [x] SubTask 3.2: 修复 `src/rdi/adapters/google_scanned.py` 超时问题（减小下载体积、重试、或明确降级）
  - [x] SubTask 3.3: 修改 `src/rdi/adapters/graspnet.py` 与 `src/rdi/adapters/dexgrasp.py`，按 `DataReqType` 返回单个文件或 metadata
  - [x] SubTask 3.4: 更新对应单元测试并验证 mesh 可被 `trimesh.load` 加载

- [x] Task 4: 优化目标解析中的 DataReq 类型识别
  - [x] SubTask 4.1: 修改 `src/rdi/intelligence/prompts/goal_parsing.py`，增加 few-shot 示例，明确 `robot_urdf`/`mesh`/`grasp`/`sim_config` 与 `code`/`dataset` 的区分
  - [x] SubTask 4.2: 修改 `src/rdi/graph/nodes/parse_goal.py`，根据 `expected_format` 或关键词对误识别的 `code`/`dataset` 进行后处理强制映射
  - [x] SubTask 4.3: 修改 `src/rdi/graph/nodes/retrieve_data.py`，按 `fallback_sources` 顺序尝试源
  - [x] SubTask 4.4: 更新 `tests/unit/graph/nodes/test_parse_goal.py` 与 `test_retrieve_data.py`

- [x] Task 5: 增强 Skill 格式兼容性
  - [x] SubTask 5.1: 在 `src/rdi/skills/urdf_convert.py` 中增加 xacro 字符串级降级处理
  - [x] SubTask 5.2: 在 `src/rdi/skills/mesh_process.py` 中增加 `glb` 与 `zip` 支持
  - [x] SubTask 5.3: 更新对应单元测试，使用 `tests/unit/skills/sample_data/` 中的样本

- [x] Task 6: 实现格式深度校验
  - [x] SubTask 6.1: 修改 `src/rdi/graph/nodes/validate.py`，对 URDF 使用 `urdfpy`/`yourdfpy` 解析
  - [x] SubTask 6.2: 对 mesh 使用 `trimesh.load` 校验
  - [x] SubTask 6.3: 对 sim_config 使用 XML/Python 语法校验
  - [x] SubTask 6.4: 对 grasp 检查 npz/pkl 必要字段
  - [x] SubTask 6.5: 新增集成测试覆盖校验路径

- [x] Task 7: 跑通端到端真实场景并生成数据包样例
  - [x] SubTask 7.1: 使用目标 "Franka Panda grasps YCB banana in MuJoCo simulation" 运行完整工作流
  - [x] SubTask 7.2: 验证输出包包含至少两类真实文件，且至少一个 URDF 可解析、一个 mesh 可加载
  - [x] SubTask 7.3: 运行 `scripts/_probe_adapters.py` 确认 13/15 以上 fetch 成功
  - [x] SubTask 7.4: 运行 `uv run pytest` 全绿

- [x] Task 8: 编写第二次联调报告
  - [x] SubTask 8.1: 创建 `docs/second_integration_report.md`，记录完成项、未决问题、风险与下一步计划

# Task Dependencies

- Task 4 depends on Task 1（目标解析需要知道 CODE/DATASET Skill 已存在）
- Task 5 depends on Task 2 and Task 3（Skill 兼容性兜底基于 Adapter 修复后的格式）
- Task 6 depends on Task 1, Task 2, Task 3, Task 5（深度校验需要真实文件格式已对齐）
- Task 7 depends on Task 1, Task 2, Task 3, Task 4, Task 5, Task 6（端到端依赖前面所有任务）
- Task 8 depends on Task 7（报告基于实际运行结果）
