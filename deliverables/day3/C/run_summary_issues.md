# Day3 C 运行问题与解决方案（run_summary_issues）

> 角色：C ｜ 日期：2026-08-15 ｜ 说明：项目 ad2581f 优化后重跑 43 单元遇到的问题、根因、解决方案与遗留待裁定项

## 一、执行过程概述

按 `Day3-C执行中段与多源交叉计划.md` 执行 43 个执行单元（批 1 二十题 + 批 2 十九题 + 批 3 三题 + ms_004 交叉），每 case 产出 `record.json` + 8 张全页截图（中间态 4 + 最终态 4）。

**执行方式**：前端真实流程，Playwright 无头驱动 Edge（`channel="msedge"`），沿用已验证流程（填目标 → 运行 → 等「已生成中间结果」→ 截中间态 → 继续运行 → 等「运行完成」→ 截最终态）。

**代码状态**：项目已按 `ad2581f`（arxiv fmt=json 降级消费适配 + 检索源级子预算）优化；本轮不修改任何项目代码（仅 `.env` 的 LLM key 由用户提供新值）。

## 二、遇到的问题与解决方案

### P1（本轮主要问题）：dashscope 免费额度耗尽，LLM 403 → 19 题解析出 0 需求

**现象**：批 2 执行中途（约 ss_dexgrasp_002 起），所有后续 case 在 14s 内快速完成且 `manifest.total_requirements=0`（`retrieve.none: no_requirements`）；日志显示 `HTTP 403 Forbidden`。

**根因**：dashscope（qwen-plus）账号**免费额度耗尽**（`AllocationQuota.FreeTierOnly`：`Free quota exhausted`）。LLM 调用失败被静默降级为空需求列表，parse_goal 解析出 0 需求 → 后续 retrieve/parse/validate 全部跳过 → 空包 `status=failed`。

**影响**：批 2 后 15 题 + 批 3 3 题 + ms_004 共 19 题首轮运行全部空结果（非真实行为）。

**解决方案**：
1. 用户提供新 key（`sk-ws-H.EDMI...`）并更新 `.env`，直接测试 `LLM_OK: ok` 确认恢复。
2. 重启前端实例加载新 key（PID 重启，HTTP 200）。
3. 用批处理脚本对受影响的 19 题**全部重跑**，均产出真实 manifest（耗时 20~136s/题，非 14s 空结果），证据覆盖原空结果。

**遗留**：LLM 失败静默降级为空需求（而非报错）是潜在风险点——生产环境建议对 LLM 调用失败给出显式错误，避免把"API 不可用"误判为"目标无需求"。

### P2：Gradio Dataframe 需求状态表解析偏移

**现象**：从 `body.innerText` 解析「数据需求状态」表时列错位（如 `req_id` 列读到表头、`req_type` 读到 `req_000`）。

**根因**：Gradio 5 Dataframe 单元格含内嵌换行（`\t\n`），按行/列切分时 token 数不稳定；且需求为 0 时仅有表头（7 token）。

**解决方案**：record 生成以 **manifest.json 为权威证据**（files/missing_items/quality_report），req_type 通过多源合并推断（validation_text 正则 + format 映射 + reason 关键词 + req_table 兜底）；`vs_expected` 对无法确定的 case 记 `unknown` 并注明。

### P3：Edge 关闭时沙箱文件访问告警（不影响结果）

**现象**：批处理脚本结束关闭浏览器时，命令行输出大量 Windows 凭据缓存路径被沙箱拦截的告警（IdentityCache/TokenBroker/OneAuth），退出码 1。

**处置**：告警发生在**所有证据落盘之后**（截图/证据 JSON 均完整，见各 case），不影响交付物；未视为运行失败。

## 三、优化效果对比（与优化前一轮对比）

| 维度 | 优化前一轮 | 本轮（ad2581f 后） |
|---|---|---|
| 总 fail 数 | 37 / 43（86%） | 22 / 43（51%） |
| PASS + PASS_WITH_FALLBACK | 6 | 21 |
| arxiv 系（P4_FORMAT） | 4 题全 FAIL | 4 题全 PASS_WITH_FALLBACK（fmt=json 降级消费生效） |
| grasp/抓取 歧义（P1_PARSE） | 14 题 | 0 题（parse_goal 优化生效） |
| mujoco 系 | 3 FAIL + 1 FALLBACK | 003/004/005 PASS_WITH_FALLBACK（mujoco_menagerie 命中） |

> 结论：**优化（ad2581f）在 parse_goal 与 arxiv 降级链路上显著生效**；剩余 FAIL 集中在数据源侧（graspnet/ycb/dexgrasp 本地数据缺失 → P3_SOURCE）与多需求类型错配（P4_FORMAT），属已知 8 源 fetch 缺陷与 LLM 多需求解析范畴，非本轮优化目标。

## 四、待裁定项（提交 A）

1. **ieee 三题**：预期 P7_ENV（无 key），实际 arxiv/pwc 检索超时判 P2_RETRIEVE——以实际行为为准，还是显式 blocked-by-user？
2. **mujoco_001/002、isaac_002、github_002**：LLM 多解析出 ROBOT_URDF 需求导致类型错配整题 FAIL——是否按需求级判定（SIM_CONFIG/ROBOT_URDF 部分成功）？
3. **ms_004**：ROBOT_URDF 成功、MESH/GRASP 缺失（P3_SOURCE），与 A 的 ms_001/ms_002 差异，结果以本轮为准？
4. **P3_SOURCE 共 12 题**：graspnet/ycb/dexgrasp 本地数据缺失为高频根因，建议 Day4 补本地数据集目录；HF model_info.json 解析失败建议核查 fetch 契约。
5. **LLM 失败静默降级**：建议对 LLM 调用异常给出显式错误而非空需求（本轮 403 事件暴露）。

## 五、环境与工具

- 前端实例：`uv run python -m rdi.frontend.app`（127.0.0.1:7860，Gradio）
- 浏览器：Playwright + Edge headless（`channel="msedge"`）
- LLM：qwen-plus @ dashscope（兼容模式），mode=real；**执行中因免费额度耗尽更换 key**
- 临时脚本存放于 `scripts/_*.py`，跑完即删
