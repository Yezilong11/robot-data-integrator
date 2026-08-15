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

## 附：真实截图说明

所有截图均为浏览器实际运行 Gradio 前端（`src/rdi/frontend/app.py`，端口 7860）时截取的真实界面，经 `tools/stitch_screens.py` 将视口分块拼接为完整页面，无模拟/合成图像。
