# Tasks

> 执行顺序遵循用户指示：**A → B → C → D → E**（组间串行）。组内并行时注意「共享文件」冲突：同一文件禁止被两个并行子代理同时编辑。每任务完成后运行对应定向测试 + `uv run pytest` 相关目录，最终 Task 18 全量回归。

## A 组：实现 gap 补齐

- [x] Task 1: 资产文件纳入 manifest 与 checksums.txt（A1）
  - [x] `src/rdi/graph/nodes/assemble.py`：资产落盘时对每个资产文件生成 ManifestFile 条目（`downloaded=true`、`format` 按扩展名推断：.stl/.dae/.obj/.xml/.png→mesh/texture 语义，`file_url` 沿用来源、`local_path` 为相对路径、`file_size`/`checksum_sha256` 实际计算）
  - [x] `checksums.txt` 覆盖资产文件（与主文件合并排序）
  - [x] 验证：`tests/unit/graph/test_assemble.py` 新增用例——含 assets 的 item 落盘后 manifest 含资产条目且 checksum 与磁盘一致、checksums.txt 覆盖资产

- [x] Task 2: 资产递归下载 + MJCF 深度校验（A2+A3，共享 `src/rdi/adapters/base.py` 与 `src/rdi/graph/nodes/validate.py`）
  - [x] `src/rdi/adapters/base.py` `_download_xml_with_assets` 增强：
    - 递归：include 子 XML 也解析其 mesh/texture/include 引用（深度上限 `_MAX_ASSET_DEPTH=3`，已下载相对路径去重防环）
    - `package://` 解析：`package://<rest>` 按 `posixpath.join(dirname(xml_url), rest)` 作为相对路径尝试下载（pybullet_robots panda 语义）；下载失败跳过并记录缺失
    - 逐资产下载失败降级跳过（与现有行为一致，不抛异常）
  - [x] `src/rdi/graph/nodes/validate.py` `_mujoco_runtime_check`：把 `item.assets` 写入临时目录（按相对路径）后再加载校验，不再因资源缺失恒 skipped
  - [x] 验证：`tests/unit/adapters/test_base.py` 新增——include 递归下载、循环引用终止、package:// 解析、无效 package:// 跳过；`tests/unit/graph/test_validate.py` 新增——MJCF 带 assets 校验不再 skipped

- [x] Task 3: 合成占位 is_fallback 标记（A4，共享 `src/rdi/skills/grasp_parse.py` 与 `src/rdi/skills/registry.py`）
  - [x] `StandardResult`（在 common/models 中定义处）增加 `is_fallback: bool = False`
  - [x] `grasp_parse.py` `_synthetic_result` 置 `is_fallback=True`（sim_config `_fallback_to_mjcf` 同步置 True）
  - [x] `registry.py` 装配 ParsedItem 时 `is_fallback=(result.is_fallback or skill_result.is_fallback)`
  - [x] 验证：`tests/unit/skills/test_grasp_parse.py`、`tests/unit/skills/test_registry.py` 新增——合成结果 is_fallback=True、ParsedItem.is_fallback 合并语义正确

## B 组：可复现性（R4/R5/R6）

- [x] Task 4: URL 钉 commit（B1，共享 `src/rdi/config/settings.py` 与 `src/rdi/adapters/franka.py`）
  - [x] 收集全部 raw.githubusercontent 直链（settings 源配置 + franka `_PANDA_*_URL` 等），把 `master`/`main` 分支替换为具体 commit hash（用 GitHub API 查询后硬编码，注释记录 pin 日期）
  - [x] 其他可变源 URL（如 zenodo 记录 API、huggingface resolve URL）确认无漂移风险或钉版本
  - [x] 验证：grep 确认无 `master`/`main` 分支引用残留；`tests/unit/adapters/test_franka.py` 通过

- [x] Task 5: run_id 贯穿（B2，共享 `src/rdi/graph/state.py`、`src/rdi/models/manifest.py`、`src/rdi/graph/builder.py`、`src/rdi/frontend/app.py`）
  - [x] `SystemState` 增加 `run_id: str = ""`
  - [x] 流程入口（builder.run 或 run_workflow）启动时生成 `run_id`（`时间戳-随机短串`），注入初始 state
  - [x] `manifest.package_info` 增加 `run_id`（取 state.run_id）
  - [x] 前端展示 run_id
  - [x] 验证：`tests/unit/graph/` 新增——build/run 后 manifest package_info 含非空 run_id；单跑测试不设 run_id 时为空（兼容）

- [x] Task 6: 缓存失效与键稳定（B3，共享 `src/rdi/adapters/base.py`、`src/rdi/config/settings.py`）
  - [x] `_make_cache_key` 规范化 URL（query 参数排序、去空值）
  - [x] 内存缓存加 TTL（`settings.cache_ttl_seconds`，默认 3600）与最大条目数（`cache_max_entries`，默认 256），写入时记录时间戳，读取时过期即失效
  - [x] franka 主/降级路径缓存键明确区分（确认当前是否共用键导致互相覆盖，若共用则按 URL+格式区分）
  - [x] 验证：`tests/unit/adapters/test_base.py` 新增——TTL 过期失效、query 乱序同键；`tests/unit/adapters/test_franka.py` 主/降级缓存互不覆盖

## C 组：业务链路（D2/D1/D5/D7/H3）

- [x] Task 7: object_name 接通（C1，共享 `src/rdi/models/goal.py`、`src/rdi/graph/nodes/retrieve_data.py`、`src/rdi/adapters/graspnet.py`、`src/rdi/adapters/ycb.py`）
  - [x] `DataReq` 增加 `object_name: str = ""`；goal 解析（parse_goal 降级路径/LLM 路径）从目标文本提取物体名填入
  - [x] `node_retrieve_single` 构造 payload 时把 `object_name` 传入 search/fetch kwargs
  - [x] `graspnet.py` fetch/search 用 object_name 查 `_graspnet_objects` 映射精确定位（不再下载仓库第一个文件）；`ycb.py` 用 object_name 匹配物体
  - [x] 验证：`tests/unit/graph/test_retrieve_data.py`、`tests/unit/adapters/test_graspnet.py`、`tests/unit/adapters/test_ycb.py` 新增——object_name 透传、按物体名取文件

- [x] Task 8: 清单外目标可诊断（C2，共享 `src/rdi/adapters/*` 与 `src/rdi/skills/registry.py`）
  - [x] 各硬编码清单 adapter（franka/ycb/graspnet/robotiq/allegro/isaac/mujoco）search 对清单外目标返回可诊断语义：`_search_fallback` 无匹配抛 `AdapterCatalogError`（reason 含「该源仅收录已知目标」+ 清单大小 +「有源但未收录」）；retrieve_data 收集诊断写入 missing 的 error_message；registry 经 `error_message or "无原始数据"` 自动透出到 MissingItem.reason
  - [x] registry 对这类 search 结果的 MissingItem.reason 透出该语义（无需改 registry，链路已通读确认）
  - [x] 验证：`tests/unit/adapters/` 清单外用例（7 adapter 抛错断言 + 消息含清单大小）、`tests/unit/graph/test_retrieve_data.py`（missing 透出 + C1 多 query 不回归）、`tests/unit/skills/test_registry.py` reason 断言

- [x] Task 9: 合成占位降级为 MissingItem（C3，共享 `src/rdi/skills/grasp_parse.py`、`src/rdi/skills/registry.py`）
  - [x] grasp_parse 合成路径（`_synthetic_result` 调用处）改为返回 MissingItem 语义：reason 含「原始数据缺失，合成占位仅作参考，真实数据见 reference」；不再以 success 交付合成数据
  - [x] 保留 reference 语义（数据集的 file_url 仍可在 manifest 呈现供手动获取）
  - [x] 验证：`tests/unit/skills/test_grasp_parse.py`——数据集仅元数据时返回 MissingItem 而非 success；受影响集成测试同步修正

- [x] Task 10: 类型错配检测（C4，共享 `src/rdi/skills/registry.py` 与 `src/rdi/graph/nodes/parse_convert.py`）
  - [x] registry 装配时校验「req_type 期望格式与实际返回」：`_REQ_EXPECTED_FORMATS` 白名单（GRASP→抓取格式、ROBOT_URDF→urdf/xacro、SIM_CONFIG→xml/mjcf/py/yaml、MESH→mesh 格式）；`_format_mismatch_reason` 错配返回 MissingItem reason 含期望/实际格式
  - [x] 不匹配 → MissingItem（reason 含期望/实际格式 +「类型错配」），不静默 success；GRASP 拿 mesh 且源标注无抓取标注时追加说明
  - [x] 验证：`tests/unit/skills/test_registry.py` 新增 5 用例——YCB GRASP 拿 obj 记 MissingItem、合法格式不误报、MESH 反向；全量 643 passed

- [x] Task 11: 仅修订失败 req（C5，共享 `src/rdi/graph/nodes/human_review.py`、`src/rdi/graph/nodes/retrieve_data.py`、`src/rdi/graph/state.py`）
  - [x] `SystemState` 增加 `retry_req_ids: list[str]`（operator.add 累积）
  - [x] human_review unsatisfied/revised 时把「失败的 req」（missing_items + retrieval_errors 对应的 req_id）写入 `retry_req_ids`（或从 feedback 显式指定）
  - [x] retrieve_data/parse_convert 重跑时只处理 `retry_req_ids` 覆盖的 req，已成功项沿用不重拉
  - [x] 验证：`tests/unit/graph/test_human_review.py`、`tests/unit/graph/test_retrieve_data.py`——修订只重跑失败 req、成功项结果保留

## D 组：P2 演进

- [x] Task 12: 物理量纲显式化（D1，共享 `src/rdi/models/parsed.py`、`src/rdi/skills/grasp_parse.py`、`src/rdi/skills/urdf_convert.py`、`src/rdi/skills/sensor_data.py`、`src/rdi/graph/nodes/assemble.py`、`src/rdi/skills/registry.py`）
  - [x] `ParsedItem` 增加 `units: str = ""`、`coordinate_frame: str = ""`、`timestamp_epoch: float | None = None`
  - [x] `CanonicalGrasp` 增加 `units`/`frame` 标注字段（默认 "meter"/"unknown" 或按数据集约定填充）；DATASET_CONVENTIONS 装配时填入；urdf/sensor 类同理填单位
  - [x] skills 装配后经 registry 透传到 ParsedItem
  - [x] assemble 生成包内 `units.json`（记录每 req 的 units/coordinate_frame/timestamp_epoch，来自 DATASET_CONVENTIONS + item 元数据），转换参数不再只存在于代码常量
  - [x] 验证：`tests/unit/skills/test_grasp_parse.py`（grasps 带单位标注）、`tests/unit/graph/test_assemble.py`（units.json 落盘且内容正确）、`tests/unit/skills/test_registry.py`（透传）

- [x] Task 13: DataReqType 扩充（D2，共享 `src/rdi/models/common.py`（或 goal.py 枚举处）、LLM 提示、`src/rdi/frontend/app.py`）
  - [x] `DataReqType` 新增 `CAMERA_CALIB` / `TEACHING_TRAJECTORY` / `ROBOT_CONFIG` / `BENCHMARK_TASK`（枚举 + 中文描述）
  - [x] LLM 提示（parse_goal 系统提示）与前端类型选项同步（前端仅表格展示 req_type 字符串，确认无需改动）
  - [x] 新类型无内置 adapter/skill：检索返回 missing + reason「该类型暂无内置数据源」（诚实失败，不塞 UNKNOWN）
  - [x] 验证：`tests/unit/` goal 解析用例（新类型可识别）、检索该类型返回 missing

- [x] Task 14: 本地数据集挂载（D3，共享 `src/rdi/config/settings.py`、`src/rdi/adapters/base.py`、相关 adapter）
  - [x] `settings.local_datasets: dict[str, str] = {}`（来源名 → 本地目录）
  - [x] base.py 提供本地命中检查（按来源+item_id/object_name 在目录树中查找文件）；命中 adapter 直接返回本地 RawData（不发起网络请求，provenance 记录 source=local）
  - [x] 与前端 per-req 注入（local_files）并存互不干扰
  - [x] 验证：`tests/unit/adapters/test_base.py`、相关 adapter 测试——配置 local_datasets 后命中本地文件、未命中走网络

## E 组：体验与可观测性

- [x] Task 15: 前端分步进度（E1，共享 `src/rdi/frontend/app.py`）
  - [x] 运行改为分步：retrieve→parse→validate→assemble 各阶段 yield 中间状态（gr.Progress / 阶段输出），展示当前阶段与阶段性结果
  - [x] 验证：`tests/unit/frontend/`（若有）或人工冒烟；现有 run 流程测试不回归

- [x] Task 16: 日志启用（E2，共享 `src/rdi/config/settings.py` 与核心节点）
  - [x] 接入 structlog（install logging 配置，LOG_LEVEL/LOG_FORMAT 生效）
  - [x] retrieve_data/parse_convert/validate/assemble/human_review 关键节点加结构化日志（req_id/source/耗时/状态）
  - [x] 验证：单元测试或冒烟——日志按配置格式输出；`ruff check` 通过

- [x] Task 17: 演示与真实产物隔离（E3，共享 `src/rdi/frontend/app.py` 与 `src/rdi/graph/nodes/assemble.py`）
  - [x] 演示流程产物标记 demo：写 `demo/` 目录或 manifest.package_info.demo=true，不混入真实 output_packages
  - [x] 真实流程不再伪造 fallback 包（异常按真实失败呈现）
  - [x] 验证：人工冒烟 + 相关测试

## 回归

- [x] Task 18: 全量回归与端到端验证
  - [x] `uv run pytest tests/ -q` 全量通过（修复回归）
  - [x] `uv run python scripts/smoke_adapters.py` 冒烟
  - [x] 端到端（复用上一轮方式）：目标含 URDF/MJCF/MESH/GRASP，核对——资产文件在 manifest+checksums.txt 中、MJCF 链离线完整、run_id 在 manifest、object_name 生效、清单外目标可诊断、合成降级为 missing、units.json 落盘、前端分步
  - [x] 验证：全量测试通过；端到端核对清单通过

# Task Dependencies

- [Task 2] 依赖 [Task 1]（A 组内部 assemble 资产条目先行，Task 2 侧重 base/validate；可并行但注意 assemble.py 冲突）
- [Task 3] 独立于 [Task 1]/[Task 2]（不同文件），可与 A 组并行
- [Task 6] 依赖 [Task 4]/[Task 5] 完成后再做（B 组串行：URL 钉 commit → run_id → 缓存，均不共享文件但按 B 组顺序推进）
- [Task 9] 依赖 [Task 3]（is_fallback 标记是降级显式化的前提）
- [Task 12] 依赖 C 组完成（units 透传链路依赖 registry 语义稳定）
- [Task 18] 依赖全部任务

# 共享文件冲突提示（禁止并行编辑同一文件）

- `src/rdi/adapters/base.py`：Task 2 / Task 6 / Task 14
- `src/rdi/graph/nodes/assemble.py`：Task 1 / Task 12 / Task 17
- `src/rdi/skills/registry.py`：Task 3 / Task 8 / Task 9 / Task 10 / Task 12
- `src/rdi/graph/state.py`：Task 5 / Task 11
- `src/rdi/graph/nodes/retrieve_data.py`：Task 7 / Task 11
- `src/rdi/config/settings.py`：Task 4 / Task 6 / Task 14 / Task 16
- `src/rdi/frontend/app.py`：Task 5 / Task 13 / Task 15 / Task 17
- `src/rdi/skills/grasp_parse.py`：Task 3 / Task 9 / Task 12
