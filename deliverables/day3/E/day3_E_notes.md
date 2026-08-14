# Day3 E 工程师执行说明

## 1. 基本信息

日期：2026-08-14  
角色：E 产品工程师  
执行任务：多源端到端 case 交叉测试与前端流程稳定性观察  
执行 case：ms_004  
输入目标：UR5 with Robotiq 2F-85 grasps YCB apple  
运行模式：真实流程  
审查决定：satisfied  

## 2. 执行结果概述

本次执行 `ms_004`，系统成功完成目标解析、数据检索、解析转换、质量校验与整合打包流程，前端四个页面均能正常展示结果。

系统共解析出 3 条数据需求：

1. `req_000`：robot_urdf，数据源 robotiq，检索成功。
2. `req_001`：mesh，数据源 ycb，检索失败，原因为检索超时。
3. `req_002`：grasp，数据源 graspnet，检索阶段显示成功，但解析转换后未获得真实 npz 抓取数据，最终作为缺失项记录。

最终生成数据包：

`package-20260814-150603`

数据包中实际落盘 1 个文件：

`robots/req_000.urdf`

manifest 中显示 `status = failed`，缺失 2 项必需需求，因此本 case 最终判定为：

`FAIL`

失败分类：

`P2_RETRIEVE`

## 3. 失败原因说明

本 case 失败主要不是前端问题，而是数据检索与真实数据获取问题。

具体原因如下：

1. `req_001` 的 YCB apple mesh 检索超时，超过 `per_req_timeout` 秒，系统跳过该需求以避免阻塞后续流程。
2. `req_002` 的 grasp 数据未获得真实 npz 文件，GraspNet 返回的是元数据或参考入口，未形成可用抓取数据文件。
3. 数据包只满足 1/3 个需求，且缺失项均为 required，因此不能判定为 PASS 或 PASS_WITH_FALLBACK。

## 4. 前端稳定性观察

本次执行过程中，前端流程展示基本正常，未发现明显 `P6_FRONTEND` 问题。

已正常展示：

1. 目标输入页：可以输入目标并选择真实流程。
2. 进度展示页：可以展示阶段进度、数据需求状态、provenance 和 state_summary。
3. 数据包审查页：可以展示数据包目录和 manifest。
4. 校验与缺失项页：可以展示 validation_issues 和 missing_items。
5. human_review：审查决定为 satisfied 后流程可继续完成。

未观察到以下前端异常：

1. 页面卡死。
2. 按钮无响应。
3. interrupt 卡死。
4. resume 失败。
5. 后端失败但前端无错误展示。
6. 数据包生成但前端不展示。

因此本次不标记 `P6_FRONTEND`。

## 5. 截图与记录文件

本 case 的测试记录应放置在：

`records/ms_004/record.json`

截图应放置在：

`records/ms_004/screenshots/`

截图文件包括：

1. `image.png`：目标输入页。
2. `prove.png`：进度展示页。
3. `data.png`：数据包审查页。
4. `validation.png`：校验与缺失项页。

本次虽然判定为 FAIL，但错误已在 validation_issues 和 missing_items 中清晰展示，如无单独错误弹窗，可不额外提交 `05_error.png`。

## 6. 操作手册修订情况

本次按照现有前端操作手册执行 `ms_004`，整体流程与手册描述基本一致。

当前暂未发现必须修改的页面步骤差异，因此本日未单独提交 `frontend_manual_v2.md`。

如后续执行 `ms_007` 或其他 case 时发现以下问题，再补充修订操作手册第二版：

1. 页面按钮名称与手册不一致。
2. human_review 操作流程变化。
3. 截图位置或字段展示变化。
4. 数据包审查页字段变化。
5. 校验与缺失项展示逻辑变化。

## 7. 今日结论

E 端今日已完成至少 1 条多源端到端 case 的真实流程测试记录。

`ms_004` 的主要失败原因是数据检索超时和真实抓取数据缺失，属于 `P2_RETRIEVE`，不是前端流程异常。前端可以稳定承接失败结果，并展示阶段进度、manifest、validation_issues 和 missing_items。