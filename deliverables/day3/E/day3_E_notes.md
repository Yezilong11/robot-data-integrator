# Day3 E 工程师交付说明（修订版）

## 1. 基本信息

修订日期：2026-08-16
角色：E 产品工程师
任务类型：多源交叉测试复核、前端流程稳定性观察、操作手册第二版修订
运行模式：真实流程
审查决定：satisfied

## 2. 修订说明

本文件根据 Day3 审查意见修订，主要修正以下内容：

1. `ms_004` / `ms_007` 的入库记录执行时间均为 2026-08-14，属于 Day2 已完成记录；Day3 notes 不再表述为“今日新执行”。
2. `ms_007` 的判定按 A 已确认口径更新为 `PASS_WITH_FALLBACK`：GraspNet 仅返回元数据 JSON 属显式降级，达标。
3. `ms_004` 仍判定为 `FAIL`：YCB mesh 检索超时属于必需需求真缺失，且失败 case 必须补充 `05_error.png`。
4. 已补充前端操作手册第二版 `frontend_manual_v2.md`，即使页面步骤未发生重大变化，也记录已核对项与踩坑记录。

## 3. Day2 已完成 case 复核

### 3.1 `ms_004`

输入目标：

```text
UR5 with Robotiq 2F-85 grasps YCB apple
```

执行记录：

```text
records/ms_004/record.json
```

截图目录：

```text
records/ms_004/screenshots/
```

当前截图应包含：

```text
01_input.png
02_progress.png
03_package.png
04_validation.png
05_error.png
```

判定：

```text
FAIL
```

失败分类：

```text
P2_RETRIEVE
```

主要原因：

1. `req_000` robot_urdf 通过 Robotiq 源真实获取。
2. `req_001` mesh 在 YCB 源检索超时，属于必需需求真缺失。
3. `req_002` grasp 通过 GraspNet 显式降级为元数据 JSON，但未获得真实 npz。
4. 数据包仅满足部分需求，不满足该多源 case 的完整输出要求。

补充说明：

`records/ms_004/screenshots/05_error.png` 已补齐，并已在 `records/ms_004/record.json` 的 `screenshots` 字段追加条目：

```json
{
  "file": "screenshots/05_error.png",
  "desc": "报错截图：ycb mesh 检索超时"
}
```

### 3.2 `ms_007`

输入目标：

```text
抓取 YCB 香蕉（未指定仿真器）
```

执行记录：

```text
records/ms_007/record.json
```

截图目录：

```text
records/ms_007/screenshots/
```

判定：

```text
PASS_WITH_FALLBACK
```

口径依据：

A 已按《判定口径纪要_C数据源类.md》§6 确认：GraspNet 仅返回元数据 JSON 属显式降级，若 `missing_items` 中有 reason 与 alternatives，且降级可追溯，则判 `PASS_WITH_FALLBACK`。

主要原因：

1. YCB banana mesh 已真实获取，输出 `objects/req_000.stl`。
2. GraspNet 真实 npz 不可得，系统返回元数据 JSON / 参考入口。
3. 该降级在 `record.json`、`missing_items`、`notes` 中均有明确说明，属于显式降级。
4. 本 case 未指定仿真器，系统未强制生成 `sim_config`，符合预期。

## 4. Day3 新执行补测

根据审查意见，Day3 需要至少新增执行 1 道与 Day2 不同的交叉多源题。本次已补测：

```text
ms_006
```

输入目标：

```text
用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词）
```

执行记录：

```text
records/ms_006/record.json
```

截图目录：

```text
records/ms_006/screenshots/
```

当前截图包含：

```text
records/ms_006/screenshots/01_input.png
records/ms_006/screenshots/02_progress.png
records/ms_006/screenshots/03_package.png
records/ms_006/screenshots/04_validation.png
```

判定：

```text
PASS_WITH_FALLBACK
```

主要原因：

1. 目标解析成功，生成 `robot_urdf`、`mesh`、`grasp`、`sim_config` 四条数据需求，与 expected 匹配。
2. 数据包 `package-20260816-095609` 已生成，落盘 4 个文件，`missing_items` 为 0。
3. 校验结果为 0 error / 10 warning，warning 主要来自完整度、置信度与 fallback 输出路径提示。
4. `franka` 与 `mujoco` 主源出现源级超时，但系统继续走 fallback，最终完成产包，属于显式降级。
5. `runtime_check` 因本地未安装 MuJoCo 被标记为 skipped，仅做 XML 语法校验；该项属于环境能力限制，不记为前端失败。

本 case 是 Day3 补充的新执行记录，不再使用 `ms_004` / `ms_007` 的 Day2 内容顶替 Day3 新执行要求。

## 5. 前端流程稳定性观察

基于 `ms_004` / `ms_007` 已完成记录复核，前端流程整体表现如下：

1. 目标输入页可正常输入目标并选择真实流程。
2. 进度展示页可展示阶段进度、数据需求状态、provenance 与 state_summary。
3. 数据包审查页可展示数据包目录和 manifest。
4. 校验与缺失项页可展示 validation_issues 与 missing_items。
5. human_review 审查决定为 satisfied 后流程可继续。

未观察到以下 `P6_FRONTEND` 问题：

1. 页面卡死。
2. 按钮无响应。
3. interrupt 卡死。
4. resume 失败。
5. 后端失败但前端无错误展示。
6. 数据包生成但前端不展示。

## 6. 今日 E 端结论

1. 已修正 `ms_007` 判定理解：不再按 `FAIL/P2_RETRIEVE` 记录，而按 `PASS_WITH_FALLBACK` 处理。
2. 已确认 `ms_004` 仍为 `FAIL/P2_RETRIEVE`，并补齐失败截图条目。
3. 已补交 `frontend_manual_v2.md`，记录页面核对项与踩坑记录。
4. 已补充 Day3 新交叉多源题 `ms_006` 的真实执行记录与 4 张截图，判定为 `PASS_WITH_FALLBACK`。

## 7. 待办

1. 提交前运行 JSON 校验，确认 `records/ms_006/record.json` 可解析。
2. 提交前确认 `records/ms_006/screenshots/` 下 4 张截图均已入库。
3. 如审查方要求进一步复核 fallback 细节，再补充 package manifest 截图或数据包路径说明。
