# 科研就绪设计审查（design review）

> 状态：审查结论存档，P0 项建议纳入第三轮联调任务清单
> 范围：`src/rdi/` 全部子系统（adapters / models / skills / graph / frontend / config）
> 视角：研究人员日常准备机器人实验，而非 demo 演示

## 1. 背景与核心诊断

第二次联调后系统能端到端生成含 URDF / mesh / sim_config / grasp 的数据包，但审查发现：**这套系统的设计目标是「demo 能跑通」，不是「科研人员日常使用」**。大量设计决策在 demo 场景下无感、在科研场景下致命——尤其是「静默」类缺陷：降级不告知、溯源丢失、失败语义塌缩、单位坐标隐式。

审查发现的全部问题按对科研使用的伤害分为六类，后续章节逐一展开。其中「大文件处理」是单独沉淀的一份设计（第 7 章），其余五类为本轮新增。

## 2. 可复现性地基缺失（最致命）

demo 无感、科研致命，均**静默**破坏实验可复现性：

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| R1 | `provenance`/`errors`/`validation_issues` 无 reducer，LangGraph 默认「后值覆盖」 | `graph/state.py:57-58` | 最终 manifest 的 `provenance.log` 只剩 assemble 一行，无法追溯「数据从哪个源、经过什么转换来」 |
| R2 | parse_convert 无条件返回 `"errors": []` | `graph/nodes/parse_convert.py:164` | LLM 解析错误被前序清空，前端读到的 errors 恒为空 |
| R3 | manifest 无 checksum / 版本 / 许可 / 引用 | `models/manifest.py:13-29` | 无法验证包内文件与来源一致；无法合规引用数据集 |
| R4 | URL 指分支不指 commit | `adapters/franka.py:16`、`settings.py:134-141` | 同一 item_id 前后两次实验拿到漂移内容，无法察觉 |
| R5 | 无 run_id 贯穿 | `models/common.py`（ProvenanceEntry） | 溯源无法关联到具体一次实验 |
| R6 | 磁盘缓存无失效策略、键不稳定 | `adapters/base.py:85-112` | 重跑拿到过期数据；Franka 主/降级路径共用缓存键互相覆盖 |

**修复方向**：给 state 的 list 字段加 `Annotated[list, operator.add]` reducer；manifest 落盘时计算 sha256 并记录 pipeline 版本；adapter 配置按 commit 钉住；缓存键加入内容指纹 + 失效机制。

## 3. 失败语义塌缩（研究者无法诊断）

demo 里「失败就重试」可接受，科研场景必须知道「为什么失败、是哪种失败」：

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| E1 | `except AdapterError: continue` 吞掉具体错误，`retrieval_errors` 是死字段 | `graph/nodes/retrieve_data.py:209` | 前端只能显示「所有候选源均失败」，无法区分 404/限流/超时/认证 |
| E2 | `status != "success"` 一律转 MissingItem | `skills/registry.py:87` | 「搜索无结果」与「下载被限流」无法区分 |
| E3 | 静默降级全部显示 success | YCB GRASP→mesh、Isaac→不可加载、大文件→metadata JSON | 研究者以为拿到目标数据，实际是降级替代品 |
| E4 | `data_source_quality` 默认 `or "fallback"` | `graph/nodes/assemble.py:163`、`models/manifest.py:26-29` | 真实下载的 URDF 也被标成 fallback，manifest 默认在撒谎 |
| E5 | status 恒为 "complete" | `graph/nodes/assemble.py:187` | 0 文件、有 ERROR 也标 complete |

**修复方向**：`status` 改枚举（FOUND / NOT_FOUND / DOWNLOAD_FAILED / RATE_LIMITED / TOO_LARGE_REFERENCED）；降级必须透出 `is_fallback` 到 manifest 与前端；`data_source_quality` 默认 `unknown`；status 由 missing/error 数量推导 complete/partial/failed。

## 4. 真实科研数据链路不通（核心业务）

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| D1 | 搜索靠硬编码清单（Franka 3 型号、YCB 20 物体、MuJoCo 6 场景、物体映射 12 条） | 各 adapter `_FALLBACK_*` | 清单外的目标静默返回空，无「有源但未收录」提示 |
| D2 | `object_name` 从不传入，`except TypeError` 兜签名差异 | `graph/nodes/retrieve_data.py:182-187` | 「香蕉的抓取标注」实际下载仓库第一个 `.npz/.pkl`；`_graspnet_objects.py` 是死代码 |
| D3 | 数据不自包含：URDF/MJCF 只下单个 XML，mesh 资产悬空 | `adapters/base.py`、`adapters/franka.py` | 外部工具加载即崩 |
| D4 | URDF 解析忽略 `<visual>/<collision>` mesh 引用，validate `load_meshes=False` | `skills/urdf_convert.py:132-180`、`graph/nodes/validate.py:73` | 「引用不存在 mesh 的 URDF」照样 PASS |
| D5 | 合成数据冒充成功，原始 metadata 的 file_url 被丢弃 | `skills/grasp_parse.py:289-312` | 研究者既没拿到数据，也不知道去哪手动下载 |
| D6 | 无本地数据集挂载配置 | `config/settings.py` | 本地已有 GraspNet/YCB 的研究者被强制走镜像小样本 |
| D7 | 需求类型与返回格式不匹配无检测 | `adapters/ycb.py:140-167` | YCB GRASP 拿到 obj，下游解析失败但记录 success |

**修复方向**：为 MESH/ROBOT_URDF 增加通用搜索源（HF 标签 / GitHub 代码搜索）；统一 fetch 签名并接通 object_name；递归下载 URDF/MJCF 引用资源；validate 用 `load_meshes=True` 完整加载；合成占位降级为 MissingItem；新增本地数据集目录配置。

## 5. 人机闭环是假象

| # | 缺陷 | 位置 | 后果 |
|---|---|---|---|
| H1 | `review_decision` 在运行前预选，一次 ainvoke 跑完全图，无 checkpointer | `frontend/app.py:542-546`、`graph/builder.py:91` | 研究者永远看不到中间结果，审查形同虚设 |
| H2 | unsatisfied 分支重检索用相同需求/关键词/源 | `graph/nodes/human_review.py:187-205`、`retrieve_data.py:56` | 必然得到相同失败，白等后 3 轮强制 pass 带错误交付 |
| H3 | 修订只能整链重跑，无法只修失败项 | `graph/builder.py:84` | 已成功项被丢弃重拉，浪费时间且引入不稳定 |
| H4 | 无法注入本地文件 | `frontend/app.py` | 「我本地有 grasp 标注」无法处理 |
| H5 | 修订上限复用 iteration_count，与 validate 互相污染 | `validate.py:336`、`human_review.py:135-136` | 强制 pass 静默发生，用户不知情 |

**修复方向**：启用 MemorySaver + `interrupt_before=["human_review"]`；unsatisfied 时把 feedback 写入 data_requirements 后再重检索；支持「仅修订失败 req」路径；per-req 本地文件注入；拆分为 validate_iteration 与 review_iteration 两个独立计数器。

## 6. 数据模型缺物理量纲与体验缺陷

### 6.1 物理量纲（最危险）

单位/坐标系/时间基准全部隐式：`CanonicalGrasp`/`CanonicalRobot`/`SensorDataset` 无 units/frame 字段，单位换算参数硬编码在 Skill 代码常量（`grasp_parse.py:DATASET_CONVENTIONS`、`mesh_process.py`）。研究者拿到 grasps json 不知道 position 是米还是毫米、旋转是四元数还是矩阵——机器人实验最致命的隐性歧义。

**修复方向**：`ParsedItem` 增加强制的 `units`、`coordinate_frame`、`timestamp_epoch` 元数据；转换参数随数据落盘而非留在代码常量。

### 6.2 类型覆盖不足

`DataReqType` 只有 9 类，缺科研日常类型：相机标定、示教轨迹、机器人配置（关节限位/控制器增益）、benchmark 任务定义——LLM 只能硬塞进 SENSOR_DATA/UNKNOWN。

### 6.3 概念混杂

`DataSource` 把硬件型号（FRANKA）与仓储源（ARXIV）并列，「数据关于哪台机器人」和「数据来自哪」两个正交维度压成一个枚举。

### 6.4 体验与可观测性

- 前端黑盒一次性提交，无分步进度、无 gr.Progress、无 stream
- 日志配置是死的：`LOG_FORMAT=json` 定义但全库仅 2 处 logging，structlog 装了从不 import
- README 声称的「并行检索」实际是顺序 for 循环
- 演示包混入真实产物：前端默认「演示流程」，后端异常伪造 fallback 包当成功展示
- 串行检索 + 无 per-req 超时预算：10+ 需求一次运行轻松半小时

## 7. 大文件统一引用模型（P0 设计，见原 design note）

机器人实验数据普遍存在大体积文件（GraspNet 单物体 grasp_label 数百 MB、权重 GB 级、tar/ROS bag 数 GB）。当前各 Adapter 各自为政：

| Adapter | 现状 | 问题 |
|---|---|---|
| GraspNet | HEAD 预检超 50MB → metadata JSON | 格式私有，skill 无法统一识别 |
| arXiv | PDF 超 2MB → metadata JSON | 阈值与其他 Adapter 不一致 |
| Google Scanned | mesh 下载 30s 超时 | 无预检，直接失败 |
| HuggingFace | 只返回 config.json | 权重文件完全未触达 |

**核心原则**：大文件的分水岭不在体积，而在「是否需要在 pipeline 内消费」。必须下载（URDF/mesh/PDF/CSV）走下载；只需引用（grasp 标签/模型权重/大 tar）走引用。

**统一模型**：

```
RawData
 ├─ data=bytes（已下载，可解析）
 └─ reference={...}（引用模式）
      ├─ url / local_path / file_size / download_hint
```

**统一决策顺序**：`本地磁盘缓存 → 本地数据集挂载 → HEAD 预检 → 单文件下载 → 引用降级`

**类型可配项**（不一刀切）：`max_fetch_bytes` 按 req_type 覆盖（PDF 2MB、mesh 50MB、权重 500MB）；`allow_download`（URDF/mesh 必须 true）；`consume_mode`（bytes vs 本地路径）。

**Manifest 统一记录**：`{source, file_url, file_size, downloaded, local_path}`，让研究者一眼看出「真实下载 or 引用外链」。

## 8. 修复优先级

| 优先级 | 修复项 | 理由 |
|---|---|---|
| **P0** | state 加 reducer（provenance/errors 累积）+ 失败语义结构化 | 溯源与诊断的地基，一切可复现性的前提 |
| **P0** | 真实 human_review（checkpointer + interrupt） | 「审查闭环」从演示变真实 |
| **P0** | 数据不自包含修复（递归下载 URDF/MJCF 引用资产 + validate 完整加载） | 包不可运行 = 直接不能用 |
| **P0** | 大文件统一引用模型（第 7 章） | grasp/权重真实路径的地基 |
| **P1** | manifest 补 sha256/版本/license/citation、status 推导 | 归档可信度 |
| **P1** | 静默降级显式化（is_fallback 透出 + 不默认 fallback 标签） | 让研究者信任 manifest |
| **P1** | 恢复并行检索 + per-req 超时预算 | 多需求场景可用性 |
| **P2** | 数据模型补 units/frame、扩充 DataReqType、本地数据集挂载 | 物理量纲与真实工作流 |

## 9. 结论

系统在「单一路径 demo」上已经跑通，但距离「科研人员日常使用」还差一轮以 P0 项为核心的联调：先修可复现性地基（state reducer / manifest 校验和 / 版本钉住），再修数据链路（引用模型 / 资产自包含 / object_name 接通 / 本地挂载），最后修人机闭环（真交互 human_review / 失败可诊断）。P0-P1 项建议并入第三轮联调任务清单，P2 项作为后续演进。
