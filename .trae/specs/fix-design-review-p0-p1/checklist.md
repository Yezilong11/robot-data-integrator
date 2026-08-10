# Checklist

## Task 1: state reducer + 失败语义结构化
- [x] `state.py` 中 `provenance` / `errors` 使用 `Annotated[list, operator.add]` reducer
- [x] `parse_convert` 不再返回 `"errors": []`（仅真实错误时返回）
- [x] `node_retrieve_single` 捕获 `AdapterError` 并按 status_code 归类生成 `RetrievalError`，`retrieval_errors` 被实际写入（不再是死字段）
- [x] `RetrievalResult.status` 语义文档化为 success/missing/error，error 带 error_message
- [x] `registry.process_retrieval_result` 在 `MissingItem.reason` 保留 error_type/error_message
- [x] 测试：错误归类、errors 累积不被清空、retrieval_errors 非空 的用例存在且通过

## Task 2: 真实 human_review
- [x] `DataSource` 增加 `LOCAL = "local"`；`build_graph` 支持注入 checkpointer（None 单跑/演示，MemorySaver 真实两阶段）；采用**节点内 interrupt**（仅 `interrupt_review=True` 时 human_review 调用 `interrupt()`，不使用 interrupt_before），单次 invoke 行为不变
- [x] `validate_iteration` / `review_iteration` 独立计数（`iteration_count` 保留为历史兼容字段，互不污染）
- [x] `unsatisfied` 分支把 feedback 合并进 `data_requirements`（description 追加 + keywords 合并）后再回 retrieve_data
- [x] 前端两阶段：`run_workflow` 首跑返回中断状态，`resume_workflow` 用 `Command(resume=...)` 继续；UI 有「继续运行」入口与 local_files 本地文件注入（JSON：req_id → 路径）
- [x] 本地文件注入：state 含 `local_files`，parse_convert 构造 `RetrievalResult`（`DataSource.LOCAL`、`RawData`、`url=local://...`）优先消费，local 优先于外部检索结果
- [x] 测试：interrupt/resume、unsatisfied 后 requirements 变更、review_iteration 上限、validate_iteration、本地注入 的用例存在且通过

## Task 3: 数据包自包含
- [x] `RawData.assets` 与 `ParsedItem.raw_bytes` / `assets` 字段存在
- [x] `_download_xml_with_assets` 递归下载 mesh/texture/include 引用（相对 URL 解析正确，失败不抛异常）
- [x] franka/allegro/robotiq/mujoco 的 URDF/MJCF 下载填充 assets
- [x] registry 装配 ParsedItem 时透传 raw_bytes/assets
- [x] validate 对 URDF 用 `load_meshes=True` 完整加载（资产落临时目录），坏 mesh 引用产生 ERROR/WARNING
- [x] assemble 把原始 XML + 资产按相对路径写入包
- [x] 测试：assets 递归、坏 mesh 检出、包内结构 的用例存在且通过

## Task 4: 大文件统一引用模型
- [x] `RawReference` 模型与 `RawData.reference` 字段存在
- [x] graspnet/arxiv/google_scanned 的 metadata/引用结果设置 `reference`（url/file_size/download_hint/reason）
- [x] `ManifestFile` 含 `file_size` / `downloaded` / `local_path` / `file_url`
- [x] assemble 对引用项落盘 `downloaded=false` 等字段
- [x] 测试：reference 非空、manifest 引用记录 的用例存在且通过

## Task 5: manifest 完整性与 status 推导
- [x] `ManifestFile.checksum_sha256` 存在，落盘时对每个文件计算并写入
- [x] 包内生成 `checksums.txt`（path → sha256）
- [x] `package_info` 含 `pipeline_version`（由 `PIPELINE_VERSION` 常量填充）
- [x] `status` 推导：0 文件/REQUIRED 缺失→failed、部分缺失→partial、全满足→complete
- [x] 测试：checksum 一致性、status 三态、pipeline_version 的用例存在且通过

## Task 6: 静默降级显式化
- [x] `ManifestFile.data_source_quality` 默认 "unknown"；assemble 移除 `or "fallback"`
- [x] `ParsedItem.is_fallback` 从 `RetrievalResult.is_fallback` 透传，`ManifestFile.is_fallback` 记录
- [x] 测试：真实 URDF 不标 fallback、is_fallback 透出 的用例存在且通过

## Task 7: 并行检索 + 超时预算
- [x] `settings.per_req_timeout` 存在（默认 60.0）
- [x] `node_retrieve_data` 用 `asyncio.gather` 并行，单需求超时记 error 不阻塞整体
- [x] README 并行描述与实现一致
- [x] 测试：并行汇总、超时不阻塞 的用例存在且通过

## Task 8: 全量回归与端到端
- [x] `pytest tests/ -q` 全量通过（595 passed, 1 skipped, 9 deselected）
- [x] 冒烟脚本（adapters）通过（arxiv/github/zenodo/huggingface 均正常）
- [x] 真实流程端到端核对：多节点 provenance、checksum、status 非恒 complete、降级显式标记、URDF 资产自包含（6 项核对通过；项 4 部分通过——package:// 协议约定不下载、MJCF include 未递归，记录为 P2 建议）
