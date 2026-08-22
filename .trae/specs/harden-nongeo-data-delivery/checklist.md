# Checklist

- [x] `_SEMANTIC_REQ_TYPES` 含 DATASET / SENSOR_DATA / POLICY_MODEL，语义错配产 content_validity ERROR，不受 is_fallback 豁免
- [x] 术语为空（无 object_name/semantic_terms/keywords）时语义校验静默跳过，不误伤名词稀疏需求
- [x] `DataReq.semantic_terms` 字段存在；parse_goal LLM 提炼并落值；LLM 失败时为空且 validate 回退现有提取（fail-open，流水线不中断）
- [x] `select_target_file(tree, req_type)` 按扩展名白名单 + 名字信号给出候选排序；无候选返回空；四类型规则表齐全
- [x] huggingface POLICY / zenodo files[] / github contents 均已接文件树 → 定位 → HEAD 预检 →（≤max_fetch_bytes 下载落盘 | 超限 RawReference）
- [x] 超限文件本地零落盘，RawReference 含文件级 URL + size + reason
- [x] 每个未下载项产出 `download_guide.json`（status/reason/source_file_url/file_size/method_hint/selected_by/alternatives），manifest 标 `downloaded=false` + file_url + file_size（未新增 manifest 字段）
- [x] dataset/sensor/policy fallback 产物含 download_guide 结构
- [x] explain（explain_quality）注入未下载项清单；规则兜底自动 append 获取指引段，wget 命令恒在
- [x] assemble 校验锚点：downloaded=false 项缺 download_guide 或 explain 说明 → 完整性 ERROR
- [x] 验收口径：小文件下载 → PASS；超限 → FAIL（指引照给）；语义错配/指引缺失 → FAIL；GRASP 大归档超限全 FAIL 为预期
- [x] `uv run pytest tests/ -q` 全绿（955 passed）；42 题离线验证无既有 PASS 降级（真实网络全量重放属人工扩展验收，已在 tasks.md 注明）；日食音频案复跑被语义校验拦截