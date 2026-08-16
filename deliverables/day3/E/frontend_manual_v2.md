# 前端操作手册 v2

> 日期：2026-08-14  
> 角色：E 产品工程师  
> 适用范围：v3 真实流程测试、records 截图取证、流程异常记录  

## 1. 修订目的

本版本基于 Day2 / Day3 多源端到端 case 执行情况修订。当前页面操作步骤整体与 v1 保持一致，但补充了真实测试中的核对项、截图要求、失败截图要求、显式降级判定提醒，以及 `P6_FRONTEND` / `P7_ENV` 区分。

## 2. 启动前检查

进入项目目录：

```powershell
cd D:\glass\trae\robot-data-integrator-arch-langgraph
```

启动前端：

```powershell
uv run python -m rdi.frontend.app
```

打开浏览器：

```text
http://127.0.0.1:7860
```

如果 7860 被占用，可以关闭旧终端，或临时使用其他端口。

## 3. 真实流程操作步骤

### 3.1 目标输入页

1. 进入「目标输入」Tab。
2. 运行模式选择「真实流程」。
3. 从 `problem_set/problem_set.json` 复制对应 case 的 `target` 到实验目标输入框。
4. PDF 默认不上传，除非题目明确要求“根据上传论文 PDF”。
5. 本地文件注入默认留空，除非 case 明确要求指定本地文件。
6. 点击「运行」。

### 3.2 进度展示页

运行后切换到「进度展示」Tab，观察：

1. `state_summary` 是否返回。
2. 数据需求状态是否包含 `req_id`、`req_type`、状态、数据源、fallback、失败原因。
3. `provenance` 是否记录执行过程。
4. 阶段进度是否覆盖目标解析、数据检索、解析转换、质量校验、整合打包。

若阶段显示完成但数据需求或结果为空，需要在 `record.json` 的 notes 中说明。

### 3.3 数据包审查页

切换到「数据包审查」Tab，观察：

1. 是否生成数据包目录。
2. 是否展示 `manifest`。
3. `manifest` 中是否有 `files`、`missing_items`、fallback 或来源质量信息。
4. 数据包路径是否与 `record.json` 中记录一致。

### 3.4 校验与缺失项页

切换到「校验与缺失项」Tab，观察：

1. `validation_issues` 是否有 error / warning。
2. `missing_items` 是否明确列出缺失需求。
3. fallback 是否显式记录 reason 和 alternatives。
4. 如果失败，是否能看清错误原因。

### 3.5 human_review

如果流程进入人工审查：

1. 返回「目标输入」Tab。
2. 审查决定选择 `satisfied`、`revised` 或 `unsatisfied`。
3. 如选择 `revised` 或 `unsatisfied`，必须填写反馈。
4. 点击「继续运行」。
5. 如果 resume 卡死或失败，记录为 `P6_FRONTEND`。

## 4. 截图规范

每个 case 至少保留 4 张截图：

```text
01_input.png
02_progress.png
03_package.png
04_validation.png
```

失败 case 必须额外保留：

```text
05_error.png
```

截图保存位置：

```text
records/<case_id>/screenshots/
```

截图内容要求：

1. `01_input.png`：能看清输入目标、运行模式。
2. `02_progress.png`：能看清阶段进度、数据需求状态、provenance。
3. `03_package.png`：能看清数据包目录和 manifest。
4. `04_validation.png`：能看清 validation_issues 与 missing_items。
5. `05_error.png`：能看清报错信息或失败原因。

## 5. `record.json` 记录要求

每个 case 的记录文件位于：

```text
records/<case_id>/record.json
```

至少记录：

1. `case_id`
2. `input`
3. `executor`
4. `executed_at`
5. `env`
6. `observations`
7. `screenshots`
8. `verdict`
9. `failure_category`
10. `failure_reason`
11. `notes`

失败 case 的 `screenshots` 必须包含：

```json
{
  "file": "screenshots/05_error.png",
  "desc": "报错截图：简述失败原因"
}
```

## 6. 判定提醒

### 6.1 PASS

满足以下条件时可判 `PASS`：

1. 数据包完整。
2. 无 error。
3. 文件数量和格式满足 expected。
4. 数据来源符合预期。

### 6.2 PASS_WITH_FALLBACK

满足以下条件时可判 `PASS_WITH_FALLBACK`：

1. 数据包可用。
2. 存在显式 fallback 或 missing_items。
3. fallback 原因可追溯。
4. `missing_items` 中有 reason 和 alternatives。

注意：A 已确认，GraspNet 仅返回元数据 JSON 属显式降级；若降级可追溯，可判 `PASS_WITH_FALLBACK`。

### 6.3 FAIL

出现以下情况时判 `FAIL`：

1. 必需数据真缺失。
2. 无数据包。
3. 页面崩溃。
4. 文件不可用。
5. 静默降级。
6. 失败 case 缺少 `05_error.png`。

## 7. P6_FRONTEND 与 P7_ENV 区分

### 7.1 记为 P6_FRONTEND

以下属于前端或流程问题：

1. 页面卡死。
2. 运行按钮无响应。
3. interrupt 卡死。
4. resume 失败。
5. 后端失败但前端无错误展示。
6. 数据包已生成但前端不展示。
7. 页面字段与操作手册不一致且影响执行。

### 7.2 记为 P7_ENV

以下属于环境问题：

1. API Key 缺失。
2. 依赖缺失。
3. 端口占用。
4. 网络不可用。
5. 本地路径或权限问题。

## 8. 已核对项

基于 `ms_004` / `ms_007` 记录复核，已确认：

1. 真实流程入口可用。
2. 目标输入页可正常提交目标。
3. 进度展示页可显示阶段状态。
4. 数据包审查页可显示目录和 manifest。
5. 校验与缺失项页可显示 validation_issues 和 missing_items。
6. human_review 选择 satisfied 后可继续。
7. 失败原因可以通过 validation_issues / missing_items / provenance 追溯。

## 9. 踩坑记录

1. Day3 notes 不应把 Day2 已完成 case 写成“今日执行”。
2. `ms_007` 原按旧口径写为 FAIL/P2_RETRIEVE，现按 A 裁定改为 PASS_WITH_FALLBACK。
3. FAIL case 必须有 `05_error.png`，不能只用 validation_issues 替代。
4. 即使页面步骤没有变化，也需要交付操作手册第二版，记录已核对项和踩坑。
5. 新增 Day3 交叉多源题必须是真实新执行，不能复述 Day2 内容。

## 10. 后续补测建议

Day3 仍需补测至少 1 道与 Day2 不同的多源题，建议优先：

```text
ms_006
```

补测后需要新增：

```text
records/ms_006/record.json
records/ms_006/screenshots/01_input.png
records/ms_006/screenshots/02_progress.png
records/ms_006/screenshots/03_package.png
records/ms_006/screenshots/04_validation.png
```

若失败，额外新增：

```text
records/ms_006/screenshots/05_error.png
```
