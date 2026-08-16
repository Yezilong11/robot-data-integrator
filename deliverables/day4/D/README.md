# Day 4：D（机器人工程师）交付物

> 分支：`feat/arch-langgraph`
> 执行日期：2026-08-16
> 依据：`Day4_执行收尾.md`（D 任务）+ `问题集构建策略.md`（record 模板/截图规范/判定 P1-P8）
> 问题集：`problem_set/problem_set.json`
> 交付目录：`deliverables/day4/D/`

## 执行范围（Day4-D）

| # | 任务                                      | 完成情况                       |
| - | --------------------------------------- | -------------------------- |
| 1 | 完成格式/仿真类全部单源题（ss\_franka\_001/002/003）  | ✅ 3 题全部执行并留档               |
| 2 | 多源交叉完成（ms\_003，Kinova Gen3 + Isaac Sim） | ✅ 执行并留档（FAIL/P2\_RETRIEVE） |
| 3 | 汇总可加载性验证结论（哪些 URDF/Mesh/MJCF 验证不过）      | ✅ 见「可加载性验证结论」              |

全部 4 题均走真实流程：`run_graph`（前端「运行」→ interrupt human\_review → 「继续运行」resume 打包），所有截图均为**实际运行环境下的真实界面截图**（滚动分块 + PIL 拼接，完整页面无截断）。FAIL 用例（ms\_003）按 day3 标准已截含报错信息的界面。

## 目录结构

```
deliverables/day4/D/
├── README.md                        # 本索引
├── ss_franka_001/                   # Franka Panda URDF 单源题（直接）
│   └── record.json + screenshots/{intermediate,final}/01~04.png
├── ss_franka_002/                   # Franka Panda 完整 URDF（碰撞+视觉网格）
│   └── record.json + screenshots/{intermediate,final}/01~04.png
├── ss_franka_003/                   # Franka Panda 模型（口语化）
│   └── record.json + screenshots/{intermediate,final}/01~04.png
└── ms_003/                          # 多源交叉题（Kinova Gen3 + EGAD mug + Isaac Sim）
    └── record.json + screenshots/{intermediate,final}/01~04.png
```

> 截图命名：01 目标输入 / 02 进度展示 / 03 校验与缺失项 / 04 数据包审查（中间态 + 最终态各一套，完整页面）。

## 执行结果总览

| case\_id        | input                                      | 解析需求                                              | 命中源                                       | runtime\_check                                                       | 落盘文件                        | verdict                  |
| --------------- | ------------------------------------------ | ------------------------------------------------- | ----------------------------------------- | -------------------------------------------------------------------- | --------------------------- | ------------------------ |
| ss\_franka\_001 | 获取 Franka Panda 机器人的 URDF 模型               | \[robot\_urdf] match                              | franka（pybullet\_robots/jsdelivr）         | **LOAD\_OK**（13 links/12 joints，mesh 11 处引用全解析）                      | 19（URDF + 18 OBJ）           | **PASS**                 |
| ss\_franka\_002 | 完整 URDF，包含碰撞网格与视觉网格                        | \[robot\_urdf] match                              | franka（deoxys\_control，is\_fallback=true） | LOAD\_OK\_PARTIAL（URDF 结构可解析，`package://meshes/...` 11 处无法解析）        | 1（仅 URDF，网格未打包）             | **PASS\_WITH\_FALLBACK** |
| ss\_franka\_003 | 抓取仿真，先把模型文件给我                              | \[robot\_urdf] match                              | franka（deoxys\_control，is\_fallback=true） | LOAD\_OK\_PARTIAL（同上）                                                | 1（仅 URDF）                   | **PASS\_WITH\_FALLBACK** |
| ms\_003         | Kinova Gen3 picks up EGAD mug in Isaac Sim | \[robot\_urdf, mesh, sim\_config] partial（+grasp） | fuel(gazebo)+huggingface+github           | **MJCF\_PARSE\_FAIL**（req\_003.xml 实为 python；runtime\_check skipped） | 3（stl+json 空壳+xml 错配）+ 缺失 1 | **FAIL/P2\_RETRIEVE**    |

## 关键结论与发现

### 1. Franka 系列（ss\_franka\_001/002/003）——同一源头，两种交付质量

- **PASS（001）**：franka 适配器命中 `pybullet_robots/panda.urdf`（jsdelivr 直达），随包抓齐 18 个 OBJ 网格（visual/collision 各 9），URDF 以**相对路径** `meshes/...` 引用网格——yourdfpy 全量解析成功（13 links/12 joints），trimesh 18/18 可加载。**URDF+网格全链路可用**，是本批次唯一完整命中的 FRANKA 题。
- **PASS\_WITH\_FALLBACK（002/003）**：两条目标均降级命中 `deoxys_control/panda.urdf`（`is_fallback=true` 显式可追溯），仅落盘 1 个 URDF 文件，**网格资产未随包交付**。该 URDF 以 `package://meshes/...` 引用网格，包内无对应文件 → yourdfpy 报 11 处 `Unable to resolve filename`。运动学结构（13 links/12 joints）可用，但 002 明确要求「碰撞网格与视觉网格」——**核心交付内容缺失**，属实质性降级。
- 结论：franka 源的两种分支（jsdelivr 直达 vs GitHub raw 降级）决定了网格是否随包抓取。**fallback 路径缺「网格资产跟随抓取」逻辑**，是 002/003 的共性根因。

### 2. ms\_003 多源交叉——Kinova 无源 + sim\_config 格式错配双失败

- 题目：Kinova Gen3 在 Isaac Sim 中抓取 EGAD mug（期望 robot\_urdf + mesh + sim\_config）。
- **P2\_RETRIEVE（req\_000）**：registry 无 kinova 专用 adapter；通用 GitHubAdapter 返回 markdown 网页产物被 C4 格式预检拦截；franka/robotiq 均报「有源但未收录 Kinova Gen3」→ **核心机器人资产缺失**，整体判定 FAIL。
- mesh（req\_001）经 fuel.gazebosim.org 真实命中 EGAD mug（ACE\_Coffee\_Mug\_Kristen\_16\_oz\_cup），confidence=1.0，落盘 `objects/req_001.stl`——**唯一高质量产出**。
- sim\_config（req\_003）降级命中 IsaacLab `robots/franka.py`（Python 资产定义文件），却**标记 format=mjcf 落盘为 .xml** → mujoco 解析失败（`XML_ERROR_PARSING_TEXT`）；且场景内资源引用 `objects/ACE_Coffee_Mug_Kristen_16_oz_cup.stl` 与落盘 `objects/req_001.stl` **名字不匹配**，runtime\_check 因此 skipped。
- grasp（req\_002，LLM 额外解析）GraspNet URL 未实际下载，0 字节空壳。
- 结论：多源题在「无专用源的机器人 URDF」链路上与单源题共享同一检索瓶颈（见 Day3 根因）；**sim\_config 降级路径无格式校验（python→mjcf 错配）+ 资源名引用不校验** 是本 case 的第二重失败点。

## 可加载性验证结论（任务 3）

> 工具：URDF→`yourdfpy.URDF.load`，Mesh→`trimesh.load`，MJCF→`mujoco.MjModel.from_xml_path`。逐包实测，非仅读 manifest。

| 数据包                     | case            | URDF（yourdfpy）                                                  | Mesh（trimesh）                      | MJCF（mujoco）                                                                                            | 结论                   |
| ----------------------- | --------------- | --------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------- |
| package-20260816-133544 | ss\_franka\_001 | ✅ LOAD\_OK links=13 joints=12，11 处 mesh 引用全部随相对路径解析             | ✅ 18/18 OBJ 全部可加载                  | —（无）                                                                                                    | **全量可加载**            |
| package-20260816-134307 | ss\_franka\_002 | ⚠️ 结构解析 OK（13/12），但 11 处 `package://meshes/...` **无法解析**（包内无网格） | ❌ 网格未打包（0 文件）                      | —                                                                                                       | **仅运动学可用，视觉/碰撞几何缺失** |
| package-20260816-134838 | ss\_franka\_003 | ⚠️ 同上（13/12，11 处引用无法解析）                                         | ❌ 网格未打包（0 文件）                      | —                                                                                                       | **仅运动学可用，仿真模型不完整**   |
| package-20260816-132237 | ms\_003         | ❌ req\_000 robot\_urdf 缺失（P2\_RETRIEVE）                         | ✅ objects/req\_001.stl trimesh 可加载 | ❌ sim\_config/req\_003.xml **XML\_ERROR\_PARSING\_TEXT**（实为 python 脚本）；runtime\_check skipped（资源引用名不匹配） | **场景不可构建**           |

**验证不过项汇总**：

1. **URDF 网格引用不可解析 ×2**（ss\_franka\_002/003）：URDF 用 `package://` URI 引用网格，包内未落盘网格 → yourdfpy 无法解析。根因：fallback 检索路径不抓取 mesh 资产。
2. **MJCF 内容非 XML ×1**（ms\_003）：python 源码被当 mjcf 落盘 → mujoco 解析失败。根因：sim\_config 降级缺格式校验。
3. **场景资源引用名不匹配 ×1**（ms\_003）：场景引用 `ACE_Coffee_Mug_Kristen_16_oz_cup.stl`，落盘 `req_001.stl` → runtime\_check skipped。根因：assemble 重命名后未回写场景引用。
4. **机器人资产缺失 ×1**（ms\_003）：Kinova Gen3 无专用源 + 通用源 markdown 拦截 → req\_000 缺失。

## 根因归纳（Day4-D 视角）

| 失败码/降级               | 出现次数                   | 根因                                                                                          |
| -------------------- | ---------------------- | ------------------------------------------------------------------------------------------- |
| P2\_RETRIEVE         | 1（ms\_003 req\_000）    | 问题集要求（Kinova Gen3）超出 adapter 覆盖范围：registry 无 kinova/isaac 专用源，通用 GitHub 返回 markdown → C4 拦截 |
| PASS\_WITH\_FALLBACK | 2（ss\_franka\_002/003） | franka fallback 路径只落 URDF 文本，不跟随抓取 `package://meshes/...` 引用的网格资产 → 网格交付缺失                  |
| sim\_config 降级错配     | 1（ms\_003 req\_003）    | 降级命中 python 资产文件仍标 format=mjcf，无格式校验；资源引用名与落盘文件名不一致                                         |

系统性结论：**franka 源 primary 路径（jsdelivr）可完整交付 URDF+网格，fallback 路径缺网格跟随抓取** 是单源题降级主因；**ms\_003 为「无专用源 + 格式错配」的复合失败**，核心是平台 adapter 覆盖面不足（Kinova/Isaac 未收录），非代码 bug。
