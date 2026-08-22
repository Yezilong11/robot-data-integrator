# Tasks

> 依据 `spec.md` 与已批准计划 `.trae/documents/二轮测试问题修复计划.md`。执行顺序：P0 → P1 → P2 → 回归。共享文件冲突组（同一文件禁止并行编辑）：`validate.py`（Task 1/3/5）、`base.py`（Task 3）、`edges.py`（Task 5）、`manage_test_records.py`（Task 8/9）。

## P0 内容有效性把关

- [x] Task 1: P0-A 横切内容/语义校验层（`src/rdi/graph/nodes/validate.py`）
  - [x] 1.1 新增常量 `_PLACEHOLDER_BYTE_THRESHOLD = 200`；新增 `_is_metadata_proxy(item) -> tuple[bool, str]`（reference 非空 / DatasetSummary 且 file_tree 空 / <200B 且 fallback 来源）
  - [x] 1.2 新增 `_semantic_mismatch(req, item) -> str`：`_extract_semantic_terms`（object_name + keywords + description 的 YCB 中英名单/YCB id、泛词过滤）与 `_item_identity_text`（name + source_url 末两段 + data title/description 前 200 字符）；仅 GRASP/MESH/ROBOT_URDF/SIM_CONFIG 启用；术语为空跳过
  - [x] 1.3 `node_validate` 主循环接入：每个 ParsedItem 依次跑占位检测与语义匹配，命中即 ERROR（`context={"issue_type": "content_validity"}`）；`_check_loadability` 保留格式/加载跳过但内容校验不受 is_fallback 豁免
  - [x] 1.4 `ponytail:` 注释标注轻量规则上限与升级路径
  - [x] 1.5 验证：`tests/unit/graph/test_validate_content_validity.py`——占位代理（reference/DatasetSummary 空 file_tree/<200B fallback）各命中 ERROR；语义 mismatch（UR5←franka、apple←coffeemaker）命中、合法匹配不误报、术语为空跳过

- [x] Task 2: P0-B assemble 排除占位项（`src/rdi/graph/nodes/assemble.py`）
  - [x] 2.1 `node_assemble` 处理 parsed_data 前，收集 `state.validation_issues` 中 `context["issue_type"]=="content_validity"` 的 ERROR 对应 req_id 集合
  - [x] 2.2 这些 req 不写入 manifest_files，转为追加 MissingItem（reason="内容有效性未通过：" + 原 issue message），使 `_derive_package_status` 判 partial（非必需）/ failed（REQUIRED）
  - [x] 2.3 验证：`tests/unit/graph/test_assemble.py` 新增——占位项（0~116B 元数据）包判 partial/failed，manifest 无该文件且有 MissingItem

- [x] Task 3: P0-C URDF mesh 缺失显性化（`src/rdi/adapters/base.py` + `src/rdi/graph/nodes/validate.py`）
  - [x] 3.1 `_download_xml_with_assets`：下载失败资产收集写入返回 `metadata["assets_missing"]`（远程分支）；`_local_assets_from_xml` 本地缺失同样记录；更新全部调用点（franka/allegro/robotiq/mujoco/isaac/ycb 等）透传 metadata
  - [x] 3.2 `parse_convert.py`：把 `raw.metadata.get("assets_missing")` 透传到 ParsedItem（metadata 或 warnings）
  - [x] 3.3 `_validate_urdf_loadability`：raw_bytes 缺失分支也执行 XML 引用核对（复用 `_missing_urdf_assets`）；结合 assets_missing 判 ERROR「引用的外部资源缺失: …」
  - [x] 3.4 验证：`tests/unit/adapters/test_base_assets_missing.py`（下载失败→assets_missing 记录）；`tests/unit/graph/test_validate.py`（缺失 mesh 判 ERROR）

- [x] Task 4: P0-D DatasetSkill markdown 消费（`src/rdi/skills/dataset_parse.py`）
  - [x] 4.1 新增 `_parse_markdown`：首个 `# ` 标题 + 首个非空段 description，file_tree 空，返回 fallback summary（success=True, is_fallback=True, data_source_quality="fallback", completeness_pct=55, confidence=0.6, warnings=["仅数据集摘要（markdown），未下载数据文件"]）
  - [x] 4.2 `process` 接入 fmt=="markdown"|"md" 分支；fmt 未知但内容 markdown 特征（`# `/`##` 开头）同样走该分支
  - [x] 4.3 验证：`tests/unit/skills/test_dataset_markdown.py`（README→fallback summary 字段全对）

## P1 检索与解析

- [x] Task 5: P1-A validate 重试路由区分检索轴（`src/rdi/graph/nodes/validate.py` + `src/rdi/graph/edges.py`）
  - [x] 5.1 `node_validate` 缺失类（missing 需求、result.data 为 None）issue 补 `context["issue_type"]="retrieval_axis"`
  - [x] 5.2 `route_after_validate`：全部 ERROR 均为 retrieval_axis 且无新增 retry_req_ids → 返回 "pass"；否则 retry（≤3 不变）
  - [x] 5.3 验证：`tests/unit/graph/test_edges_retrieval_axis.py`（检索轴全失败直出 pass；存在内容 ERROR 仍 retry）

- [x] Task 6: P1-B parse_goal 解析偏移修复（`src/rdi/graph/nodes/parse_goal.py`）
  - [x] 6.1 `_STRONG_TYPE_KEYWORDS[GRASP]` 增加：抓取标签/抓取标注/抓取规划/grasp label/grasp annotation/grasp planning
  - [x] 6.2 `_normalize_datareq` 前置单向消歧：当前判定 DATASET 且文本含上述 GRASP 数据内容词 → 改写为 GRASP
  - [x] 6.3 验证：`tests/unit/graph/test_parse_goal_disambiguate.py`（ss_graspnet_004 类 → GRASP；"机器人抓取数据集" 类仍 DATASET）

- [x] Task 7: P1-C LLM 列表输出归一化（`src/rdi/intelligence/client.py`）
  - [x] 7.1 `call_structured` 校验失败分支：捕获 ValidationError，对 list[str] 类型字段按 `[，,、;;；\s]+` 拆分字符串为数组后重试一次；仍失败走原降级
  - [x] 7.2 验证：`tests/unit/intelligence/test_client_list_normalization.py`——qwen-max 逗号字符串归一化通过；非列表字段不改动

## P2 工具与记录治理

- [x] Task 8: P2-A 脚本枚举与旧值映射（`scripts/manage_test_records.py`）
  - [x] 8.1 `ALLOWED_FAILURE_CATEGORIES` 更新为八类：P1_PARSE / P2_RETRIEVE / P3_SOURCE / P4_FORMAT / P5_LLM / P6_VALIDATE / P7_PACKAGE / P8_OTHER
  - [x] 8.2 旧值兼容映射：P5_RUNTIME→P6_VALIDATE、P6_FRONTEND→P8_OTHER、P7_ENV→P8_OTHER（登记 WARNING 非 ERROR）
  - [x] 8.3 validate_record 对 `runtime_check`/`vs_expected` 非字符串给出明确报错文案（行为不变，仅文案与映射）
  - [x] 8.4 验证：`uv run python scripts/manage_test_records.py all` 无新 ERROR（记录层面）；旧值 ss_code_github_001(P5_RUNTIME) 映射 WARNING ✓

- [x] Task 9: P2-B 台账 round 字段（`scripts/manage_test_records.py` + `records/_management/progress.csv`）
  - [x] 9.1 台账输出增加 `round` 列（由分配清单行序推导：前 63 行 round=1，其余 round=2，与 git 59f2cde 一轮题库精确吻合）
  - [x] 9.2 重新生成 progress.csv：round=1 筛选 63 行、round=2 筛选 59 行（122 行全量核对通过）

## 回归与清单

- [x] Task 10: 回归验证与行动清单（依赖 Task 1-9）
  - [x] 10.1 `uv run pytest tests/ -q` 全量通过（867 passed, 1 skipped, 9 deselected；含新增用例 + 既有回归）
  - [x] 10.2 生成 `docs/fix_actions_checklist.md`：截图缺失清单（按成员 A/C/D/E/F，合规 14.8%→104 题缺失）、一轮补正（ss_ycb_001/002/003、ss_robotiq_001~003、ms_003/004、ss_huggingface_002 等，非截图 ERROR 全列）、一轮 15 FAIL 处置表、122 题复核分配（F 复核 A/D、A 复核 C/E、C/E 互核 F，组长终审）、P0 补位（7/12→≥8，缺口 5 题 + 优先回归队列）
  - [x] 10.3 统计重算并核对：progress.csv 含 round 列（round=1 63 行 / round=2 59 行，122 行核对通过）；重算统计可用率 59.0% 与修复前基准一致，如实反映"代码修复已落地、记录待成员动作后重跑"

# Task Dependencies

- [Task 2] 依赖 [Task 1]（validation_issues 的 content_validity 标记是 assemble 排除依据）
- [Task 3] 依赖 [Task 1]（validate 接入 assets_missing 判 ERROR）；3.2 依赖 3.1
- [Task 5] 依赖 [Task 1]（issue context 机制复用）
- [Task 10] 依赖全部任务

# 并行执行建议

- 阶段 P0：Task 1 → Task 2/3/4（Task 2 依赖 1；Task 3、4 与 Task 2 文件不冲突可并行；注意 validate.py 仅 Task 3 与 Task 1 共用，串行）
- 阶段 P1：Task 5（依赖 Task 1）→ Task 6/7（文件独立，可与 Task 5 并行）
- 阶段 P2：Task 8、9 串行（同一脚本）
- 回归：Task 10