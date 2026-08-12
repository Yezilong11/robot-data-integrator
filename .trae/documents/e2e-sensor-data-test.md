# SENSOR_DATA 端到端测试计划

## Summary
用系统正式后端入口 `build_graph().ainvoke()` 驱动端到端流程（与 Gradio 真实流程同代码路径，[app.py:267 run_graph](file:///d:/robot-data-integrator-latest/src/rdi/frontend/app.py)），让 LLM 真实解析目标生成数据需求，记录 SENSOR_DATA 在完整系统流程里的表现。数据来源两者都试：① 系统自动联网搜（GitHub/Zenodo Adapter）② 若搜不到，用本地真实末端 F/T CSV 注入后半段流程（parse_convert → validate → assemble）。

## Current State Analysis（基于 Phase 1 探索）

### 系统端到端流程（[builder.py](file:///d:/robot-data-integrator-latest/src/rdi/graph/builder.py)）
```
parse_goal(LLM 解析目标→DataReq) → retrieve_data(Adapter 联网搜)
→ parse_and_convert(Skill 解析) → validate → assemble_package → human_review → END
```

### 三个已确认的阻塞点
1. **LLM key 不匹配（阻塞）**：[client.py:38](file:///d:/robot-data-integrator-latest/src/rdi/intelligence/client.py#L38) 读 `settings.llm_api_key`（对应环境变量 `LLM_API_KEY`），但 [.env](file:///d:/robot-data-integrator-latest/.env) 用的是 `QWEN_API_KEY`。当前 `llm_api_key=""`，parse_goal 会降级返回空需求 → 测不到 SENSOR_DATA。
2. **SENSOR_DATA 无专门 Adapter**：[retrieve_data.py:116](file:///d:/robot-data-integrator-latest/src/rdi/graph/nodes/retrieve_data.py#L116) 调 `select_adapter(SENSOR_DATA)` 返回 GitHub/Zenodo 通用搜索源，用 keywords 搜，不会用本地 CSV。搜 "franka force torque" 大概率返回代码仓库而非时序 CSV → missing。
3. **Hermes/ChromaDB**：[retrieve_data.py:22](file:///d:/robot-data-integrator-latest/src/rdi/graph/nodes/retrieve_data.py#L22) 用真实 `HermesEngine`，可能依赖 ChromaDB + Embedding。[run_second_integration_demo.py:36](file:///d:/robot-data-integrator-latest/scripts/run_second_integration_demo.py#L36) 用 `_NoOpHermesEngine` 禁用了它。

### 已有资产
- 修复后的 SensorDataSkill（5 个修复点已完成，13 passed）
- 本地真实末端 F/T 数据：`data/sensor_real/ft_end_effector_prepared.csv`（6 路 F/T，5152 行，83.33Hz）
- 组长新 key：`sk-ws-H.EDDRRPH.r5sJ.MEYCIQCXoJ8vcCuwvfH35PzRObzilTPaUjUV0iNjfo0oNLEwhQIhAMsZbFiVOYa-ciEhQ75r-RcT9Gg4T12GhnwJsw3oiumc`

## Proposed Changes

### 步骤 1：修 .env LLM key（前置，必须）
- 在 [.env](file:///d:/robot-data-integrator-latest/.env) 加一行 `LLM_API_KEY=<组长新key>`（保留原 QWEN_API_KEY 不删，避免破坏其他依赖）
- 确认 `llm_model` / `llm_base_url`：settings 默认值 `qwen-plus` / `https://dashscope.aliyuncs.com/compatible-mode/v1` 已正确（阿里云 dashscope，国内可达，不需梯子）。若 .env 的 QWEN_MODEL 不被读取（字段名不匹配），默认值仍够用，无需改。
- 验证：`uv run python -c "from rdi.config import settings; print('key=', settings.llm_api_key[:20], 'model=', settings.llm_model)"`（key 非空即通）

### 步骤 2：写端到端驱动脚本 `scripts/run_e2e_sensor_test.py`
**这不是测试脚本**（不直接调 skill），而是驱动系统正式 LangGraph 流程，等价于 Gradio 真实流程的后端调用。内容：
- `from rdi.graph.builder import build_graph`
- `user_goal = "获取 Franka Panda 机器人的末端力/力矩传感器时序数据，用于接触力分析与抓取接触检测"`（明确提到"力/力矩传感器时序数据"，引导 LLM 生成 SENSOR_DATA 需求）
- 不替换任何节点（真实 LLM parse_goal，不绕过）
- `state = {user_goal, iteration_count:0, provenance:[], errors:[], review_decision:"satisfied", user_feedback:[]}`
- `result = await graph.ainvoke(state, config={"configurable":{"thread_id":"e2e-sensor-test"}})`
- 打印完整结果：`data_requirements`（LLM 生成了哪些需求，含 SENSOR_DATA?）、`retrieval_results`（每个需求搜到什么）、`parsed_data`（skill 解析结果）、`validation_issues`、`experiment_package`（manifest/落盘）

### 步骤 3：第一轮 — 系统自动搜（真实端到端）
跑驱动脚本，记录：
- LLM 是否生成 SENSOR_DATA 需求？（parse_goal 真实调用，看 data_requirements 里 req_type=sensor_data）
- 若生成：retrieve_data 对 SENSOR_DATA 联网搜（GitHub/Zenodo），结果 success/missing/error？
- 若 success：SensorDataSkill 解析结果（signals/sample_rate/validation）
- 若 missing/error：记录原因（这是真实结论 — 暴露系统获取 SENSOR_DATA 的短板）

**Hermes 处理**：先不禁用（真实流程）。若 Hermes/ChromaDB 报错导致流程中断，加 `_NoOpHermesEngine` 替换（参考 [run_second_integration_demo.py:49](file:///d:/robot-data-integrator-latest/scripts/run_second_integration_demo.py#L49)）重跑，记录两份结果（真实 Hermes 失败 + 禁用 Hermes 成功）。

### 步骤 4：第二轮 — 本地 CSV 注入（若第一轮 SENSOR_DATA missing）
若系统搜不到 SENSOR_DATA 数据，用本地真实 CSV 跑后半段流程，测 skill 在系统里的完整表现：
- 在驱动脚本里加一个 `--inject-local` 分支
- 先跑 parse_goal（真实 LLM）拿 requirements（确认有 SENSOR_DATA 需求）
- 手动构造 `RetrievalResult`：`data=RawData(data=<ft_end_effector_prepared.csv bytes>, format="csv", source=DataSource.GITHUB)`，注入 `state["retrieval_results"]["req_xxx"]`
- 跑 `node_parse_convert` → `node_validate` → `node_assemble`（分阶段调用，绕过 retrieve_data）
- 记录：SensorDataSkill 在系统流程里解析 6 路 F/T 信号、采样率、validation、落盘 manifest

### 步骤 5：记录结果 + 对比
- 两轮结果都记录（系统自动搜 / 本地 CSV 注入）
- 对比修复前后：修复前静默失败（success=True/signals=0），修复后空信号 success=False 或合规数据正确解析
- 数据包 manifest / validation / provenance 截图给组长

## Assumptions & Decisions
1. **运行方式**：驱动 `build_graph().ainvoke()`（用户选定），不操作 Gradio UI。与 Gradio 真实流程同代码路径，符合组长"喂给系统"。
2. **目标设计**：目标明确提到"力/力矩传感器时序数据"，引导 LLM 生成 SENSOR_DATA。若 LLM 不生成，调整目标措辞或分析 prompt（[intelligence/prompts.py](file:///d:/robot-data-integrator-latest/src/rdi/intelligence/prompts.py)）。
3. **Hermes**：先真实跑，出错才禁用（记录真实问题）。
4. **本地 CSV 注入**：绕过 retrieve_data，构造 RetrievalResult 跑后半段。这是"系统流程里测 skill"，不是完整端到端，但能验证 skill 在 parse_convert/validate/assemble 链路的表现。
5. **不新增 Adapter**：不加 LocalFileAdapter（避免过度工程）。本地 CSV 注入用驱动脚本构造 RetrievalResult 即可。
6. **网络**：用户已开梯子。LLM 走阿里云 dashscope（国内可达），Adapter 走 GitHub/Zenodo（需梯子）。
7. **key 安全**：新 key 写入 .env（gitignore，不入库）。旧 QWEN_API_KEY 保留不删。

## Verification Steps
1. `uv run python -c "from rdi.config import settings; print(settings.llm_api_key[:20])"` — key 非空
2. 驱动脚本第一轮跑通（不崩溃），打印 data_requirements / retrieval_results
3. 确认 LLM 生成了 SENSOR_DATA 需求（data_requirements 含 req_type=sensor_data）
4. 第一轮记录系统自动搜结果（success/missing + 原因）
5. 第二轮（若触发）本地 CSV 注入：6 路信号识别、采样率合理、落盘 manifest 含 sensor 数据
6. 两轮结果对比修复前后行为
7. 截图/日志可发给组长

## 风险与应对
- **LLM 不生成 SENSOR_DATA**：调整目标措辞；最坏情况手动构造 SENSOR_DATA 的 DataReq 跑后半段（记录 LLM 局限）
- **Hermes/ChromaDB 出错**：禁用 Hermes 重跑
- **Adapter 联网搜超时**：梯子已开；超时则记录为 error，转第二轮
- **LLM 调用失败（key/网络）**：确认 key 配置；dashscope 国内可达
