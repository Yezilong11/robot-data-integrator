# C 角色二轮执行摘要（12 题摸底）

> 生成时间：2026-08-21
> 执行人：C｜复核：F（待复核）
> 依据：`assignment_overview.md`（C 二轮 12 题）+ `second_round_plan.md`（验收口径）
> 记录位置：`robot-data-integrator/records/<case_id>/`（record.json + screenshots/）
> 模型：qwen-plus（2026-08-21 换新 API key 后服务端真实流程逐题运行，见「已知偏差」）
> 截图分工：01/02/03（数据包文件内容）由 C 生成，04/05（前端 explorer/provenance 面板）由执行人 C 于浏览器逐题截图
> 截图口径：每 case 5 张 = ① manifest.json 内容 ② provenance.log 内容 ③ 主数据文件内容 ④ 前端 explorer 面板 ⑤ 前端 provenance 日志面板；FAIL 题 ③ 为"无主数据文件"说明图

## 1. 判定总览

| 判定 | 数量 | 可用率 |
|---|---:|---:|
| PASS | 1 | |
| PASS_WITH_FALLBACK | 7 | |
| FAIL | 4 | |
| 合计 | 12 | 66.7%（8/12） |

> 注：本次为 2026-08-21 晚间「服务端真实流程逐题重跑（qwen-plus）+ 浏览器截图」的最终结果；相比早间记录（qwen-turbo 批次），`ss_zenodo_006` 由 PASS 改为 FAIL（命中 markdown 格式不可消费），`ss_allegro_006` 由 PASS 改为 PWF（github 兜底）。

## 2. 逐题结果

| case_id | 源 | req_types | 优先级 | 判定 | 失败分类/说明 |
|---|---|---|---|---|---|
| ss_kinova_002 | github | robot_urdf | P1 | PASS_WITH_FALLBACK | 源偏移降级（Joajibola Kinova-Gen3-lite），URDF 落包 1 文件 |
| ss_allegro_006 | github | robot_urdf | P2 | PASS_WITH_FALLBACK | 源偏移降级（allegro_hand_model_v4），URDF 落包 1 文件 |
| ss_graspnet_004 | graspnet | grasp | P2 | FAIL | P1_PARSE：LLM 稳定解析为 dataset（题面含「数据集」），未命中 grasp |
| ss_graspnet_005 | graspnet | dataset | P2 | FAIL | P3_SOURCE：命中 github 源 DatasetSummary 但 0 文件落包 |
| ss_google_scanned_005 | google_scanned | mesh | P2 | FAIL | P3_SOURCE：mesh 检索持续未命中杯 mesh |
| ss_robotiq_005 | github | robot_urdf | P2 | PASS | real 命中（jsdelivr robotiq 2F-85），URDF+10 mesh 落包 11 文件 |
| ss_zenodo_006 | zenodo | dataset | P2 | FAIL | P4_FORMAT：命中 github README（markdown）DatasetSkill 不可消费，8/8 复现 |
| ss_sensor_github_001 | github | sensor_data | P2 | PASS_WITH_FALLBACK | 源偏移降级（zenodo 兜底） |
| ss_code_hf_001 | github | code | P2 | PASS_WITH_FALLBACK | 源偏移降级（github 兜底） |
| ss_mesh_gso_001 | google_scanned | mesh | P2 | PASS_WITH_FALLBACK | 降级命中（ycb 香蕉兜底 mesh） |
| ss_urdf_kinova_005 | github | robot_urdf | P2 | PASS_WITH_FALLBACK | 源偏移降级（ros_kortex Gen3），URDF+7 mesh 落包 8 文件 |
| ms_013 | github;hf | robot_urdf;sim_config;policy_model | P1 | PASS_WITH_FALLBACK | 多源端到端，落包 3 文件 |

## 3. 分层统计

- **按源**：kinova 0/0（重跑全命中 github，见源偏移）；allegro 0/0（同上）；github 4/4 可用；huggingface 1/1；franka/mujoco/hf 1/1；robotiq 1/1；google_scanned 1/2（ss_mesh_gso_001 可用、ss_google_scanned_005 FAIL）；graspnet 0/2；zenodo 0/1（ss_zenodo_006 FAIL）。
- **按 req_type**：robot_urdf 5/5 可用（含源偏移）；code 1/1；sensor_data 1/1；sim_config+policy_model（随 ms_013）1/1；mesh 1/2；dataset 0/2；grasp 0/1。
- **按优先级**：P1 2/2 可用；P2 6/10 可用（4 FAIL 全为 P2）。

## 4. FAIL 根因（多次运行均复现，非偶发）

1. **ss_graspnet_004**（P1_PARSE）：题面「我要做抓取规划，帮我找 GraspNet 数据集的抓取标签」含「数据集」强词，LLM（qwen-plus/qwen-turbo）均解析为 `dataset`，预期为 `grasp`；检索仅拿到 GraspNet 说明文档（markdown），非结构化抓取标签 → 核心需求未命中。建议组长 B 评估：题面歧义（关键词归一化）或增加「抓取标签→grasp」强词。
2. **ss_graspnet_005**（P3_SOURCE）：dataset 检索命中 github 源 DatasetSummary，但 Skill 未能产出可落盘文件（0 文件、包 missing）。与候选源顺序/查询词相关，建议复核 GraspNet 数据源可达性。
3. **ss_google_scanned_005**（P3_SOURCE）：mesh 检索持续未命中（google_scanned/ycb 均未产出杯 mesh），多次运行一致；同源 ss_mesh_gso_001（香蕉）经 ycb 兜底降级可用。建议复核 google_scanned 适配器对 cup 类查询的搜索逻辑。
4. **ss_zenodo_006**（P4_FORMAT）：dataset 检索命中 github 源 README（markdown），DatasetSkill 不支持该格式 → 0 文件落包，8/8 复现（qwen-plus）。原早间 qwen-turbo 运行命中 zenodo json（22036612）为 PASS，换模型/关键词后检索结果偏移到 github 源。与 ss_graspnet_005 同类（github 摘要不可消费），建议复核候选源排序与 DatasetSkill 对 github 摘要的消费分支。

## 5. 已知偏差（提交组长 B）

1. **截图口径（与 second_round_plan §9 Step 4「截图记录每个文件内容」一致）**：每 case 5 张——① `01_manifest.png`（manifest.json 内容完整图）② `02_provenance_log.png`（provenance.log 内容完整图）③ `03_req_file.png`（主数据文件内容完整图；FAIL 题无主数据文件，改生成"无主数据文件 FAIL 说明"图）④ `04_explorer.png`（前端 explorer 面板）⑤ `05_provenance_panel.png`（前端 provenance 日志面板，仅日志区、滚动全量多张拼接）。文件内容图因沙箱限制 Win11 记事本无法打开，改为用等宽字体将文件全文渲染为完整长图（内容等价于「打开后完整截图」；二进制主文件如 mesh STL 渲染二进制说明图）。12 份记录 `screenshots[]` 已同步更新（全部 5 条）。
2. **记录与前端运行包严格对应**：服务端逐题真实流程运行后，记录 `package.dir` 均同步为该题最新数据包；01/02/03 由 C 从该数据包生成，04/05 由执行人在浏览器中对同一运行界面截图，五张截图与记录指向同一数据包。为此 `ss_zenodo_006`（PASS→FAIL）、`ss_allegro_006`（PASS→PWF）、`ss_kinova_002`（保持 PWF 并显式源偏移）的判定已与各自实际运行对齐。
3. **API key 已更换**（2026-08-21）：用户提供新 key（`sk-ws-…EDPDXXI…`）已写入 `.env`，qwen-plus/turbo/max 探测均可用；本次逐题重跑与前端展示均用 qwen-plus。
4. **模型切换（历史）**：原 qwen-plus 免费配额耗尽（403 AllocationQuota.FreeTierOnly）；qwen-max 结构化输出不兼容（keywords/fallback_sources 输出为字符串而非数组 → LLMParseError）。换新 key 后 qwen-plus 已恢复，另出现偶发 `LLMParseError`（驱动脚本已按「缺需求/解析失败自动重试」处理）。
5. **failure_category 枚举**：以 second_round_plan §9 为准（`P1_PARSE/P2_RETRIEVE/P3_SOURCE/P4_FORMAT/P5_LLM/P6_VALIDATE/P7_PACKAGE/P8_OTHER`）。本轮 4 个 FAIL 使用 P1_PARSE/P3_SOURCE/P4_FORMAT。`manage_test_records.py` 脚本枚举已同步为计划版。
6. **前端展示机制**：为让执行人刷新浏览器即可看到运行结果截图，`/api/workspace` 返回最近一次完成的运行结果（decision_board）并回填目标到输入框；前端「日志」面板在资源管理器点击数据包时加载该包 provenance.log。
7. **full-repo 校验**：12 份二轮记录 `manage_test_records.py validate-records` 0 ERROR（仅 §2.4 放行类 WARNING 4 条：ms_013×2、ss_code_hf_001 format、ss_graspnet_004 补充需求）。全仓校验仍报告部分一轮记录（如 ss_ycb_001/002/003、ss_robotiq_002/003）的既有校验错误——非本次二轮执行引入，需团队另行排查。

## 6. 证据

- 记录：`robot-data-integrator/records/<case_id>/record.json`（12 份）
- 截图：`robot-data-integrator/records/<case_id>/screenshots/`——12 题均 5 张（01_manifest/02_provenance_log/03_req_file/04_explorer/05_provenance_panel；FAIL 题 03 为"无主数据文件 FAIL 说明"图）
- 执行日志：`robot-data-integrator/records/_rerun_c_round2_progress.jsonl`
- 复核：`reviewer` 待 F 复核后填写 `reviewer`/`reviewed_at`
