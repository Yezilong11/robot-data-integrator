# 第二次联调 Checklist

> 依据：[spec.md](./spec.md) 与 [tasks.md](./tasks.md)

- [x] `CodeSkill` 已实现并注册到 `SkillRegistry`
- [x] `DatasetSkill` 已实现并注册到 `SkillRegistry`
- [x] `parse_convert` 对 `CODE` 类型不再返回 `MissingItem`
- [x] `parse_convert` 对 `DATASET` 类型不再返回 `MissingItem`
- [x] `FrankaAdapter` 返回纯 URDF 字节
- [x] 至少一个 URDF 源可被 `URDFSkill` 解析
- [x] `YCBAdapter` 返回 `MeshSkill` 支持的格式
- [x] 至少一个 Mesh 源可被 `trimesh.load` 加载
- [x] `GoogleScannedAdapter` 超时问题已修复或已明确降级方案
- [x] `parse_goal` 输出中不再把 URDF/mesh 识别为 `CODE`/`DATASET`
- [x] `retrieve_data` 按 `fallback_sources` 顺序尝试数据源
- [x] `URDFSkill` 在无 ROS 环境下对 xacro 有降级处理
- [x] `MeshSkill` 支持 `glb` 与 `zip` 输入
- [x] `validate` 节点对 URDF 做可解析性校验
- [x] `validate` 节点对 mesh 做可加载性校验
- [x] `validate` 节点对 sim_config 做语法校验
- [x] `validate` 节点对 grasp 做字段完整性校验
- [x] 输入 "Franka Panda grasps YCB banana in MuJoCo simulation" 能生成数据包
- [x] 数据包包含至少两类真实文件（URDF / mesh / grasp / sim_config）
- [x] 生成的数据包中至少一个 URDF 可被 `urdfpy` 解析
- [x] 生成的数据包中至少一个 mesh 可被 `trimesh` 加载
- [x] 新增单元测试覆盖率不低于 80%
- [x] `uv run pytest` 全绿
- [x] `uv run ruff check src tests` 无错误
- [x] `uv run ruff format --check src tests` 无错误
- [x] `scripts/_probe_adapters.py` 13/15 以上 Adapter fetch 成功
- [x] `docs/second_integration_report.md` 已创建
