# Day 2：单源执行启动

## 当日目标

单源测试正式开跑：C/D/E 按专长认领并完成第一批单源题（约 1/3），每题产出 `record.json` + 截图；A 首测多源题。

## 各角色详细工作

### A（组长/架构师）

1. 认领多源题 `ms_001`（Franka Panda grasps YCB banana in MuJoCo）、`ms_002`（中文版）执行，填写 record.json + 截图。
2. 抽查 C/D/E 当天已提交的 2-3 条记录，确认判定口径执行一致。
3. 对 C/D/E 提交的存疑 case 做判定裁定。

### C（数据工程师）

1. 执行数据源类单源题第一批：arxiv / github / huggingface 各 1 题（如 `ss_arxiv_001`），走真实流程。
2. 每题记录：解析结果、命中源、`data_source_quality`、错误类型（timeout/rate_limit/not_found/auth）。
3. 填写 record.json 的 `input` 字段为实际输入原文，截图至少 2 张（阶段界面 + 结果页）。
4. 判定为 FAIL 的题，标注失败分类码（P2_RETRIEVE/P3_SOURCE 优先）。

### D（机器人工程师）

1. 执行格式/仿真类单源题第一批：ycb mesh / mujoco sim_config 各 1 题。
2. 数据包生成后做可加载性验证：URDF 用 `yourdfpy`（`load_meshes=True`）、Mesh 用 `trimesh`、MJCF 用 `mujoco.mj_step`。
3. 核验数据包目录结构（robots/objects/grasps/sim_config/）与 manifest 记录一致。
4. FAIL 标注分类码（P4_FORMAT/P5_RUNTIME 优先）。

### E（产品工程师）

1. 执行流程类单源题第一批（如 `ss_mujoco_001` 单源仿真场景）。
2. 按操作手册走真实流程，验证手册步骤无误，发现出入当天修订手册。
3. 落实截图规范：阶段截图 + 结果截图，文件名 `NN_<stage>.png`。
4. 记录流程异常（interrupt 卡死/resume 失败），标 P6_FRONTEND。

### F（质量工程师）

1. 校验当日全部记录：JSON 格式合法、字段完整、判定与分类码填写一致。
2. 更新执行进度表并晚间同步全员。
3. 汇总当日判定统计（PASS/PASS_WITH_FALLBACK/FAIL 数）上报 A。

## 与 A 的对接点

| 对接人 | 对接内容 | 期望输出 |
|---|---|---|
| C/D/E | 提交存疑 case 请求裁定 | A 给出判定结论 |
| C/D/E | 提交当日记录 | F 校验 + 进度表更新 |
| F | 晚间汇报当日统计 | A 确认执行进度正常 |

## 当日出口标准

- [ ] 每人至少完成 1 条单源题记录并入库
- [ ] 判定口径无分歧（有分歧当天裁定）
- [ ] F 进度表当晚同步
