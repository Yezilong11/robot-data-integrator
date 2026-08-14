# Day3 C 运行问题与解决方案（run_summary_issues）

> 角色：C ｜ 日期：2026-08-14 ｜ 说明：执行中遇到的问题、根因、解决方案与遗留待裁定项

## 一、执行过程概述

本轮按 `Day3-C执行中段与多源交叉计划.md` 执行，43 个执行单元（批 1 二十题 + 批 2 十九题 + 批 3 三题 + ms_004 交叉）全部跑完，每 case 产出 `record.json` + 8 张全页截图（中间态 4 + 最终态 4）。

**执行方式**：前端真实流程，Playwright 无头驱动 Edge（`channel="msedge"`），沿用 Day2 已验证流程（填目标 → 运行 → 等「已生成中间结果」→ 截中间态 → 继续运行 → 等「运行完成」→ 截最终态）。

## 二、遇到的问题与解决方案

### P1：早期批量脚本与探测脚本并发驱动前端，互相干扰

**现象**：会话恢复时发现之前的批处理任务仍在后台运行（`_progress.jsonl` 由它持续写入）；我新增的探测脚本与其并发操作同一前端实例，出现：
- 探测脚本等待状态长时间无输出（等待超时）
- 个别 case 出现 `TimeoutError: Page.wait_for_function ... exceeded`

**解决方案**：
1. 确认后台批量任务已退出后，再独占前端执行剩余 case（未改任何代码，仅调度顺序调整）。
2. 最终统一核对 `_progress.jsonl` 去重（同一 case 只保留最新一条）。

### P2：resume（继续运行）后 UI 状态长时间不更新

**现象**：个别 case 点「继续运行」后状态停留在「已生成中间结果」直到 600s 超时，最终态截图内容实际仍为中间态。

**根因**：截图后页面停留在「数据包审查」Tab，「继续运行」按钮不在可视 Tab 内，Playwright 点击时按钮不可见，异常被静默吞掉（`try/except: pass`），实际未触发 resume。

**解决方案**：点击「继续运行」前先切回「目标输入」Tab 再点击，并加 force 重试。修复后 resume 2–3s 即完成（用 `_probe_ui12` 验证）。

### P3：Gradio Dataframe 数据行不在 `<table>` 中，初始读取 source 为空

**现象**：首次脚本读取「数据需求状态」表格时 `source="none"`、`req=[]`。

**根因**：Gradio 5 的 Dataframe 表头渲染在 `<table class="header-table">`，数据行渲染在普通 div 结构；且首跑（interrupted 状态）时表格只有表头无数据行，需在 resume 完成后读取。

**解决方案**：改为从页面 `body.innerText` 解析「数据需求状态」区段（表头 6 列 → 数据行按 6 列切分），并在最终态之后读取；表格解析失败时兜底从 `state_summary` JSON 文本抓取 `req_type`。

### P4：mujoco_002/003/005 前端「运行失败」但磁盘有产物

**现象**：这三题 UI 状态为「运行失败」，但 `manifest.json` 显示 SIM_CONFIG 需求成功产出 15/69/15 个文件（MuJoCo XML + 资产）。

**根因**：LLM 同时解析出 ROBOT_URDF（期望 CanonicalRobot/URDF，实际返回 markdown，类型错配）与 SIM_CONFIG 两个需求；类型错配需求未满足导致整体运行标记失败。

**解决方案**：record 如实记录 —— `req_list=["SIM_CONFIG","ROBOT_URDF"]`、vs=mismatch、verdict=FAIL、failure_category=P1_PARSE；根因写入 `rootcause_c_20260814.json`（FAIL_GENERIC）。

### P5：ieee 系预期 P7_ENV，实际 P4_FORMAT

**现象**：`ss_ieee_001/002/003` 计划预期 P7_ENV（无 API Key，blocked-by-user），实际运行中 LLM 将源解析为 arxiv（fallback），随后 PDF 打开失败 → 判 P4_FORMAT。

**解决方案**：按实际行为记录（P4_FORMAT + source=arxiv + failure_reason=无法打开 PDF），并作为存疑项提交 A 裁定。

### P6：record.json 的 verdict 字段格式不统一

**现象**：早期脚本生成的 `verdict="FAIL"` + `failure_category="P2_RETRIEVE"` 与既有记录 `verdict="P2_RETRIEVE"` 格式不一致；`failure_reason` 出现重复拼接。

**解决方案**：统一脚本修正 —— FAIL 类 case 的 `verdict` 直接用分类码（P1_PARSE/P2_RETRIEVE/P3_SOURCE/P4_FORMAT/P7_ENV/PASS_WITH_FALLBACK），reason 去重；ms_004 补全 expected_req_types 与 retrieve 三条。

## 三、待裁定项（提交 A）

1. **ieee 三题**：以实际行为 P4_FORMAT 记录，还是按 blocked-by-user 记 P7_ENV？
2. **mujoco_002/003/005**：多需求中一个类型错配，整题 FAIL 是否合理；是否应按需求级判定（SIM_CONFIG 部分 PASS）？
3. **ms_004**：本轮 LLM 解析出 3 需求（URDF 成功、MESH/GRASP 缺失），与 A 的 ms_001/ms_002 差异记录，结果以本轮为准？
4. **P4_FORMAT 共 9 题**：arXiv 系 PDF 下载后「无法打开 PDF」为高频共性根因，建议作为 Day4 代码修复优先级。

## 四、环境与工具

- 前端实例：`uv run python -m rdi.frontend.app`（127.0.0.1:7860，Gradio）
- 浏览器：Playwright + Edge headless（`channel="msedge"`，因 ms-playwright 目录未装 chromium）
- LLM：qwen-plus @ dashscope（兼容模式），mode=real
- 临时脚本存放于 `scripts/_*.py`，跑完即删
