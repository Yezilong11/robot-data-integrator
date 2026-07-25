# Tasks

> 落地 5.5 能力执行层 6 类 Skill。任务 1 为地基，任务 2-7 可并行，任务 8 串联节点，任务 9 收口验证。
> 样本数据原则：从 `E:\数据收集\data2\sources\` 拷贝**小型**代表文件到 `tests/unit/skills/sample_data/`，测试自包含、不依赖 E: 盘、不打真实 API。

- [x] Task 1: 搭建 Skill 地基（BaseSkill + StandardResult 字段 + 中间表示契约 + skills 包导出）
  - [x] SubTask 1.1: 修改 `src/rdi/models/common.py`，给 `StandardResult` 加 `data: Any = Field(default=None, ...)` 字段，补 docstring
  - [x] SubTask 1.2: 新建 `src/rdi/skills/base.py`，实现 `BaseSkill` ABC（`process`/`validate` 抽象方法 + `skill_name` 约定 + docstring 说明降级原则）
  - [x] SubTask 1.3: 新建 `src/rdi/skills/__init__.py` 占位导出（先导出 `BaseSkill`，后续 Task 逐步补充 6 个 Skill 与中间表示）
  - [x] SubTask 1.4: 新建 `tests/unit/skills/__init__.py` 与 `tests/unit/skills/test_base.py`，验证 `StandardResult.data` 默认 None、`BaseSkill` 不可实例化

- [x] Task 2: URDFSkill — 机器人描述文件解析
  - [x] SubTask 2.1: 在 `src/rdi/skills/urdf_convert.py` 定义中间表示 `CanonicalRobot`/`Link`/`Joint`（dataclass，暴露 `Joint.limit_lower/limit_upper/name/type`、`Link.name/mass/inertia/origin_xyz`）
  - [x] SubTask 2.2: 实现 `URDFSkill.parse(urdf_bytes) -> CanonicalRobot`：用 `lxml` 解析 URDF，提取 link/joint/inertial
  - [x] SubTask 2.3: 实现 `validate_physics(robot)`：惯性张量正定性（numpy 特征值）、关节限位 lower<upper、总质量 0~200kg
  - [x] SubTask 2.4: 实现 `process`/`validate` 契约；xacro 输入走降级（`try: import xacro` 失败 → `success=False` + 错误说明，不抛异常）
  - [x] SubTask 2.5: 拷贝 `allegro_hand_r.urdf`（裁剪至手部子集）与 `fr3.urdf.xacro` 到 `sample_data/urdf/`
  - [x] SubTask 2.6: 写 `tests/unit/skills/test_urdf.py`：纯 URDF 解析成功、关节限位非法报 ERROR、惯性非正定报 ERROR、xacro 降级、转换后关节限位不变（数据完整性）

- [x] Task 3: MeshSkill — 3D 几何数据处理（可与 Task 2 并行）
  - [x] SubTask 3.1: 实现 `MeshSkill.parse(bytes, fmt) -> trimesh.Trimesh`：支持 stl/obj/ply/dae，`trimesh.load(BytesIO(...), file_type=fmt)`
  - [x] SubTask 3.2: 实现 `standardize(mesh)`：质心对齐（`vertices -= center_mass`）+ 毫米→米（`extents.max()>10` 时除 1000），记录 transformations
  - [x] SubTask 3.3: 实现 `generate_lod(mesh)`：`simplify_quadric_decimation(face_count//4)`，面数不足时退化 + warning
  - [x] SubTask 3.4: 实现 `process`/`validate` 契约：`is_watertight==False` → warning；面数<100 → warning
  - [x] SubTask 3.5: 拷贝 Franka `link0.stl`（或更小的 `hand.stl`）与 Google Scanned `model.obj`+`model.mtl` 到 `sample_data/mesh/`
  - [x] SubTask 3.6: 写 `tests/unit/skills/test_mesh.py`：STL 加载、质心对齐结果正确、毫米→米转换正确、缺面 warning、OBJ 材质缺失 warning

- [x] Task 4: GraspSkill — 6-DOF 抓取姿态统一（可与 Task 2/3 并行）
  - [x] SubTask 4.1: 在 `src/rdi/skills/grasp_parse.py` 定义 `CanonicalGrasp`（dataclass：`position: np.ndarray`、`orientation: np.ndarray` [x,y,z,w]、`width: float`、`score: float`）与 `DATASET_CONVENTIONS`（graspnet/dexgraspnet/ycb/abdataset 四条约定）
  - [x] SubTask 4.2: 实现 GraspNet npz 解码：`np.load` 读 `points/offsets/scores/collision`，按 GraspNet-1Billion 约定重构平移+旋转，毫米→米，旋转矩阵→四元数（scipy）
  - [x] SubTask 4.3: 实现通用 `standardize(raw_grasps, dataset_name)`：按 `DATASET_CONVENTIONS` 分支处理旋转表示/坐标系原点/单位
  - [x] SubTask 4.4: 实现 `process`/`validate` 契约：DexGraspNet pkl 在 `graspnetAPI` 不可用时降级；未知 dataset_name 报错；位置 >1m 报 WARNING
  - [x] SubTask 4.5: 构造小型 GraspNet npz 样本（从 `000_labels.npz` 切片前 N 个点生成 <1MB 的样本）放到 `sample_data/grasp/`
  - [x] SubTask 4.6: 写 `tests/unit/skills/test_grasp.py`：GraspNet 解析、单位转换、四元数顺序 [x,y,z,w]、DexGraspNet 降级、未知约定报错

- [x] Task 5: SimConfigSkill — 仿真环境配置解析（可与 Task 2/3/4 并行）
  - [x] SubTask 5.1: 在 `src/rdi/skills/sim_config.py` 定义 `SceneDescription`/`SceneObject`/`Camera`（dataclass，`SceneObject` 含 `name/type/pos/size`，`SceneDescription.objects` 暴露给校验引擎）
  - [x] SubTask 5.2: 实现 `parse_mujoco(xml_bytes) -> SceneDescription`：lxml 解析 `<geom>`/`<camera>`/`<joint>`，`parse_vec3` 辅助
  - [x] SubTask 5.3: 实现 `to_mjcf(scene) -> bytes`：反向生成合法 MJCF XML
  - [x] SubTask 5.4: 实现 `process`/`validate` 契约：Isaac `.py`/`.yaml` 走描述性降级（`pxr` 不可用，从 YAML 提取要素，`confidence<1.0`）；空场景 WARNING
  - [x] SubTask 5.5: 拷贝 `cube_3x3x3.xml`（裁剪）到 `sample_data/sim/`，构造一个最小 Isaac yaml 样本
  - [x] SubTask 5.6: 写 `tests/unit/skills/test_sim_config.py`：MJCF 解析、反向生成 XML 合法、空场景 warning、Isaac 降级

- [x] Task 6: PolicyInterfaceSkill — 策略模型接口标准化（可与 Task 2-5 并行）
  - [x] SubTask 6.1: 在 `src/rdi/skills/policy_interface.py` 定义 `PolicyInterfaceDoc`（Pydantic BaseModel：`framework`/`layers`/`input_spec`/`output_spec`/`weight_files`/`source_url`）
  - [x] SubTask 6.2: 实现框架检测：按扩展名 `.pt/.pth/.safetensors/.onnx/.ckpt` 识别
  - [x] SubTask 6.3: 实现权重解析路径：`try: import safetensors` 读 tensor keys/shapes；`try: import onnx` 读 IO 节点；不可用则降级
  - [x] SubTask 6.4: 实现元数据路径：解析 `model_info.json`/`weight_files.json`/`config.json`/README，提取 `filename`/`download_url`/`tags`/`modelId`
  - [x] SubTask 6.5: 实现 `process`/`validate` 契约：元数据-only 时 `confidence<1.0`+warning；未知扩展名 `success=False`
  - [x] SubTask 6.6: 拷贝 `saic3d_graspnet_ckpt` 目录的元数据 JSON（不含真实权重）到 `sample_data/policy/`；构造一个最小 safetensors 样本（或 mock）
  - [x] SubTask 6.7: 写 `tests/unit/skills/test_policy_interface.py`：元数据路径、框架检测、未知扩展名报错、safetensors 可用时解析（用 `pytest.importorskip`）

- [x] Task 7: SensorDataSkill — 传感器与实验数据对齐（可与 Task 2-6 并行）
  - [x] SubTask 7.1: 在 `src/rdi/skills/sensor_data.py` 定义 `SensorDataset`（dataclass：`timestamps: np.ndarray`、`signals: dict[str, np.ndarray]`、`sample_rate_hz: float`）
  - [x] SubTask 7.2: 实现 CSV 解析：识别 `timestamp`/`time` 列，提取数值列；缺失时间戳用行号 + warning
  - [x] SubTask 7.3: 实现 JSON 解析：支持 `[{timestamp, ...}]` 与 `{signals: {...}}` 两种结构
  - [x] SubTask 7.4: 实现多源时间戳对齐：线性插值到最大公共采样率
  - [x] SubTask 7.5: 实现 `process`/`validate` 契约：`.bag` 在 `rosbag` 不可用时降级
  - [x] SubTask 7.6: 构造小型 CSV/JSON 传感器样本（手写或从 zenodo 提取）放到 `sample_data/sensor/`
  - [x] SubTask 7.7: 写 `tests/unit/skills/test_sensor_data.py`：CSV 对齐、缺失时间戳降级、多源采样率统一、bag 降级

- [x] Task 8: SkillRegistry + parse_convert 节点接入（依赖 Task 1-7）
  - [x] SubTask 8.1: 新建 `src/rdi/skills/registry.py`：`SkillRegistry` 维护 `DataReqType → BaseSkill` 单例映射，实现 `get_skill(req_type)` 与 `process_retrieval_result(result, req) -> ParsedItem | MissingItem`
  - [x] SubTask 8.2: 在 `skills/__init__.py` 导出全部 6 个 Skill、中间表示、`SkillRegistry`
  - [x] SubTask 8.3: 修改 `src/rdi/graph/nodes/parse_convert.py`：用 `SkillRegistry` 替换占位，按 req_type 分发，装配真实 `ParsedItem`（provenance 从 RawData 继承 + 追加 transformations）或 `MissingItem`
  - [x] SubTask 8.4: 写 `tests/unit/skills/test_registry.py`：已注册类型返回正确 Skill、未注册类型返回 None、`process_retrieval_result` 端到端装配
  - [x] SubTask 8.5: 更新 `tests/unit/graph/` 下 parse_convert 相关测试（若有）以反映真实分发

- [x] Task 9: 全量验证与收口
  - [x] SubTask 9.1: `ruff check src/rdi/skills tests/unit/skills` 全绿
  - [x] SubTask 9.2: `ruff format --check src/rdi/skills tests/unit/skills`
  - [x] SubTask 9.3: `mypy src/rdi/skills` 无报错（trimesh/可选依赖已配 `ignore_missing_imports`）
  - [x] SubTask 9.4: `pytest tests/unit/skills -v` 全绿，覆盖率 ≥ 80%
  - [x] SubTask 9.5: `pytest tests/unit/graph/test_parse_convert*`（端到端节点）全绿
  - [x] SubTask 9.6: 人工抽样：用 `E:\数据收集\data2` 真实文件跑一遍各 Skill，确认非占位输出

- [x] Task 10: 修复 spec 缺口 — StandardResult 补 confidence_score 字段（9.6 冒烟测试发现）
  - [x] SubTask 10.1: `src/rdi/models/common.py` 给 `StandardResult` 加 `confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)`，docstring 说明「1.0=直接解析，<1.0=含推断/降级」
  - [x] SubTask 10.2: `urdf_convert.py` process：物理问题（error_count>0）时设 `confidence_score=1.0-0.1*error_count`（下限 0.5），删除 line 240 的 workaround 注释
  - [x] SubTask 10.3: `sim_config.py` Isaac 降级路径设 `confidence_score=0.8`（与 completeness_pct=80.0 对应）
  - [x] SubTask 10.4: `policy_interface.py` `_ok` helper 加 `confidence` 参数，metadata-only 路径传 `confidence<1.0`；权重解析成功传 1.0
  - [x] SubTask 10.5: `sensor_data.py` 缺时间戳降级路径设 `confidence_score=0.7`（与 completeness=70.0 对应）
  - [x] SubTask 10.6: `registry.py` 删除 `completeness_pct<100` 推断逻辑，改为直接 `confidence=res.confidence_score` 传播到 `ProvenanceEntry` 与 `ParsedItem`；`is_inferred = res.confidence_score < 1.0`
  - [x] SubTask 10.7: 更新对应单测：URDF 非正定惯性、SimConfig Isaac 降级、Policy 元数据-only、Sensor 缺时间戳 四处断言 `result.confidence_score < 1.0`；正常路径断言 `== 1.0`
  - [x] SubTask 10.8: 重跑 ruff/mypy/pytest 全绿，覆盖率不降

# Task Dependencies

- Task 1 是地基，必须最先完成
- Task 2 / 3 / 4 / 5 / 6 / 7 互相独立，可并行（均仅依赖 Task 1）
- Task 8 依赖 Task 1-7 全部完成（需要 6 个 Skill 才能注册）
- Task 9 依赖 Task 8 完成（需要节点接入后才能跑端到端验证）
