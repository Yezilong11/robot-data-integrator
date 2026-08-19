# Day 2：D（机器人工程师）交付物

> 分支：`feat/arch-langgraph`
> 执行日期：2026-08-14
> 依据：`Day2_单源执行启动.md`（D 任务）+ `问题集构建策略.md`（record 模板/截图规范/判定 P1-P8）+ `deliverables/day1/D/数据包可加载性验证.md`
> 问题集：`problem_set/problem_set.json`（63 题；D 负责格式/仿真类：robot\_urdf / mesh / sim\_config）

## 执行范围（Day2 第一批）

D 任务 1：执行格式/仿真类单源题第一批——**ycb mesh / mujoco sim\_config 各 1 题**，走真实流程（`run_graph` 中断于 human\_review → `resume_workflow("satisfied")` 完成打包，与前端完全一致）。

## 目录结构

```
deliverables/day2/D/
├── README.md                        # 本索引
├── observations_d_20260814.json     # 每题记录汇总（解析/命中源/quality/可加载性/错误类型）
├── run_day2_d_cases.py              # 执行驱动脚本（真实流程 + 可加载性验证 + 观测落盘）
├── make_screenshots.py              # 截图生成脚本（观察数据 → 文本截图 PNG）
├── verify_packages.py               # 数据包目录结构 vs manifest 一致性核验脚本
├── run_log*.txt                     # 各次运行日志（含 mujoco 首次超时与 180s 重跑）
├── ss_ycb_001/
│   ├── record.json
│   ├── observe.json                 # 完整执行观测（中间态+最终态+可加载性）
│   └── screenshots/{intermediate,final}/01~04.png
└── ss_mujoco_001/
    ├── record.json
    ├── observe.json
    └── screenshots/{intermediate,final}/01~04.png
```

> 截图命名：01 目标输入 / 02 进度展示 / 03 校验与缺失项 / 04 数据包审查（中间态 + 最终态各一套）。

## 执行结果

| case\_id        | input                                             | 解析结果                                   | 命中源             | quality                          | 可加载性                     | 目录一致 | verdict |
| --------------- | ------------------------------------------------- | -------------------------------------- | --------------- | -------------------------------- | ------------------------ | ---- | ------- |
| ss\_ycb\_001    | 获取 YCB 数据集中的香蕉（banana）mesh 模型                     | \[mesh] ✓                              | ycb             | unknown\*                        | Mesh passed（16384 faces） | ✓    | PASS    |
| ss\_mujoco\_001 | 获取 mujoco\_menagerie 中 Franka Panda 的 MuJoCo 场景配置 | \[robot\_urdf, sim\_config] ⚠（多出 urdf） | franka + mujoco | real（sim\_config）/ unknown（urdf） | URDF/Mesh/MJCF 全 passed  | ✓    | PASS    |

\* `data_source_quality=unknown` 为 YCB adapter 未标注真实度，实际为 YCB 真实 mesh（expected 允许 real/fallback），已在记录中注明。

## 关键结论与发现

1. **ss\_ycb\_001**：mesh 单需求，LLM 解析 match；ycb 源命中 `011_banana/google_16k/textured.obj`（1.43MB），转 STL 落包 `objects/req_000.stl`，trimesh 加载 16384 faces 通过。
2. **ss\_mujoco\_001**：LLM 解析出双需求（robot\_urdf + sim\_config，mismatch 但可接受）。sim\_config 由 mujoco 源命中 mujoco\_menagerie `scene.xml`（quality=real，panda.xml+68 资产）；robot\_urdf 由 franka 源补足 pybullet\_robots `panda.urdf`。三类可加载性验证全部通过：URDF yourdfpy（12 joints/13 links）、Mesh trimesh、MJCF `mujoco.mj_step`（nq=9/nu=8 一步仿真成功）。
3. **首次 60s 超时（如实记录）**：mujoco fetch 需串行下载 68 个 mesh 资产（\~42s），与 franka 并行检索双需求超出默认 `per_req_timeout=60s`，首次运行 FAIL；分类 P2\_RETRIEVE（网络/超时预算类，非 P4/P5 格式问题）。`PER_REQ_TIMEOUT=180s` 重跑成功 PASS。
4. **目录结构核验**：`verify_packages.py` 确认两包 manifest.files 与磁盘数据文件完全一致（仅差 checksums/manifest/provenance/units 4 个包级元数据文件，属系统设计）。
5. **修复前端真实 bug**：`src/rdi/frontend/app.py` 的 `to_plain` 对二进制 bytes（URDF/STL 资产）在 pydantic `mode="json"` 下抛 `UnicodeDecodeError`，导致 resume 路径崩溃；已加 `mode="python"` + bytes 占位 fallback。

## 最终结果：2026-08-16 前端真实流程重测（2/2 全部通过）

> 本节为**最终权威结果**。2026-08-16 对 day2/D 全部 2 题走真实前端（`src/rdi/frontend/app.py`，端口 7860）：radio「真实流程」→「运行」→ human_review 中断 →「数据包审查」选 satisfied →「继续运行」→「运行完成」；各 case 的 `record.json / observe.json / screenshots/` 均已按最新结果**覆盖写回**。截图由浏览器真实界面滚动分块拼接为完整页面（8/8，中间态 + 最终态各 4 张），替换了最初 `make_screenshots.py` 生成的文本合成截图。

| case_id | verdict | package_id | 落盘文件 | 可加载性 | 截图 |
|---|---|---|---|---|---|
| ss_mujoco_001 | **PASS** | package-20260816-232408 | 69 | URDF/Mesh/MJCF 全 passed（mj_step 一步仿真成功） | 8/8 |
| ss_ycb_001 | **PASS** | package-20260816-233447 | 1 | Mesh passed（16384 faces） | 8/8 |

两题首轮即 PASS，无失败需修复；本次重测目的为统一为真实前端流程 + 完整页面真实截图留档。

<br />
