# Checklist — 5.5 能力执行层（Skills）

> 验证每项实现是否满足 spec.md 的要求。全部勾选后方可结束本 spec。

## 地基

- [x] `StandardResult` 新增 `data: Any = None` 字段，默认 None，向后兼容现有 Adapter/Hermes 用法
- [x] `BaseSkill` 为 ABC，定义 `process`/`validate` 抽象方法与 `skill_name` 约定，docstring 说明降级原则
- [x] `BaseSkill` 不可直接实例化（抽象方法阻止）
- [x] `skills/__init__.py` 导出 `BaseSkill` 及后续全部 Skill/中间表示/Registry

## URDFSkill

- [x] `CanonicalRobot`/`Link`/`Joint` 暴露校验引擎所需属性：`Joint.limit_lower/limit_upper/name/type`、`Link.name/mass/inertia/origin_xyz`、`CanonicalRobot.links/joints`
- [x] 纯 URDF（allegro_hand_r.urdf 样本）解析成功，返回非空 `CanonicalRobot`
- [x] 关节限位 `lower >= upper` 时 `validate` 报 ERROR 级 `ValIssue`
- [x] 惯性张量非正定时 `validate` 报 ERROR，`process` 仍 `success=True` 但 `confidence_score<1.0`
- [x] 总质量 ≤0 或 >200kg 时 `validate` 报 ERROR
- [x] xacro 输入在 `xacro` 模块缺失时降级（`success=False` + 错误说明），不抛异常
- [x] 测试覆盖：数据完整性（转换后关节限位不变）

## MeshSkill

- [x] STL/OBJ/PLY/DAE 均能用 trimesh 加载为 `trimesh.Trimesh`
- [x] 标准化执行质心对齐（`vertices -= center_mass`）并记录 `transformations`
- [x] 毫米单位（`extents.max()>10`）自动除 1000 转米，记录 `transformations`
- [x] `generate_lod` 在面数充足时输出 high + collision（1/4 面）双版本，面数不足时退化 + warning
- [x] `is_watertight==False` 时 `process` 记 warning，`success` 仍为 True
- [x] 测试覆盖：质心对齐结果正确、毫米→米转换数值正确

## GraspSkill

- [x] `CanonicalGrasp` 字段：`position`（米）、`orientation` 四元数 [x,y,z,w]、`width`（米）、`score`
- [x] `DATASET_CONVENTIONS` 至少含 graspnet/dexgraspnet/ycb/abdataset 四条约定
- [x] GraspNet npz 用 numpy 直接解 `points/offsets/scores/collision`，毫米→米，旋转矩阵→四元数（scipy 输出 [x,y,z,w]）
- [x] DexGraspNet pkl 在 `graspnetAPI` 不可用时降级，不抛异常
- [x] 未知 `dataset_name` 报错（不猜测约定）
- [x] 位置绝对值 >1m 时 `validate` 报 WARNING
- [x] 测试覆盖：单位转换正确、四元数顺序为 [x,y,z,w]

## SimConfigSkill

- [x] `SceneDescription` 暴露 `objects: list[SceneObject]`、`cameras: list[Camera]`，`SceneObject` 含 `name/type/pos/size`
- [x] MJCF XML（cube_3x3x3.xml 样本）解析成功，`objects` 非空
- [x] `to_mjcf(scene)` 反向生成合法 MJCF XML（含 `<mujoco>/<worldbody>/<geom>`）
- [x] 空场景 `validate` 报 WARNING
- [x] Isaac `.py`/`.yaml` 在 `pxr` 不可用时描述性降级（`confidence<1.0` + warning），不抛异常

## PolicyInterfaceSkill

- [x] `PolicyInterfaceDoc` 含 `framework`/`layers`/`input_spec`/`output_spec`/`weight_files`/`source_url`
- [x] 框架检测覆盖 `.pt/.pth/.safetensors/.onnx/.ckpt`
- [x] 元数据-only 目录（model_info.json + weight_files.json，远端权重 size_bytes=0）能生成接口文档，`confidence<1.0` + warning
- [x] safetensors/onnx 可用时解析结构，不可用时降级（`pytest.importorskip` 守卫测试）
- [x] 未知扩展名 `success=False`

## SensorDataSkill

- [x] `SensorDataset` 含 `timestamps`/`signals`/`sample_rate_hz`
- [x] CSV 含 `timestamp`/`time` 列时正确对齐；缺失时用行号 + warning，`confidence<1.0`
- [x] JSON 两种结构（`[{timestamp,...}]` 与 `{signals:{...}}`）均支持
- [x] 多源采样率不同时线性插值到最大公共采样率
- [x] `.bag` 在 `rosbag` 不可用时降级，不抛异常

## SkillRegistry + 节点接入

- [x] `SkillRegistry.get_skill(req_type)` 对 6 类 req_type 返回正确 Skill 单例
- [x] 未注册 req_type（如 PAPER）返回 None
- [x] `process_retrieval_result` 成功时装配 `ParsedItem`，`data`/`output_path`/`canonical_format`/`provenance`/`completeness_pct`/`confidence_score`/`warnings` 字段齐全
- [x] `provenance` 从 `RawData` 继承 source/url/retrieved_at/original_format 并追加 `transformations`
- [x] 处理失败时装配 `MissingItem`（带 `reason` + `fallback_sources`）
- [x] `parse_convert` 节点不再构造占位 `ParsedItem`，改为真实分发；provenance 日志标注真实 Skill 名

## confidence_score 契约（Task 10 补齐）

- [x] `StandardResult` 新增 `confidence_score: float`（默认 1.0，范围 0~1）
- [x] URDFSkill 物理问题（error_count>0）时 `confidence_score<1.0`
- [x] SimConfigSkill Isaac 降级时 `confidence_score=0.8`
- [x] PolicyInterfaceSkill 元数据-only 时 `confidence_score=0.8`
- [x] SensorDataSkill 缺时间戳时 `confidence_score=0.7`
- [x] GraspSkill 近似旋转路径 `confidence_score=0.7`
- [x] Registry 直接传播 `res.confidence_score` 到 `ProvenanceEntry` 与 `ParsedItem`，不再用 `completeness_pct` 启发式推断

## 边界遵守

- [x] 未实现 `PDFParseSkill`（属 5.2 范围，不在本 spec）
- [x] 未实现 `validation_engine.py`（属 E 工程师 W6），但中间表示属性契约满足其校验规则所需
- [x] 未新增重量级依赖（safetensors/onnx/graspnetAPI/rosbag/pxr/xacro 均走 `try/except ImportError` 降级）
- [x] Skill 不直接调用外部 API，输入仅为 bytes
- [x] 测试样本自包含于 `tests/unit/skills/sample_data/`，不依赖 `E:\数据收集\data2` 路径、不打真实 API

## 质量门禁

- [x] `ruff check src/rdi/skills tests/unit/skills` 全绿
- [x] `ruff format --check src/rdi/skills tests/unit/skills` 全绿
- [x] `mypy src/rdi/skills` 无报错
- [x] `pytest tests/unit/skills -v` 全绿，覆盖率 ≥ 80%（实测 80%，79 tests passed）
- [x] `pytest tests/unit/graph`（parse_convert 节点）全绿（5 tests passed）
- [x] 真实数据冒烟测试：6 类 Skill 在 `E:\数据收集\data2` 真实文件上产出非占位输出（URDF 21 links/20 joints、STL 200 faces、OBJ 20706 faces、MJCF 30 objects、Policy metadata-only confidence=0.8、Grasp/Sensor 降级不崩溃）
- [x] commit message 遵循 Conventional Commits（`feat(skill): ...` / `fix(skill): ...`）
