# Day3 E 工程师执行说明

## 1. 基本信息

日期：2026-08-14  
角色：E 产品工程师  
执行任务：多源端到端 case 交叉测试与前端流程稳定性观察  
执行 case：ms_004、ms_007  
运行模式：真实流程  
审查决定：satisfied  

## 2. 今日执行概览

今日 E 端完成 2 条多源端到端 case 的真实流程测试：

1. `ms_004`：UR5 with Robotiq 2F-85 grasps YCB apple
2. `ms_007`：抓取 YCB 香蕉（未指定仿真器）

两条 case 均能正常完成前端流程展示，包括：

1. 目标输入。
2. 进度展示。
3. 数据包审查。
4. 校验与缺失项。
5. human_review 审查流程。

两条 case 最终均判定为 `FAIL`，主要原因集中在数据检索与真实抓取数据缺失，不属于前端流程异常。

## 3. ms_004 执行结果

输入目标：

`UR5 with Robotiq 2F-85 grasps YCB apple`

系统解析出 3 条数据需求：

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

失败原因：

1. `req_001` 的 YCB apple mesh 检索超时，超过 `per_req_timeout` 秒。
2. `req_002` 的 grasp 数据未获得真实 npz 文件。
3. 数据包只满足 1/3 个需求，且缺失项均为 required。

## 4. ms_007 执行结果

输入目标：

`抓取 YCB 香蕉（未指定仿真器）`

系统解析出 2 条数据需求：

1. `req_000`：mesh，YCB banana 的 3D 网格模型。
2. `req_001`：grasp，YCB banana 的抓取姿态数据。

本 case 未指定仿真器，系统未强制生成 `sim_config`，符合题目预期。

最终生成数据包：

`package-20260814-170029`

数据包中实际落盘 1 个文件：

`objects/req_000.stl`

manifest 中显示 `status = failed`，缺失 1 项必需需求，因此本 case 最终判定为：

`FAIL`

失败分类：

`P2_RETRIEVE`

失败原因：

1. 系统成功获取 YCB banana mesh 文件。
2. `req_001` 的 grasp 数据未获得真实 npz 文件。
3. GraspNet 返回元数据 JSON 或参考入口，未形成可用抓取数据文件。
4. 数据包只满足 1/2 个需求，仍缺失 required 的 grasp 数据。

## 5. 前端稳定性观察

本次执行 `ms_004` 和 `ms_007` 过程中，前端流程展示基本正常，未发现明显 `P6_FRONTEND` 问题。

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
7. 阶段进度完成但结果完全空白。

因此今日不标记 `P6_FRONTEND`。

## 6. 截图与记录文件

`ms_004` 的测试记录应放置在：

`records/ms_004/record.json`

截图应放置在：

`records/ms_004/screenshots/`

`ms_007` 的测试记录应放置在：

`records/ms_007/record.json`

截图应放置在：

`records/ms_007/screenshots/`

每个 case 建议包含以下截图：

1. `01_input.png`：目标输入页。
2. `02_progress.png`：进度展示页。
3. `03_package.png`：数据包审查页。
4. `04_validation.png`：校验与缺失项页。

如果未出现单独错误弹窗，可不额外提交 `05_error.png`；错误信息已经体现在 validation_issues 和 missing_items 中。

## 7. 操作手册修订情况

本次按照现有前端操作手册执行 `ms_004` 和 `ms_007`，整体流程与手册描述基本一致。

当前暂未发现必须修改的页面步骤差异，因此本日未单独提交 `frontend_manual_v2.md`。

如后续 case 中发现以下问题，再补充修订操作手册第二版：

1. 页面按钮名称与手册不一致。
2. human_review 操作流程变化。
3. 截图位置或字段展示变化。
4. 数据包审查页字段变化。
5. 校验与缺失项展示逻辑变化。

## 8. 今日结论

E 端今日完成 2 条多源端到端 case 的真实流程测试记录。

`ms_004` 和 `ms_007` 的主要失败原因均集中在数据检索超时或真实抓取数据缺失，归类为 `P2_RETRIEVE`。前端能够稳定承接失败结果，并展示阶段进度、manifest、validation_issues 和 missing_items，今日未发现 `P6_FRONTEND`。