# Day 1：问题集定稿与环境准备

## 当日目标

问题集 `problem_set/problem_set.json` 定稿评审通过；全员本机环境就绪，具备开测条件。

## 各角色详细工作

### A（组长/架构师）

1. 召集问题集评审会，逐题过 `problem_set.json`，确认每题的 `target`、`expected`（req_types/quality/format/min_files）无歧义。
2. 定验收线：P0 题至少 6/8 生成可用数据包；记录完整率 ≥ 90%；Day 6 交付两个文件夹（Day6-8 已压缩合并为一日，见 `docs/problem_set/Day6_汇总统计.md`）。
3. 定判定口径：PASS / PASS_WITH_FALLBACK / FAIL 边界 + 失败分类码（P1_PARSE~P8_OTHER）用法。
4. 裁定争议题目（是否保留、期望输出是否调整），签收问题集 v1.0。
5. 确认各角色环境就绪情况，宣布 Day 2 开测。

### C（数据工程师）

1. 提交数据源类题目草案（paper/code/dataset/grasp/sim_config/policy/sensor）给 A 评审。
2. 环境准备：`.env` 填 `GITHUB_TOKEN`、`IEEE_API_KEY`（有则填）、确认 `HF_ENDPOINT` 镜像。
3. 验证探活脚本可运行：`uv run python scripts/_probe_adapters.py` 至少能出结果。
4. 与 A 对齐数据源类题目的期望 `quality`/`format` 判定标准。

### D（机器人工程师）

1. 提交格式/仿真类题目草案（robot_urdf/mesh/sim_config）给 A 评审。
2. 环境准备：`uv sync --extra runtime`，验证 `yourdfpy`/`trimesh`/`mujoco` 三个库可用。
3. 用现有数据包跑通一次可加载性验证脚本（URDF/Mesh/MJCF 三类的加载代码）。
4. 与 A 对齐格式类题目的可加载性验收标准。

### E（产品工程师）

1. 编写前端操作手册第一版：真实流程操作步骤（模式选择 → 输入目标 → 观察阶段 → human_review 中断 → 提交决策 resume）。
2. 确认前端可启动：`uv run python -m rdi.frontend.app` 正常打开 http://127.0.0.1:7860。
3. 整理执行环境排查清单（LLM Key 缺失/依赖缺失/端口占用等常见问题）。
4. 与 A 对齐流程类题目的执行与截图规范。

### F（质量工程师）

1. 维护问题集 JSON：将评审通过的题目入库 `problem_set/problem_set.json`，校验 JSON 格式合法、case_id 唯一。
2. 建立记录模板：`records/<case_id>/record.json` 模板 + `screenshots/` 目录规范。
3. 建立执行进度表（case × 执行人 × 状态：未执行/已执行/已判定/已复核）。
4. 与 A 确认进度表字段与统计口径。

## 与 A 的对接点

| 对接人 | 对接内容 | 期望输出 |
|---|---|---|
| C | 提交数据源类题目草案 | A 评审通过并入 JSON |
| D | 提交格式/仿真类题目草案 | A 评审通过并入 JSON |
| E | 提交操作手册与执行环境清单 | A 确认可执行 |
| F | 提交问题集 JSON 与进度表 | A 确认签收 v1.0 |

## 当日出口标准

- [ ] 问题集 JSON 定稿（A 签收）
- [ ] 五人人均能启动前端/跑探活
- [ ] 记录模板与进度表就绪
