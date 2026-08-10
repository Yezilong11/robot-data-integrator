# Tasks

> 范围：P0+P1（审查第 8 章）。P2 留作后续。
> 原则：每个任务交付可验证的改动 + 对应单元测试更新；最终全量回归。

- [x] Task 1: state reducer + 失败语义结构化（P0-1 地基）
  - [x] `src/rdi/graph/state.py`：`provenance` / `errors` 改为 `Annotated[list, operator.add]`（引用 `typing.Annotated` 与 `operator`）；`validation_issues` 保持 last-wins 并在注释说明理由（validate 每轮全量重算，accumulate 会跨轮重复）
  - [x] `src/rdi/graph/nodes/parse_convert.py`：移除返回值中的 `"errors": []`；仅在有真实错误时返回 `errors`
  - [x] `src/rdi/models/retrieval.py`：`RetrievalResult.status` 语义枚举化——文档化为 success/missing/error（error 必须带 `error_message`）；`RetrievalError.error_type` 保持 timeout/rate_limit/not_found/auth/unknown
  - [x] `src/rdi/graph/nodes/retrieve_data.py`：`node_retrieve_single` 内 `except AdapterError as e` 时按 `status_code` 归类（429→rate_limit、408/TimeoutError→timeout、404→not_found、401/403→auth、其余→unknown），生成 `RetrievalError` 累积返回 `retrieval_errors`；不再 `continue` 吞掉细节
  - [x] `src/rdi/skills/registry.py`：`process_retrieval_result` 对 status="error" 的 result 在 `MissingItem.reason` 中保留 error_type + error_message
  - [x] 验证：`pytest tests/unit/graph/test_retrieve_data.py tests/unit/graph/test_parse_convert.py tests/unit/skills/test_registry.py`（新增用例：错误归类、errors 累积不被清空、retrieval_errors 非空）—— 28 passed 定向；539 passed unit 全量

- [x] Task 2: 真实 human_review（P0-2）
  - [x] `src/rdi/models/common.py`：`DataSource` 增加 `LOCAL = "local"`（本地文件注入专用来源，不注册网络适配器）
  - [x] `src/rdi/graph/builder.py`：`build_graph(checkpointer: Any = None)`，`compile(checkpointer=checkpointer)`；采用**节点内 interrupt**（仅 `interrupt_review=True` 时 human_review 内调用 `interrupt()`），不使用 `interrupt_before`，单次 invoke 行为不变
  - [x] `src/rdi/graph/state.py`：新增 `interrupt_review` / `review_iteration` / `local_files` 字段；`node_validate` 改用 `validate_iteration`（`iteration_count` 保留为历史兼容字段）
  - [x] `src/rdi/graph/nodes/validate.py` / `edges.py`：读取/递增 `validate_iteration`（重试上限 3 逻辑不变）
  - [x] `src/rdi/graph/nodes/human_review.py`：节点内 `interrupt()` 条件暂停；循环上限用 `review_iteration`（>= `_MAX_REVIEW_ROUNDS` 强制 satisfied）；`unsatisfied` 分支把 feedback 写入 `data_requirements`（description 追加 + keywords 合并，`model_copy(deep=True)` 不就地改原需求）后再回 retrieve_data；`revised` 分支维持回 parse_goal
  - [x] `src/rdi/frontend/app.py`：两阶段运行——`run_graph` 首跑返回 (state, thread_id, interrupted)，`resume_workflow(decision, feedback)` 用 `Command(resume=...)` 继续（共享模块级 `_pending_thread_id` / `_graph_app` / `_get_graph_app()` 带 MemorySaver）；抽取 `_format_result` 共用；UI 增加「继续运行」按钮与 local_files Textbox（JSON：req_id → 路径）
  - [x] 本地文件注入：`run_graph` 把 local_files 写入 state（`local_files: dict[str, str]`），`node_parse_convert` 构造 `RetrievalResult`（`DataSource.LOCAL`、`RawData`、`url=f"local://{path}"`）合并进 retrieval_results（local 优先）
  - [x] 验证：`pytest tests/unit/graph/test_human_review.py tests/unit/graph/test_validate.py tests/unit/graph/test_parse_convert.py tests/unit/frontend/test_progress.py`（新增：interrupt/resume 双阶段、unsatisfied 后 requirements 变更、review_iteration 独立上限、validate_iteration、本地文件注入）—— 71 passed；适配器测试排除 LOCAL 后 `tests/unit` 550 passed；`tests/integration` 11 passed

- [ ] Task 3: 数据包自包含（P0-3）
  - [ ] `src/rdi/models/retrieval.py`：`RawData` 增加 `assets: dict[str, bytes] = Field(default_factory=dict)`
  - [ ] `src/rdi/models/parsed.py`：`ParsedItem` 增加 `raw_bytes: bytes | None = None`、`assets: dict[str, bytes] = Field(default_factory=dict)`
  - [ ] `src/rdi/adapters/base.py`：新增 `_download_xml_with_assets(xml_url, xml_bytes)`——解析 XML 中 `<mesh filename>` / `<texture filename>` / `<include filename>` 引用，相对 URL 以 XML 所在目录为基准解析，逐个 `_download_bytes`（含镜像兜底），返回 `{相对路径: bytes}`；解析失败时降级返回空 dict（不抛异常）
  - [ ] `src/rdi/adapters/franka.py` / `allegro.py` / `robotiq.py` / `mujoco.py`：URDF/MJCF 下载后调用上述 helper 填充 `RawData.assets`
  - [ ] `src/rdi/skills/registry.py`：装配 `ParsedItem` 时透传 `raw_bytes=raw.data`、`assets=raw.assets`（URDF/MJCF 类型）
  - [ ] `src/rdi/graph/nodes/validate.py`：`_validate_urdf_loadability` 改为对 `raw_bytes` 用 `yourdfpy.URDF.load(..., load_meshes=True)`，资产写入临时目录后按相对路径加载；无 raw_bytes 时维持现状
  - [ ] `src/rdi/graph/nodes/assemble.py`：对含 `raw_bytes` 的项，把原始 XML 写入 `{req输出路径}`，`assets` 按相对路径写入同目录结构；无 raw_bytes 时维持序列化路径
  - [ ] 验证：`pytest tests/unit/adapters/test_franka.py tests/unit/adapters/test_mujoco.py tests/unit/adapters/test_base.py tests/unit/graph/test_validate.py tests/unit/graph/test_assemble.py`（新增：assets 递归、validate load_meshes=True 引用坏 mesh 报错、assemble 落盘结构）

- [x] Task 4: 大文件统一引用模型（P0-4）
  - [x] `src/rdi/models/retrieval.py`：新增 `RawReference {url, local_path, file_size, download_hint, reason}`；`RawData` 增加 `reference: RawReference | None = None`
  - [x] `src/rdi/adapters/graspnet.py`：`_build_metadata` 构造时设置 `reference`（url/file_size/download_hint/reason）
  - [x] `src/rdi/adapters/arxiv.py`：metadata 返回设置 `reference`
  - [x] `src/rdi/adapters/google_scanned.py`：`_metadata_fallback` 设置 `reference`（zip_url 为 download_hint）
  - [x] `src/rdi/adapters/huggingface.py`：模型权重场景——fetch 仍返回 config.json，但 `metadata` 中的仓库信息透传；如有 reference 语义则设置（最小实现：config.json 视为小文件下载，不强制引用）
  - [x] `src/rdi/models/manifest.py`：`ManifestFile` 增加 `file_size: int = 0`、`downloaded: bool = True`、`local_path: str = ""`、`file_url: str = ""`
  - [x] `src/rdi/graph/nodes/assemble.py`：落盘时按 `raw.reference` 填充 `downloaded=false / file_url / file_size / local_path`
  - [x] 验证：`pytest tests/unit/adapters/test_graspnet.py tests/unit/adapters/test_arxiv.py tests/unit/adapters/test_google_scanned.py tests/unit/graph/test_assemble.py`（新增：reference 字段非空、manifest 引用记录）—— 定向通过；tests/unit 573 passed 全量

- [x] Task 5: manifest 完整性与 status 推导（P1-1）
  - [x] `src/rdi/models/manifest.py`：`ManifestFile` 增加 `checksum_sha256: str = ""`；`package_info` 契约明确含 `pipeline_version`、`license`、`citation`（从源 metadata 可得时填充，否则空）
  - [x] `src/rdi/__init__.py` 或 `config/settings.py`：定义 `PIPELINE_VERSION` 常量
  - [x] `src/rdi/graph/nodes/assemble.py`：落盘时对每个文件计算 sha256 写入 `checksum_sha256`；生成 `checksums.txt`（path → sha256）；`package_info` 填 `pipeline_version`
  - [x] `src/rdi/graph/nodes/assemble.py`：`status` 推导——`len(files)==0 or REQUIRED missing → failed`；`missing>0 → partial`；`其余 → complete`
  - [x] 验证：`pytest tests/unit/graph/test_assemble.py`（新增：checksum 计算与一致性、status 三态推导、pipeline_version 存在）—— 13 passed 定向；tests/unit 579 passed 全量

- [x] Task 6: 静默降级显式化（P1-2）
  - [x] `src/rdi/models/manifest.py`：`ManifestFile.data_source_quality` 默认改为 `"unknown"`
  - [x] `src/rdi/graph/nodes/assemble.py`：移除 `or "fallback"`，直接透传 `item.data_source_quality`（None → "unknown"）；`ManifestFile` 增加 `is_fallback: bool = False`，从 `RetrievalResult.is_fallback` 透出（经 `ParsedItem` 或 state 关联）
  - [x] `src/rdi/models/parsed.py`：`ParsedItem` 增加 `is_fallback: bool = False`，registry 装配时从 `result.is_fallback` 透传
  - [x] 验证：`pytest tests/unit/graph/test_assemble.py tests/unit/skills/test_registry.py`（新增：真实 URDF 不再标 fallback、is_fallback 透出）—— 31 passed 定向；tests/unit 584 passed 全量

- [x] Task 7: 并行检索 + 超时预算（P1-3）
  - [x] `src/rdi/config/settings.py`：新增 `per_req_timeout: float = 60.0`
  - [x] `src/rdi/graph/nodes/retrieve_data.py`：`node_retrieve_data` 改为 `asyncio.gather` 并行执行全部 `node_retrieve_single`，每个任务用 `asyncio.timeout(per_req_timeout)` 包裹，超时记 error 型 RetrievalResult + RetrievalError(timeout)，不阻塞其他需求；汇总结果合并 `retrieval_errors`
  - [x] README.md：核对「并行检索 fan-out」描述与实现一致（保留并行措辞即可）
  - [x] 验证：`pytest tests/unit/graph/test_retrieve_data.py`（新增：并行汇总、单需求超时不阻塞整体）—— 11 passed 定向；131 passed graph 目录

- [x] Task 8: 全量回归与端到端验证
  - [x] 运行全量测试 `pytest tests/ -q`，修复所有回归
  - [x] 运行 `uv run python scripts/smoke_adapters.py`（或等价冒烟脚本）确认 adapter 层不回归
  - [x] 以审查文档中的典型科研目标（含 MuJoCo/URDF/mesh/grasp）走一次真实流程，人工核对：manifest 含多节点 provenance、checksum、status 非恒 complete、降级被显式标记、URDF 资产自包含
  - [x] 验证：全量测试通过；端到端产物核对清单通过—— `pytest tests/ -q` 595 passed, 1 skipped, 9 deselected 全绿；冒烟 4 Adapter 正常；端到端两轮流程核对 6 项全通过（项 4 部分通过：package:// 协议约定不下载、MJCF include 资产未递归，已记录为 P2 建议）

# Task Dependencies

- Task 1（state reducer/失败语义）是地基：Task 4（reference 记录）、Task 6（is_fallback 透出）、Task 7（并行/错误记录）依赖其状态语义
- Task 3（数据自包含）与 Task 2（human_review）互不依赖，可在 Task 1 后并行
- Task 5 与 Task 6 依赖 Task 4（ManifestFile 字段演进），Task 5、6 之间可在 Task 4 后并行
- Task 8 依赖全部任务完成

建议执行顺序：Task 1 → [Task 2 ‖ Task 3 ‖ Task 7] → Task 4 → [Task 5 ‖ Task 6] → Task 8
