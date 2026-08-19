# ms_006 补测执行指引

> 目的：补齐 Day3 审查意见中“至少新增执行 1 道交叉多源题”的要求。
> 注意：本文件是补测指引，不是 `ms_006` 的正式执行记录。正式记录必须来自一次真实前端运行。

## 1. 题目信息

```text
case_id: ms_006
layer: multi_source
priority: P1
target: 用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词）
expected sources: franka, ycb, mujoco
expected req_types: robot_urdf, mesh, grasp, sim_config
expected min_files: 4
```

## 2. 启动前端

在项目根目录执行：

```powershell
cd D:\glass\trae\robot-data-integrator-arch-langgraph
uv run python -m rdi.frontend.app
```

浏览器打开：

```text
http://127.0.0.1:7860
```

如果端口被占用，先关闭旧的 Gradio 终端；如果仍无法释放，再换端口启动。

## 3. 前端输入

进入「目标输入」页：

1. 运行模式选择真实流程。
2. 实验目标输入：

```text
用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词）
```

3. PDF 不上传。
4. 本地文件注入留空。
5. 点击运行。

## 4. 截图要求

正式补测时至少保存：

```text
records/ms_006/screenshots/01_input.png
records/ms_006/screenshots/02_progress.png
records/ms_006/screenshots/03_package.png
records/ms_006/screenshots/04_validation.png
```

如果判定为 FAIL，额外保存：

```text
records/ms_006/screenshots/05_error.png
```

截图含义：

1. `01_input.png`：目标输入页，能看清 ms_006 输入目标与真实流程模式。
2. `02_progress.png`：进度展示页，能看清阶段进度、数据需求状态、provenance。
3. `03_package.png`：数据包审查页，能看清输出包目录和 manifest。
4. `04_validation.png`：校验与缺失项页，能看清 validation_issues 和 missing_items。
5. `05_error.png`：失败时的报错、超时或缺失原因截图。

## 5. record.json 填写要求

补测完成后新增：

```text
records/ms_006/record.json
```

记录至少包含：

1. `case_id`: `ms_006`
2. `input`: `用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词）`
3. `executor`: `E`
4. `executed_at`: 实际运行时间
5. `env`: 模型、base_url、分支、commit、运行模式
6. `observations.parse_goal`: 解析出的需求列表，以及与 expected 是否匹配
7. `observations.retrieve`: 每条需求的来源、状态、是否 fallback、错误原因
8. `observations.validate`: errors、warnings、runtime_check
9. `observations.package`: 数据包目录、manifest、file_count、missing_items_count、fallback_explicit
10. `screenshots`: 4 张基础截图；失败时追加 `05_error.png`
11. `verdict`: `PASS`、`PASS_WITH_FALLBACK` 或 `FAIL`
12. `failure_category` / `failure_reason`: 仅失败时填写

## 6. 判定口径提醒

可判 `PASS`：

1. 解析需求与 expected 基本匹配。
2. 数据包满足 `min_files = 4`。
3. 无必需数据真缺失。

可判 `PASS_WITH_FALLBACK`：

1. 主要流程跑通。
2. 某些数据源显式降级。
3. `missing_items` 或 manifest 中有 reason / alternatives，可追溯。

应判 `FAIL`：

1. 必需需求真缺失且无可追溯 fallback。
2. 无数据包。
3. 前端卡死、按钮无响应、resume 失败。
4. 失败 case 缺少 `05_error.png`。

## 7. 完成后更新

补测完成后，把 `day3_E_notes.md` 的第 4 节从“待补测”改为“已补测”，并追加：

```text
case_id: ms_006
verdict: <实际判定>
record: records/ms_006/record.json
screenshots: records/ms_006/screenshots/
简要原因: <真实执行观察>
```

然后执行 JSON 校验：

```powershell
Get-Content -Raw -Encoding UTF8 .\records\ms_006\record.json | ConvertFrom-Json | Out-Null
```
