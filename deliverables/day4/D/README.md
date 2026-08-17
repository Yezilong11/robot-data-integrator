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

系统性结论：**franka 源 primary 路径（jsdelivr）可完整交付 URDF+网格，fallback 路径缺网格跟随抓取** 是单源题降级主因；**ms_003 为「无专用源 + 格式错配」的复合失败**，核心是平台 adapter 覆盖面不足（Kinova/Isaac 未收录），非代码 bug。

---

# Day4 失败用例修复与重测记录（2026-08-16）

> 依据用户指令：根据 day4 测试结果系统分析失败用例 → 给出解决方案并实施修复 → 同步 5 项交付（原因分析 / 解决方案 / 代码改动 / 重测验证 / 系统状态）。
> 重测仅更新本 README，**不修改**各 case 已有文件夹（含截图/record），重测过程不重新截图。

## 一、问题原因分析报告

### 失败用例清单与现象

| 用例 ID | 首轮判定 | 失败现象描述 |
| ------- | ------- | ---------- |
| ss\_franka\_002 | PASS\_WITH\_FALLBACK | 仅落盘 1 个 URDF（deoxys\_control/panda.urdf），**碰撞/视觉网格 18 个 OBJ 未随包交付**；URDF 以 `package://meshes/...` 引用网格，yourdfpy 报 **11 处 Unable to resolve filename** |
| ss\_franka\_003 | PASS\_WITH\_FALLBACK | 同上（同一条 franka fallback 检索路径，网格同样未打包） |
| ms\_003 | **FAIL/P2\_RETRIEVE** | 4 需求：req\_000 robot\_urdf **缺失**；req\_003 sim\_config 落盘 `.xml` 实为 python 源码 → mujoco `XML\_ERROR\_PARSING\_TEXT`；场景资源引用名与落盘名不匹配 → runtime\_check skipped；req\_002 grasp 0 字节空壳。包仅 3 文件 + 缺失 1 |

### 根本原因定位

| 用例 | 根因 | 证据 |
| ---- | ---- | ---- |
| ss\_franka\_002/003 | **GitHubAdapter.fetch 未调用 `_download_xml_with_assets`**：ROBOT\_URDF 命中通用 GitHub 源（franka fallback 分支）时只落 URDF 文本，不跟随抓取 `<mesh filename>` 引用的网格资产；`_find_urdf_file` 固定 `main` 分支，而部分仓库（ros\_kortex）默认分支为 `noetic-devel`，导致回退到 markdown | record.json 包内 0 网格文件；`package://meshes/...` 11 处不可解析 |
| ms\_003 req\_000 | **Kinova Gen3 无专用 adapter**：registry 的 ROBOT\_URDF 候选（franka/allegro/robotiq/github）对「Kinova Gen3」均报「有源但未收录」；通用 GitHub 返回 markdown 被 C4 预检拦截 → 核心机器人资产缺失 | 首次 ms\_003 的 missing reason：franka/robotiq CatalogError + github markdown |
| ms\_003 req\_000（复测阶段） | **新增 KinovaAdapter 后仍两次失败**：① `_download_assets` 用 URDF 文件 URL 而非仓库根做资产下载基准 + `package://` 剥离过度（连包名 `kortex_description` 一并删除）→ 资产全 404（asset\_count=0）；② Allegro 泛词子串误命中（query "URDF" 命中描述 "Allegro 右手 URDF 模型"）→ 返回 Allegro 手爪（11 资产）而非 Kinova；③ kinova 直连 raw.githubusercontent 下载 7 资产实测 **28.2s**，超过 60/5=12s 单源预算 → 下载中途 `asyncio.timeout` 被跳过 | `_rerun_day4.log` 四轮 ms\_003：kinova asset\_count=0 → allegro 11 → missing(52.6s) |
| ms\_003 req\_003 | **sim\_config 降级缺格式校验 + 资源名不匹配**：Isaac 源命中 python 资产文件仍标 format=mjcf 落盘 `.xml`；场景引用 `ACE\_Coffee\_Mug...stl` 与落盘 `req\_001.stl` 不一致 | runtime\_check XML\_ERROR；manifest 3 文件错配 |

## 二、解决方案及实施步骤

| 步骤 | 修复项 | 实施内容 |
| ---- | ------ | ------- |
| 1（f2） | GitHub 通用源网格跟随 + 分支回退 | `github.py`：`fetch` 对 ROBOT\_URDF 调用 `_download_xml_with_assets`（URDF 中 mesh/texture/include 引用资产一并下载，失败单资产跳过）；`re.sub(rb"package://", ...)` 剥离前缀使资产键与 URDF 引用自洽；`_find_urdf_file` 返回 (路径, 分支)，分支回退 `main → master → default_branch`，杜绝因分支名不符回退 markdown |
| 2（f3） | sim\_config 格式 + 资源名一致性 | `assemble.py`：`_ext_for_raw_format` 增加 `python/py → .py`；`parse_convert.py`：`_build_sim_config_context` 显式构造 `objects/{req_id}.stl` 并传递 `mesh_bytes`，第二遍 SIM\_CONFIG 处理前注入 assets（`model_copy(update={"assets": ...})`） |
| 3（f4） | 新增 KinovaAdapter | 新建 `src/rdi/adapters/kinova.py`：search 按已知型号（gen3/gen3\_lite）token 匹配、未收录抛 CatalogError；fetch 直连 `Kinovarobotics/ros_kortex@noetic-devel` 纯 URDF（无 xacro）+ 并发抓 7 个 STL 资产。注册进 `DataSource` 枚举、`settings.kinova_base_url`、`registry`（ROBOT\_URDF 候选列表） |
| 4（f4） | Kinova 资产 URL 修复 | 资产下载基准改为仓库根 `self.base_url`；`package://` 仅剥离前缀、**保留包名** `kortex_description/...`（仓库根相对路径），保证下载 URL 与落盘 `robots/{ref}` 自洽 |
| 5（f4） | Allegro/Franka 泛词误命中收紧 | `allegro.py`/`franka.py` `_search_fallback`：归一化子串与词元交集只认 **id/title**（标识性 token），描述词元交集需 **≥2 个**；"URDF"/"机器人" 等泛词不再触发 |
| 6（f5） | 检索超时预算扩容 | `settings.py`：`per_req_timeout` 60→180s（单源预算 12s→36s，容纳 kinova 28s 下载）。jsdelivr 镜像替代不可行（half\_arm\_1/2\_link.STL 404），故保留 raw 直连 + 加预算 |

## 三、代码改动记录

> 基线：`ec0f016`（D day4）。以下为**未提交工作区改动**（2026-08-16），建议提交信息：`D day4修复：Kinova adapter + 网格跟随抓取 + sim_config格式/资源名一致性 + 检索预算扩容`。

| 文件 | 修改内容 |
| ---- | ------- |
| `src/rdi/adapters/github.py` | fetch 对 ROBOT\_URDF 调用 `_download_xml_with_assets` 并剥离 `package://`；RawData 携带 assets、url 用 raw.githubusercontent；`_find_urdf_file` 分支回退 main→master→default；新增 `_urdf_in_branch` |
| `src/rdi/graph/nodes/assemble.py` | `_ext_for_raw_format` 增加 python/py→`.py` |
| `src/rdi/graph/nodes/parse_convert.py` | SIM\_CONFIG 上下文 MESH 项显式构造 `objects/{req_id}.stl` + `mesh_bytes` 注入 |
| `src/rdi/adapters/kinova.py` | **新增**：KinovaAdapter（search/fetch/资产并发下载） |
| `src/rdi/adapters/__init__.py` | 注册 `DataSource.KINOVA: KinovaAdapter` |
| `src/rdi/models/common.py` | `DataSource` 增加 `KINOVA = "kinova"` |
| `src/rdi/adapters/registry.py` | ROBOT\_URDF 候选插入 `"KinovaAdapter"`；source\_name\_map/select\_adapter 同步 |
| `src/rdi/config/settings.py` | 新增 `kinova_base_url`；`per_req_timeout` 60→180（docstring 记录原因） |
| `src/rdi/adapters/allegro.py` | `_search_fallback` 子串/词元匹配收紧（去 description 泛词旁路） |
| `src/rdi/adapters/franka.py` | `_search_fallback` 同规则收紧（"机器人" 不再命中） |
| `tests/unit/adapters/test_kinova.py` | **新增** 4 项：source / search 命中 / 未收录抛错 / fetch 资产收集与前缀保留 |
| `tests/unit/adapters/test_allegro.py` | 新增回归：`kinova query 不命中`、`URDF 泛词不命中` |
| `tests/unit/adapters/test_franka.py` | 新增回归：`机器人/URDF 泛词不命中` |
| `tests/unit/adapters/test_github.py` | 新增：资产收集+package 剥离、分支回退到 default |
| `tests/unit/graph/test_assemble.py` | 新增：python raw config 用 `.py` 扩展名 |
| `tests/unit/graph/test_parse_convert.py` | 断言更新为 `objects/r_mesh.stl`（新一致性行为） |

## 四、修复后的测试验证结果

### 真实流水线重测（`data/_rerun_day4.py`，走 run\_graph + human\_review resume 完整链路）

| 用例 | 命中源 | format | 资产 | 包文件 | missing | runtime\_check | 判定 |
| ---- | ---- | ---- | ---- | ---- | ---- | ---- | ---- |
| ss\_franka\_002 | github（is\_fallback=true） | urdf | **18** | **19** | 0 | LOAD\_OK（11 处 mesh 引用全解析） | **PASS**（原 PASS\_WITH\_FALLBACK） |
| ss\_franka\_003 | franka | urdf | **18** | **19** | 0 | LOAD\_OK | **PASS**（原 PASS\_WITH\_FALLBACK） |
| ms\_003 | kinova + google\_scanned + graspnet + isaac | urdf/obj/json/python | 7（kinova） | **12** | **0** | req\_003 **passed**（MuJoCo 加载+一步仿真成功） | **PASS**（原 FAIL/P2\_RETRIEVE） |

ms\_003 重测明细：req\_000 ← **kinova**（elapsed 83.8s，URDF + 7 个 STL 资产全部落盘 `robots/kortex_description/...`）；req\_001 ← google\_scanned（EGAD mug obj，100%/1.0）；req\_002 ← graspnet（json，fallback 60%/0.6，**残余空壳**）；req\_003 ← isaac（python 落盘 `req_003.py`，80%/0.8，runtime\_check **passed**）。`missing=[]`、`errors=[]`，7 条 validation issue 全为 **WARNING**（完整度/置信度阈值，无 ERROR）。

### 单元测试回归

- 本次改动相关：**81 passed**（test\_franka / test\_allegro / test\_kinova / test\_github / test\_assemble / test\_parse\_convert）
- 完整测试套件（`pytest tests/ -q`）：**777 passed / 5 failed / 1 skipped**。5 项失败均为**预存问题**（robotiq 2 项：`test_adapter_base_url` 断言 raw URL 但 settings 已改 jsdelivr、`test_fetch_fallback_2f_xacro_format` 断言 xacro 但现返回已展开 urdf；google\_scanned 3 项：网络/异常类型断言），已用 git stash 验证在本次改动前同样失败，与本次修复无关。

## 五、最终系统状态说明

### 功能完整性

- **robot\_urdf 检索覆盖**：franka / allegro / robotiq / **kinova** / github 五源；Kinova Gen3（gen3/gen3\_lite）专用命中，URDF+7 网格资产数据包自包含（P0-3）。
- **网格跟随抓取**：GitHub 通用源与 kinova 专用源均随 URDF 抓取 mesh 资产；`package://` 前缀剥离后资产键与 URDF 引用自洽，离线可完整加载。
- **sim\_config**：python 资产正确落盘 `.py`；场景资源引用与落盘文件名一致；runtime\_check（MuJoCo 加载+一步仿真）真实通过。
- **4 个 day4 D 用例全部通过**（ss\_franka\_001 原 PASS 不重测；002/003 由降级升为 PASS；ms\_003 由 FAIL 升为 PASS）。

### 性能指标

| 指标 | 修复前 | 修复后 |
| ---- | ---- | ---- |
| kinova 资产下载（raw 直连） | 中途超时（>12s 预算） | 实测 28.2s（36s 预算内，7/7 资产） |
| ms\_003 单需求最慢（req\_000） | 52.6s → missing | 83.8s → success |
| ms\_003 整 case 耗时 | 194.2s（含缺失） | 108.0s（全通过） |
| ss\_franka 002/003 | 11.6~21.7s（网格缺失） | 11.6~21.7s（含 18 资产） |
| 单源预算（per\_req\_timeout/5） | 12s | 36s |

### 潜在风险评估

1. **GRASP req\_002 空壳**（残余，非本次修复目标）：GraspNet 仅落 json 元数据（60%/0.6，is\_fallback=true），非 NPZ 抓取姿态。不阻断 ms\_003 判定（robot\_urdf+mesh+sim\_config 已齐），但"抓取"数据未真实交付。
2. **kinova gen3\_lite 未端到端实测**：仅 gen3 走通；gen3\_lite 的 URDF 路径/资产引用结构未在真实流水线验证。
3. **jsdelivr 镜像对 half\_arm\_1/2\_link.STL 404**：当前依赖 raw.githubusercontent 慢速成功（未触发镜像兜底）；若 raw 挂起转镜像会丢 2 个资产 → 数据包 7/7 资产降为 5/7。已用 per\_req\_timeout 扩容缓解超时风险，但镜像缺口仍在。
4. **per\_req\_timeout 60→180 全局扩容**：完全失败的需求（所有候选源皆不命中）等待时间从 ~60s 增至 ~180s，为耗时 trade-off；成功路径不受影响。
5. **Allegro/Franka 匹配收紧**：单测 27 项已覆盖回归；day3 单源题真实流水线回归待下次执行确认（查询均含标识 token，理论上不受影响）；robotiq 未同步收紧（描述无泛词风险，ms\_003 查询实测不触发）。
6. **req\_003 format 元数据仍标 "mjcf"**（落盘 `.py`）：元数据不精确，功能不受影响（runtime\_check passed），属遗留展示问题。
7. **Hermes 动态优先级**使 github 排在 kinova 前尝试：github 每次多耗 ~17s 返回 markdown 被 C4 拦截后继续，属已知检索质量损耗，不阻塞命中。

---

# 最终结果：2026-08-17 前端真实流程重测（4/4 全部通过）

> 本节为**最终权威结果**。2026-08-17 对 day4/D 全部 4 题走真实前端（`src/rdi/frontend/app.py`，端口 7860）：radio「真实流程」→「运行」→ human_review 中断 →「数据包审查」选 satisfied →「继续运行」→「运行完成」；各 case 的 `record.json / observe.json / screenshots/` 均已按最新结果**覆盖写回**（含完整页面真实截图 8/8）。

| case_id | verdict | package_id | 落盘文件 | validation_issues(error) | 截图 |
|---|---|---|---|---|---|
| ss_franka_001 | **PASS** | package-20260817-113850 | 19（URDF+18 OBJ） | 0 | 8/8 |
| ss_franka_002 | **PASS** | package-20260817-115803 | 19（URDF+18 OBJ） | 0 | 8/8 |
| ss_franka_003 | **PASS** | package-20260817-120921 | 19（URDF+18 OBJ） | 0 | 8/8 |
| ms_003 | **PASS_WITH_FALLBACK** | package-20260817-122845 | 12 | 0（7 条 WARNING：完整度/置信度阈值 + grasp 近似） | 8/8 |

要点：

- **ss_franka_002/003**：首轮 PASS_WITH_FALLBACK（fallback 路径只落 URDF、18 个 OBJ 网格缺失）。2026-08-16 修复 GitHub 通用源网格跟随抓取后，本次前端真实流程重测**网格 18/18 随包交付** → 提升为 **PASS**。
- **ms_003**：首轮 FAIL/P2_RETRIEVE（Kinova 无源 + sim_config 格式错配）。2026-08-16 新增 KinovaAdapter + sim_config 格式/资源名一致性修复后重测通过；本次前端真实流程重测为 **PASS_WITH_FALLBACK**（req_002 grasp 为 GraspNet json 元数据 fallback、req_003 isaac python 落盘 .py，7 条 WARNING 均为质量阈值类，无 ERROR），12 文件全落盘。
- 截图：4 题全部 8/8 完整（中间态 + 最终态各 4 张，滚动分块拼接完整页面，无缺失）。
