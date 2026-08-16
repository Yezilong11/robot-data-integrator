# Day 3：D（机器人工程师）交付物

> 分支：`feat/arch-langgraph`
> 执行日期：2026-08-15
> 依据：`Day3_执行中段与多源交叉.md`（D 任务）+ `问题集构建策略.md`（record 模板/截图规范/判定 P1-P8）
> 问题集：`problem_set/problem_set.json`
> 交付目录：`deliverables/day3/D/`

## 执行范围（Day3-D）

| # | 任务 | 完成情况 |
|---|------|---------|
| 1 | 完成剩余的格式/仿真类单源题（allegro / robotiq / google_scanned） | ✅ 3×3=9 题全部执行并留档 |
| 2 | 搭建 1 道多源题交叉验证（ms_005，PyBullet 堆叠场景） | ✅ 执行并留档 |
| 3 | 逐个确认 sim_config 类记录的 runtime_check（mj_step 通过/失败）与 fallback 标记 | ✅ 见 `sim_config_runtime_check_review.md` |

全部 10 题均走真实流程：`run_graph`（前端「运行」→ interrupt human_review → 「继续运行」resume 打包），所有截图均为**实际运行环境下的真实界面截图**（滚动分块 + PIL 拼接，完整页面无截断）。

## 目录结构

```
deliverables/day3/D/
├── README.md                        # 本索引
├── sim_config_runtime_check_review.md  # 任务3：sim_config runtime_check（mj_step）复核确认
├── tools/
│   └── stitch_screens.py            # 截图拼接工具（滚动分块 → 完整页面）
├── ss_robotiq_001|002|003/          # Robotiq 2F-85 单源题
├── ss_allegro_001|002|003/          # Allegro Hand 单源题
├── ss_google_scanned_001|002|003/   # Google Scanned Objects 单源题
└── ms_005/                          # 多源交叉题（Franka + YCB + PyBullet）
    └── 每个 case：record.json + screenshots/{intermediate,final}/01~04.png
```

> 截图命名：01 目标输入 / 02 进度展示 / 03 校验与缺失项 / 04 数据包审查（中间态 + 最终态各一套，完整页面）。

## 执行结果总览

| case_id | input | 解析需求 | 命中源 | runtime_check | 落盘文件 | verdict |
|---|---|---|---|---|---|---|
| ss_robotiq_001 | Robotiq 2F-85 夹爪 URDF | [robot_urdf] match | robotiq | loaded_empty | 1（xacro 空壳） | **FAIL/P4_FORMAT** |
| ss_robotiq_002 | Robotiq 2F-85 URDF + 手指开合参数 | [robot_urdf, other] mismatch | robotiq | loaded_empty | 1 + 缺失 1 | **FAIL/P4_FORMAT** |
| ss_robotiq_003 | 抓取实验要装 Robotiq 夹爪，需要模型 | [robot_urdf] match | robotiq | empty | 0（C4 拦截） | **FAIL/P2_RETRIEVE** |
| ss_allegro_001 | Allegro Hand 灵巧手 URDF | [robot_urdf] match | github | empty | 0（C4 拦截） | **FAIL/P2_RETRIEVE** |
| ss_allegro_002 | Allegro URDF（4 指 16 关节） | [robot_urdf] match | allegro→github | empty | 0（C4 拦截） | **FAIL/P2_RETRIEVE** |
| ss_allegro_003 | Allegro 手模型文件 | [robot_urdf] match | allegro→github | empty | 0（C4 拦截） | **FAIL/P2_RETRIEVE** |
| ss_google_scanned_001 | GSO 任意物体 mesh | [dataset] mismatch | zenodo | empty | 1（错误 DatasetSummary） | **FAIL/P1_PARSE** |
| ss_google_scanned_002 | GSO 水壶 kettle mesh | [mesh] match | google_scanned | empty | 0（json 解析失败） | **FAIL/P4_FORMAT** |
| ss_google_scanned_003 | GSO 大体积物体 mesh | [mesh] match | google_scanned | empty | 0（json 解析失败） | **FAIL/P4_FORMAT** |
| ms_005 | Franka Panda stacks YCB blocks in PyBullet | [robot_urdf, mesh, robot_urdf] mismatch | franka/github/fuel | empty | 1（mesh fallback）+ 缺失 2 | **FAIL/P2_RETRIEVE** |

## 关键结论与发现

### 1. Robotiq 系列（ss_robotiq_001/002/003）——xacro 空壳与格式错配双路径

- **P4_FORMAT（001/002）**：RobotiqAdapter 命中 `ros-industrial-attic/robotiq` 仓库 `.xacro` 文件（robotiq_arg2f_85_model.xacro，仅 include+宏调用）。assemble 按 `raw_bytes` 直接落盘 xacro 原文，**未走 URDFSkill 的 xacro 展开分支**，yourdfpy 加载 `LOAD_OK links=0 joints=0`——内容不可用但 manifest 仍标 format=urdf、complete。
- **P2_RETRIEVE（003）**：中文口语化目标（"要装 Robotiq 夹爪"）下，RobotiqAdapter 检索返回 markdown 网页抓取产物，与 robot_urdf 期望格式（urdf/xacro）类型错配，被 C4 检测拦截，落盘 0 文件。
- 结论：Robotiq 源对「原始 xacro 展开」与「网页 markdown 抓取」两条路径均缺转换/清洗能力，是本系列根因。

### 2. Allegro 系列（ss_allegro_001/002/003）——无专用适配器，统一 P2_RETRIEVE

- allegro 无专用 adapter（problem_set 映射到通用源），专用源级检索 3 轮迭代均超时（`per_req_timeout/4=15s`），随后通用 GitHubAdapter 返回 markdown 网页抓取产物，C4 类型错配拦截，落盘 0 文件。
- 三题一致失败于 P2_RETRIEVE，与 Day2 观察吻合：**通用 GitHub 检索对机器人 URDF 目标的召回均为 markdown 而非 URDF/xacro**。

### 3. Google Scanned Objects 系列（ss_google_scanned_001/002/003）——两条不同失败路径

- **P1_PARSE（001）**：目标含「数据集」关键词，LLM 把 mesh 需求误解析为 dataset 类型，Zenodo 返回完全无关的论文摘要（CITT PDF），落盘 DatasetSummary JSON（confidence=1.0）而非 mesh——**产出内容错误但包仍标 complete**，暴露 parse 层对 GSO 专有名词的识别缺陷。
- **P4_FORMAT（002/003）**：google_scanned 源检索产物为 **json 元数据**，MeshSkill 不支持 `file_type=json`（期望 glb/obj/ply），3 轮迭代均解析失败，落盘 0 文件；alternatives 指向 fuel.gazebosim.org 手动下载。**未观察到题目预期的「下载超时/失败显式降级路径」（is_fallback 标记）**。

### 4. ms_005 多源交叉验证——链路断裂点定位

- 题目：Franka Panda 在 PyBullet 中堆叠 YCB blocks（3 需求：robot_urdf + mesh + robot_urdf）。
- LLM 把 PyBullet 场景需求误判为第二条 robot_urdf（期望应为 sim_config/pybullet 场景），两条 robot_urdf 全部缺失：
  - franka 源 3 轮超时（15s）→ 通用 GitHub 返回 markdown → C4 拦截；
  - req_002 通用 GitHub 同样返回 markdown（PyBullet 场景误判）→ C4 拦截。
- **mesh 经 fallback 成功**：`objects/req_001.stl`（YCB 50_BLOCKS tip），`is_fallback=true`，trimesh 验证 `LOAD_OK`（5362 顶点 / 10728 面 / 封闭）。
- 结论：多源题在「机器人 URDF」链路上与单源题共享同一检索瓶颈（无 URDF 专用源 + 通用 GitHub 返回 markdown），未达 `min_files=2`，场景无法构建。

### 5. sim_config runtime_check 复核（任务 3）

详见 [sim_config_runtime_check_review.md](sim_config_runtime_check_review.md)。要点：

- C 的 7 条 sim_config 记录（ss_mujoco_001~005、ss_isaac_001~002）中，3 条 `runtime_check=passed`（mj_step 真实通过）、4 条 `empty`（未触发验证，非失败）；无 `failed/skipped`。
- C 引用的 7 个数据包目录均已清理，不可直接读 manifest；本复核以**现存 4 个 Day2 panda 包**（manifest `req_001.status=passed`，detail「MuJoCo 加载与一步仿真成功」，88 资产）为证据链，并**独立实测** package-20260814-154110 的 `sim_config/req_001.xml`：`mj_step → PASS bodies=12 time=0.002s`。
- 代码路径核对 `validate.py::_mujoco_runtime_check`（L286-351）：仅 xml/mjcf 触发 MuJoCo 验证；passed=加载+一步仿真成功，empty=未进入验证路径，skipped=资源缺失降级，failed=真实编译/仿真错误。
- fallback 标记：仅 ss_mujoco_004 一处（retrieve.quality=fallback, source=isaac，PASS_WITH_FALLBACK）；现存 panda 包 is_fallback 全 false。

## 根因归纳（Day3-D 视角）

| 失败码 | 出现次数 | 根因 |
|---|---|---|
| P2_RETRIEVE | 6（robotiq_003、allegro×3、ms_005×2 需求） | 无 URDF/场景专用源或源超时后，通用 GitHub 检索返回 markdown → C4 拦截 |
| P4_FORMAT | 4（robotiq_001/002、google_scanned_002/003） | xacro 未展开直接落盘；json 元数据不为 MeshSkill 支持格式 |
| P1_PARSE | 1（google_scanned_001） | 「数据集」关键词诱导 dataset 误判，产出完全无关内容 |

系统性结论：**URDF/场景类需求缺专用适配器 + 通用 GitHub 检索质量差（markdown）** 是本批次 P2 主因；**xacro→URDF 转换与 json 元数据过滤**是 P4 主因；两者均为平台能力缺口，非网络偶发。

## 失败修复与重测记录（2026-08-16）

> 本节记录第一轮 10 题全部 FAIL 之后的根因定位、代码修复与重测全过程。
> 重测仅更新 README，**不修改**各 case 已有文件夹（含截图/record），且重测过程不再截图。

### 一、修复后重测结果（10/10 全部通过）

| case_id | 首轮 verdict | 修复后命中源 | 修复后 format | 落盘文件 | missing | validate | 耗时 |
|---|---|---|---|---|---|---|---|
| ss_robotiq_001 | FAIL/P4_FORMAT | robotiq | urdf | 11（URDF+10 mesh） | 0 | issue=1, error=0 | 25.9s |
| ss_robotiq_002 | FAIL/P4_FORMAT | robotiq | urdf | 11 | 0 | issue=1, error=0 | 17.7s |
| ss_robotiq_003 | FAIL/P2_RETRIEVE | robotiq | urdf | 11 | 0 | issue=1, error=0 | 18.2s |
| ss_allegro_001 | FAIL/P2_RETRIEVE | allegro | urdf | 12（URDF+11 mesh） | 0 | issue=0 | 56.8s |
| ss_allegro_002 | FAIL/P2_RETRIEVE | allegro | urdf | 12 | 0 | issue=0 | 14.4s |
| ss_allegro_003 | FAIL/P2_RETRIEVE | allegro | urdf | 12 | 0 | issue=0 | 14.2s |
| ss_google_scanned_001 | FAIL/P1_PARSE | google_scanned | obj | 1 | 0 | issue=0 | 22.5s |
| ss_google_scanned_002 | FAIL/P4_FORMAT | google_scanned | obj(stl) | 1 | 0 | issue=0 | 13.4s |
| ss_google_scanned_003 | FAIL/P4_FORMAT | google_scanned | obj | 1 | 0 | issue=0 | 11.6s |
| ms_005 | FAIL/P2_RETRIEVE | franka+google_scanned+isaac | urdf/obj/python | 21 | 0 | issue=5, error=0 | 72.5s |

- 每需求均为 `status=success`；robotiq×3、allegro×3、google_scanned×3 全部 `is_fallback=false`（命中专用源）。
- ms_005 三条需求全 success：req_000 robot_urdf←franka（6.1s，is_fallback=false）、req_001 mesh←google_scanned（fallback）、req_002 sim_config←isaac（fallback）；`missing=[]`、`errors=[]`。
- 验证 issue 均为 WARNING 级非 ERROR（`error_count=0`），不影响数据包完整性。ms_005 的 5 条 WARNING 明细（2026-08-16 探针确认）：① req_000 完整度 80%<100%；② req_000 置信度 0.80<1.0；③ req_002 完整度 80%；④ req_002 置信度 0.80；⑤ req_002 MJCF 资源引用未解析（`objects/50_BLOCKS.stl`，runtime_check 因此 skipped）。其中①②③④为质量分数阈值判定（franka urdf 与 isaac 场景均无 ERROR），⑤为 sim_config 场景资源名与落盘路径不一致（落盘 `req_001.stl`，场景引用 `50_BLOCKS.stl`）——属场景组装细节，不属检索/格式失败。

### 二、根因定位（按 case 汇总）

| case | 首轮失败码 | 根因 |
|---|---|---|
| ss_robotiq_001 | P4_FORMAT | robotiq 源命中 `*.xacro` 包装文件（仅 include+宏调用），assemble 原样落盘为 .urdf → yourdfpy 加载 0 links/0 joints 空壳 |
| ss_robotiq_002 | P4_FORMAT | 同上；另 GitHub 源对 robot_urdf 返回 markdown README，检索期未预检格式，占用命中位置 |
| ss_robotiq_003 | P2_RETRIEVE | 口语 query「Robotiq 夹爪」无法命中硬编码 id；robotiq 源被误判未收录；GitHub markdown 提前截断检索 |
| ss_allegro_001/002/003 | P2_RETRIEVE | 通用 GitHub 源对 URDF 目标返回 markdown README，被当作 success 提前终止检索，专用源再无机会 |
| ss_google_scanned_001 | P1_PARSE | 描述性 query（"任意一个 mesh"）Fuel 搜索空；`3d` 词被当有效词元搜出无关模型；兜底候选走串行 Fuel `?q` 搜索，20s 预算内跑不完 |
| ss_google_scanned_002 | P4_FORMAT | kettle 词元可命中但命中 json 元数据 → MeshSkill 不支持 json 格式（重测前修复后直接通过） |
| ss_google_scanned_003 | P4_FORMAT | stopword-only query（"大体积"）；同 001 的 `3d` 词元与兜底候选问题 |
| ms_005 | P2_RETRIEVE | ① franka raw.githubusercontent 主链挂起 42s 超源预算；② PyBullet 场景需求被 LLM 误判为第二条 robot_urdf；③ GitHub markdown 截断；④ franka urdf `package://` 引用无法离线加载 |

**共性根因（3 条）**：
1. **通用源（GitHub）检索期缺格式预检**——markdown README 被当作 success，提前终止检索，专用源（robotiq/allegro/franka）再无机会 → 表现为 P2。
2. **专用源慢/超时/路径错误**——robotiq xacro 未展开、franka raw 主链挂起、google_scanned Fuel 搜索慢 → 表现为 P4/P1。
3. **parse_goal 强词优先级缺陷**——描述性 query 误判需求类型/词元（"3d"、"数据集"）→ 表现为 P1。

### 三、代码修复清单

| 文件 | 改动 |
|---|---|
| `src/rdi/graph/nodes/parse_goal.py` | ①移除 git 合并冲突残留标记（`<<<<<<<`/`>>>>>>>`，曾致 SyntaxError 使整个流水线无法启动）；②删除重复的第二个 `SIM_CONFIG` 条目 |
| `src/rdi/adapters/robotiq.py` | ①`_PRIMARY_FAST_TIMEOUT_S=3.0` 快速超时转 fallback；②新增 xacro 轻量展开器（`_XACRO_*` 正则族：include 内联 + 宏调用展开 + `${expr}` 求值），产出纯 URDF；③`_resolve_xacro_include` 保留 `$(find pkg)` 包名作路径首段，include 链逐层并发下载（冷全链路 13.8s→3.4s）；④`_search_fallback` 改为 token 级匹配 |
| `src/rdi/adapters/franka.py` | ①纯 URDF 源改 jsdelivr 直达（fetch 42s→~3s）；②`_PRIMARY_FAST_TIMEOUT_S` 5s→3s；③`_search_fallback` token 级匹配；④primary/fallback 均剥离 `package://` 前缀，使 mesh 引用与资产键一致（pkg_refs=0） |
| `src/rdi/adapters/google_scanned.py` | ①`_metadata_fallback` 由返回 json RawData 改为**抛 AdapterError**（json 在 C4 白名单内不触发错配、终结检索循环且 MeshSkill 必解析失败）；②`_SEARCH_STOPWORDS` 增加 `"3d"`；③兜底候选直接构造 SearchResult（免 3 次串行 Fuel `?q` 往返，本环境慢、预算内跑不完） |
| `src/rdi/skills/registry.py` | 新增公共函数 `is_format_allowed(req_type, fmt)`（C4 白名单真源，装配期与检索期共用） |
| `src/rdi/graph/nodes/retrieve_data.py` | ①检索期格式预检（C4-pre）：fetch 后立即用 `is_format_allowed` 校验，GitHub 对 robot_urdf 返回 markdown 时记为 `error_type="format_mismatch"` 的 RetrievalError 并 `continue` 下一候选源；②`inject_experience` 调用包 try/except 兜底 |
| `src/rdi/config/settings.py` | `robotiq_base_url` 默认值改为 jsdelivr 镜像 |

### 四、重测过程记录（两轮）

1. **第一轮全量重测**（`data/_rerun_day3.py`，10 用例）：8/10 通过（robotiq×3、allegro×3、ss_google_scanned_002、ms_005）；仍失败 2/10：ss_google_scanned_001/003（google_scanned 搜索空，ycb/graspnet 均未收录）。结果存 `data/_rerun_day3_results.json`。
2. **修复 google_scanned 兜底后针对性重跑**（`data/_rerun_day3_gs.py ss_google_scanned_001 ss_google_scanned_003`）：2/2 通过（source=google_scanned, format=obj, 1 文件, missing=0, validate pass）。结果存 `data/_rerun_day3_gs_results.json`。
3. **修复 franka `package://` 后重跑 ms_005**：通过（3 req 全 success，franka 6.1s，21 文件，missing=0，errors=0，validate `error_count=0`）。

### 五、探针验证数据（`data/_probe_*.py`）

| 探针 | 验证点 | 结果 |
|---|---|---|
| `_probe_robotiq_e2e.py` | robotiq 全链路耗时 | 冷 10.8s（预算内）、热 3.4s；11 links/11 joints/10 assets |
| `_probe_gs_fallback.py` | google_scanned 兜底 + franka 离线资产 | 兜底命中 1.2s、fetch obj 5.6s；franka panda fetch 3.4s、`pkg_refs=0`、assets=18 |

> 临时重测/探针脚本位于 `data/_rerun_day3*.py`、`data/_probe_*.py`（不入库），结果留档于 `data/_rerun_day3*.json/log`。

## 附：真实截图说明

所有截图均为浏览器实际运行 Gradio 前端（`src/rdi/frontend/app.py`，端口 7860）时截取的真实界面，经 `tools/stitch_screens.py` 将视口分块拼接为完整页面，无模拟/合成图像。
