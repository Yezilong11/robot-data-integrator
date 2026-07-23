# 5.5 能力执行层（Skills）Spec

## Why

5.1 流程编排层、5.4 数据连接层（14 个 Adapter）已就绪，但 `parse_convert` 节点仍是占位实现（[src/rdi/graph/nodes/parse_convert.py](file:///d:/robot-data-integrator2/src/rdi/graph/nodes/parse_convert.py) 构造假 `ParsedItem`）。`src/rdi/skills/` 目录除空 `__init__.py` 外没有任何 Skill 代码。人员 D 需要补齐 6 类异构数据处理 Skill，把 Adapter 取回的原始字节（`RawData.data`）解析 → 标准化为中间表示 → 校验，产出可被打包/校验引擎消费的 `ParsedItem`。

本 spec 严格依据 `E:\数据收集\data2\sources\` 中**实际采集到的数据格式**设计，确保每个 Skill 能在真实样本上跑通，而非纸面方案。

## 真实数据现状（决定设计的关键事实）

| 数据类 | 实际格式 | 关键约束 |
|--------|---------|---------|
| 机器人描述 | Allegro 有纯 `.urdf`；Franka/Robotiq **仅 `.xacro`**（需 ROS/xacro 才能展开宏） | `xacro` 未安装 → xacro 输入走降级路径 |
| 3D Mesh | Franka `.stl`+`.dae`；Google Scanned `model.obj`+`.mtl`+`.sdf`+`metadata.pbtxt`；YCB 嵌套目录 | trimesh 可统一加载 STL/OBJ/PLY/DAE |
| 抓取姿态 | GraspNet `*_labels.npz`（键 `points`/`offsets`/`collision`/`scores`，形状 N×300×12×4）；DexGraspNet `.pkl`（pickle 引用 `graspnetAPI` 类） | `graspnetAPI` 未安装 → DexGraspNet 走降级；GraspNet 用 numpy 直接解 |
| 仿真配置 | MuJoCo `.xml`（MJCF，含 `<mujoco>/<worldbody>/<geom>/<camera>/<joint>`）；Isaac 为 `.py`/`.yaml`（IsaacLab Python API，非 USD） | `pxr`/USD 未安装 → Isaac 仅做描述性解析 |
| 策略模型 | 10 个 HF 模型目录中 **9 个仅含元数据**（`model_info.json`+`weight_files.json`，远端 `.ckpt` size_bytes=0）；仅 1 个有真实 `model.safetensors`，1 个有 `.onnx` | 必须支持「元数据模式」与「权重解析模式」双路径 |
| 传感器数据 | **无 `.bag` 文件**；CSV/JSON 为主（`rosbag` 未安装） | 以 CSV/JSON 时间序列对齐为主，bag 为可选降级 |

可用依赖（`pyproject.toml` 已声明）：`trimesh`、`lxml`、`numpy`、`scipy`、`pymupdf`、`PyYAML`。**未声明且本 spec 不强制新增**：`safetensors`、`onnx`、`graspnetAPI`、`rosbag`、`pxr`、`xacro` —— 一律 `try/except ImportError` 降级。

## What Changes

- 新增 `src/rdi/skills/base.py`：`BaseSkill` 抽象基类（`process` / `validate` 契约）
- 新增 `src/rdi/skills/urdf_convert.py`：`URDFSkill` + 中间表示 `CanonicalRobot`/`Link`/`Joint`
- 新增 `src/rdi/skills/mesh_process.py`：`MeshSkill`（标准化产物即 `trimesh.Trimesh`，无需自定义中间表示）
- 新增 `src/rdi/skills/grasp_parse.py`：`GraspSkill` + 中间表示 `CanonicalGrasp` + `DATASET_CONVENTIONS`
- 新增 `src/rdi/skills/sim_config.py`：`SimConfigSkill` + 中间表示 `SceneDescription`/`SceneObject`/`Camera`
- 新增 `src/rdi/skills/policy_interface.py`：`PolicyInterfaceSkill` + 接口文档模型 `PolicyInterfaceDoc`
- 新增 `src/rdi/skills/sensor_data.py`：`SensorDataSkill` + 中间表示 `SensorDataset`
- 新增 `src/rdi/skills/registry.py`：`SkillRegistry`，按 `DataReqType` 分发到对应 Skill
- 修改 `src/rdi/skills/__init__.py`：导出全部 Skill 与中间表示
- **MODIFIED** `src/rdi/models/common.py`：`StandardResult` 新增 `data: Any = None` 字段（承载内存中的中间表示对象，供 `parse_convert` 节点装配 `ParsedItem.data` 与校验引擎读取）
- **MODIFIED** `src/rdi/graph/nodes/parse_convert.py`：用 `SkillRegistry` 替换占位逻辑，按 `req_type` 分发调用 Skill，装配真实 `ParsedItem`
- 新增 `tests/unit/skills/sample_data/` 下各 Skill 的小型样本（从 `E:\数据收集\data2` 拷贝裁剪，测试自包含，不依赖 E: 盘）
- 新增 `tests/unit/skills/` 下 6 个 Skill + base + registry 的单元测试

## 边界说明

- **不实现 `PDFParseSkill`**：论文解析属于 5.2 目标解析节点（B 工程师）范畴，已由 `parse_goal` 节点用 PyMuPDF 临时处理。本 spec 的 6 类 = URDF / Mesh / Grasp / SimConfig / Policy / Sensor。
- **不实现 `validation_engine.py`**：校验规则引擎属 E 工程师 W6 任务。但本 spec 定义的中间表示（`CanonicalRobot.joints[].limit_lower/upper`、`Link.mass/inertia`、`CanonicalGrasp.position`、`SceneDescription.objects`、`trimesh.Trimesh.is_watertight/faces`）**必须暴露 E 的校验规则所需的属性**，作为跨模块接口约定。
- **不新增重量级依赖**：所有可选第三方库走 `try/except ImportError` 降级，保持 `pyproject.toml` 核心依赖不变、CI 可在无 ROS/无 GPU 环境运行。
- **Skill 不直接调用外部 API**：输入仅为 `bytes`（来自 `RawData.data`），符合开发规范「节点内部不直接调用外部 API，必须通过 Adapter 或 Skill」。

## Impact

- **Affected specs**：
  - 5.1 流程编排层（`parse_convert` 节点从占位变为真实分发）
  - 5.6 整合输出层（E 的打包模块将消费 Skill 产出的 `ParsedItem`）
  - 校验规则引擎（E，依赖本 spec 中间表示的属性契约）
- **Affected code**：
  - `src/rdi/models/common.py` — `StandardResult` 加字段
  - `src/rdi/skills/*` — 全部新建
  - `src/rdi/graph/nodes/parse_convert.py` — 接入 `SkillRegistry`
  - `tests/unit/skills/*` — 全部新建

## ADDED Requirements

### Requirement: BaseSkill 抽象基类

系统 SHALL 提供 `BaseSkill` 抽象基类，约定每个 Skill 实现 `process(data, **kwargs) -> StandardResult` 与 `validate(result) -> ValidationReport`，处理失败时返回降级结果而非抛异常中断流程。

#### Scenario: 处理成功
- **WHEN** 调用 `skill.process(data_bytes)` 且数据可解析
- **THEN** 返回 `StandardResult(success=True, canonical_format=..., output_path=..., data=<中间表示对象>)`，`warnings` 为空或包含非阻断提示

#### Scenario: 处理失败降级
- **WHEN** 数据格式无法解析（如损坏的 STL、无法 unpickle 的 pkl）
- **THEN** 返回 `StandardResult(success=False, errors=[...])`，**不抛异常**，`data=None`

#### Scenario: 大文件流式处理
- **WHEN** 输入数据较大（如 800MB 的 GraspNet npz）
- **THEN** Skill 使用按需加载（`np.load` 懒加载 + 切片读取），不一次性把全部内容载入内存

### Requirement: StandardResult 承载中间表示对象

`StandardResult` SHALL 新增 `data: Any = None` 字段，承载 Skill 处理后的内存中间表示对象（如 `CanonicalRobot`、`trimesh.Trimesh`），供 `parse_convert` 节点装配 `ParsedItem.data` 与校验引擎读取。

#### Scenario: 装配 ParsedItem
- **WHEN** `parse_convert` 节点拿到 `StandardResult(success=True, data=canonical_obj)`
- **THEN** 节点构造 `ParsedItem(data=canonical_obj, output_path=result.output_path, canonical_format=result.canonical_format, ...)`

#### Scenario: 降级时 data 为空
- **WHEN** `StandardResult(success=False)`
- **THEN** `data=None`，节点据此构造 `MissingItem` 或带 warning 的 `ParsedItem`

### Requirement: URDFSkill — 机器人描述文件解析

系统 SHALL 提供 `URDFSkill`，将 URDF/MJCF/SDF 解析为中间表示 `CanonicalRobot`（含 `links`/`joints`，每个 `Joint` 暴露 `limit_lower`/`limit_upper`/`name`/`type`，每个 `Link` 暴露 `name`/`mass`/`inertia`/`origin_xyz`），并校验物理一致性。

#### Scenario: 解析纯 URDF 成功
- **WHEN** 输入为 `allegro_hand_r.urdf` 的字节内容
- **THEN** 返回 `CanonicalRobot`，`links`/`joints` 非空，`canonical_format="CanonicalRobot"`

#### Scenario: xacro 输入降级
- **WHEN** 输入为 `.xacro` 文件（如 `fr3.urdf.xacro`）且 `xacro` 模块不可用
- **THEN** 不抛异常，返回 `StandardResult(success=False, errors=["xacro 展开需要 ROS xacro 模块"])`，`warnings` 提示用户改用已展开的 URDF

#### Scenario: 关节限位非法
- **WHEN** 某 `Joint` 的 `limit_lower >= limit_upper`
- **THEN** `validate` 返回的 `ValidationReport` 含 ERROR 级 `ValIssue`，`process` 的 `warnings` 也记录该问题

#### Scenario: 惯性张量非正定
- **WHEN** 某 `Link.inertia` 矩阵非正定
- **THEN** `validate` 返回 ERROR 级 `ValIssue`，`process` 仍返回 `success=True` 但 `confidence_score<1.0` + `warnings` 标注

#### Scenario: 总质量不合理
- **WHEN** 所有 `Link.mass` 之和 ≤ 0 或 > 200
- **THEN** `validate` 返回 ERROR 级 `ValIssue`

### Requirement: MeshSkill — 3D 几何数据处理

系统 SHALL 提供 `MeshSkill`，用 `trimesh` 将 STL/OBJ/PLY/DAE 统一加载为 `trimesh.Trimesh`，标准化坐标系（原点移到质心、单位统一为米），生成多精度版本。

#### Scenario: 加载 STL 成功
- **WHEN** 输入为 Franka `link0.stl` 的字节
- **THEN** 返回 `trimesh.Trimesh` 对象，`data.is_watertight` 可读，`canonical_format="trimesh.Trimesh"`

#### Scenario: 加载 OBJ + 材质
- **WHEN** 输入为 Google Scanned `model.obj` 字节（含 `.mtl` 引用）
- **THEN** trimesh 加载成功，材质缺失时记 `warnings` 但 `success=True`

#### Scenario: 毫米→米单位统一
- **WHEN** mesh 的 `extents.max() > 10`（疑似毫米单位）
- **THEN** 顶点坐标除以 1000.0，`transformations` 记录 `"unit_mm_to_m"`

#### Scenario: 质心对齐
- **WHEN** 标准化执行
- **THEN** `mesh.vertices -= mesh.center_mass`，`transformations` 记录 `"recenter_to_centroid"`

#### Scenario: 多精度生成
- **WHEN** 调用 `generate_lod(mesh)` 且原 mesh 面数 > 400
- **THEN** 返回 `{"high": <原 mesh>, "collision": <简化至 1/4 面数>}`；面数不足时 `collision` 退化为原 mesh + warning

#### Scenario: 缺面检测
- **WHEN** `mesh.is_watertight == False`
- **THEN** `process` 的 `warnings` 记录面数与孔洞提示，`success` 仍为 True

### Requirement: GraspSkill — 6-DOF 抓取姿态统一

系统 SHALL 提供 `GraspSkill`，将不同数据集的抓取姿态统一为 `CanonicalGrasp`（`position` 米制、`orientation` 四元数 [x,y,z,w]、`width` 米、`score`），通过 `DATASET_CONVENTIONS` 识别数据集约定。

#### Scenario: 解析 GraspNet npz 成功
- **WHEN** 输入为 `*_labels.npz` 字节，`dataset_name="graspnet"`
- **THEN** 用 numpy 直接解 `points`/`offsets`/`scores`/`collision` 键，重构出 `list[CanonicalGrasp]`，单位毫米→米，`canonical_format="CanonicalGrasp"`

#### Scenario: 旋转矩阵→四元数
- **WHEN** 数据集约定 `rotation="matrix"`
- **THEN** 用 `scipy.spatial.transform.Rotation.from_matrix(...).as_quat()` 转为 [x,y,z,w]

#### Scenario: DexGraspNet pkl 降级
- **WHEN** 输入为 DexGraspNet `.pkl` 且 `graspnetAPI` 不可用导致 unpickle 失败
- **THEN** 返回 `StandardResult(success=False, errors=["DexGraspNet pkl 需要 graspnetAPI 才能反序列化"])`，不抛异常

#### Scenario: 抓取点超出工作空间
- **WHEN** 某 `CanonicalGrasp.position` 任一分量绝对值 > 1.0 米
- **THEN** `validate` 返回 WARNING 级 `ValIssue`，提示检查坐标系约定

#### Scenario: 未知数据集约定
- **WHEN** `dataset_name` 不在 `DATASET_CONVENTIONS` 中
- **THEN** 返回 `success=False` + 错误说明，不猜测约定

### Requirement: SimConfigSkill — 仿真环境配置解析

系统 SHALL 提供 `SimConfigSkill`，将 MuJoCo MJCF XML 解析为中间表示 `SceneDescription`（含 `objects: list[SceneObject]`、`cameras: list[Camera]`），Isaac USD/Python 配置走描述性降级。

#### Scenario: 解析 MJCF 成功
- **WHEN** 输入为 `cube_3x3x3.xml` 字节
- **THEN** 返回 `SceneDescription`，`objects` 非空（每个 `SceneObject` 含 `name`/`type`/`pos`/`size`），`cameras` 含 `<camera>` 节点，`canonical_format="SceneDescription"`

#### Scenario: 场景无物体
- **WHEN** 解析后 `scene.objects` 为空
- **THEN** `validate` 返回 WARNING 级 `ValIssue`

#### Scenario: Isaac 配置降级
- **WHEN** 输入为 IsaacLab `.py`/`.yaml` 配置且 `pxr` 不可用
- **THEN** 不抛异常，返回 `StandardResult(success=True, confidence_score<1.0, warnings=["Isaac 配置仅做描述性解析，未生成 USD"])`，从 YAML/文本提取可识别的场景要素

#### Scenario: MJCF 生成（反向）
- **WHEN** 调用 `to_mjcf(scene: SceneDescription)`
- **THEN** 返回合法 MJCF XML 字节，含 `<mujoco>/<worldbody>/<geom>` 结构

### Requirement: PolicyInterfaceSkill — 策略模型接口标准化

系统 SHALL 提供 `PolicyInterfaceSkill`，自动检测框架（`.pt`/`.pth`/`.safetensors`/`.onnx`/`.ckpt`），在有权重文件时解析结构、在仅元数据时从 `model_info.json`/`weight_files.json`/`config.json`/README 生成标准化接口文档 `PolicyInterfaceDoc`。

#### Scenario: 真实 safetensors 权重
- **WHEN** 输入目录含 `model.safetensors` 且 `safetensors` 模块可用
- **THEN** 读取 tensor keys/shapes，`PolicyInterfaceDoc.framework="safetensors"`，`layers` 列出权重名与形状，`canonical_format="PolicyInterfaceDoc"`

#### Scenario: 元数据-only 目录
- **WHEN** 输入目录仅含 `model_info.json`+`weight_files.json`（远端权重 size_bytes=0）
- **THEN** 从 `weight_files.json` 提取 `filename`/`download_url`，从 `model_info.json` 提取 `tags`/`modelId`，`PolicyInterfaceDoc.framework` 标注为推断值，`confidence_score<1.0`，`warnings` 标注「权重未本地化，接口为推断」

#### Scenario: onnx 模型
- **WHEN** 输入含 `.onnx` 且 `onnx` 模块可用
- **THEN** 解析输入/输出节点；`onnx` 不可用时降级为仅记录文件名 + warning

#### Scenario: 未知框架
- **WHEN** 文件扩展名不在支持列表
- **THEN** 返回 `success=False` + 错误说明

### Requirement: SensorDataSkill — 传感器与实验数据对齐

系统 SHALL 提供 `SensorDataSkill`，对 CSV/JSON 时间序列提取关键指标、对齐时间戳到最大公共采样率、统一坐标系；ROS bag 走可选降级。

#### Scenario: CSV 时间序列对齐
- **WHEN** 输入为关节角度 CSV 字节（含 `timestamp` 列与若干数据列）
- **THEN** 返回 `SensorDataset`，含对齐后的时间戳数组与各指标数组，`canonical_format="SensorDataset"`

#### Scenario: 多源采样率统一
- **WHEN** 两路数据采样率不同
- **THEN** 统一到最大公共采样率（线性插值），`transformations` 记录 `"resample_to_<hz>Hz"`

#### Scenario: ROS bag 降级
- **WHEN** 输入为 `.bag` 且 `rosbag` 不可用
- **THEN** 返回 `success=False, errors=["ROS bag 解析需要 rosbag 模块"]`，不抛异常

#### Scenario: 缺失时间戳列
- **WHEN** CSV 无 `timestamp`/`time` 列
- **THEN** 用行号生成单调递增时间戳 + warning，`confidence_score<1.0`

### Requirement: SkillRegistry — 按 req_type 分发

系统 SHALL 提供 `SkillRegistry`，维护 `DataReqType → BaseSkill` 映射，提供 `get_skill(req_type)` 与 `process_retrieval_result(result) -> ParsedItem | MissingItem` 便捷方法。

#### Scenario: 已注册类型分发
- **WHEN** `get_skill(DataReqType.MESH)` 调用
- **THEN** 返回 `MeshSkill` 单例

#### Scenario: 未注册类型
- **WHEN** `get_skill(DataReqType.PAPER)`（论文不在 6 类 Skill 范围）
- **THEN** 返回 `None`，`parse_convert` 节点跳过该需求并记 warning

#### Scenario: 端到端装配 ParsedItem
- **WHEN** `process_retrieval_result(retrieval_result)` 且 Skill 处理成功
- **THEN** 返回 `ParsedItem`，`data`/`output_path`/`canonical_format`/`provenance`/`completeness_pct`/`confidence_score`/`warnings` 全部来自 `StandardResult` + `RawData`

## MODIFIED Requirements

### Requirement: StandardResult 数据契约

`StandardResult`（[src/rdi/models/common.py](file:///d:/robot-data-integrator2/src/rdi/models/common.py)）新增可选字段以承载中间表示对象：

```python
data: Any = Field(default=None, description="处理后的内存中间表示对象（CanonicalRobot/Trimesh/...），供节点装配 ParsedItem 与校验引擎读取")
```

该改动向后兼容（默认 `None`），不破坏现有 Adapter/Hermes 对 `StandardResult` 的使用。

### Requirement: parse_convert 节点真实分发

`node_parse_convert`（[src/rdi/graph/nodes/parse_convert.py](file:///d:/robot-data-integrator2/src/rdi/graph/nodes/parse_convert.py)）SHALL 用 `SkillRegistry` 替换占位逻辑：

1. 遍历 `retrieval_results`，对每个 `RetrievalResult`
2. 由 `result.data.format` 或需求 `req_type` 决定 Skill
3. 调用 `skill.process(result.data.data, ...)` 获取 `StandardResult`
4. 成功 → 装配 `ParsedItem`（含 `provenance`，从 `RawData` 继承 source/url/retrieved_at/original_format，追加 `transformations`）
5. 失败 → 装配 `MissingItem`（带 `reason` + `fallback_sources`）
6. 追加 `provenance` 日志，标注真实 Skill 名与处理结果

## REMOVED Requirements

无。本 spec 为纯新增 + 两处向后兼容修改。
