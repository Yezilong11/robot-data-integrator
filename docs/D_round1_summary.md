# D 负责一轮 23 题前端全流程测试汇总报告

- **执行人**：D
- **执行日期**：2026-08-20（15:23–17:30）
- **执行方式**：前端真实流程测试（http://127.0.0.1:8000/，输入目标 → 点击运行 → human_review 中断 → 点击"继续运行"（satisfied）→ 提取最终结果）
- **LLM 引擎**：qwen-plus（dashscope.aliyuncs.com/compatible-mode/v1）
- **数据记录**：每个用例的 `records/<case_id>/record.json` 均已覆盖更新；观测数据取自 `data/output_packages/package-*/manifest.json` 与 `/api/result/{task_id}`

---

## 一、总体统计

| 判定 | 数量 | 占比 | 用例 |
|---|---|---|---|
| PASS | 10 | 43.5% | ss_allegro_001/002/003、ss_franka_002、ss_google_scanned_002、ss_mujoco_001/005、ss_robotiq_001/002/003 |
| PASS_WITH_FALLBACK | 6 | 26.1% | ss_franka_001/003、ss_isaac_001/002、ss_mujoco_002、ss_ycb_003 |
| FAIL | 7 | 30.4% | ms_003、ss_google_scanned_001/003、ss_mujoco_003/004、ss_ycb_001/002 |

- FAIL 分类：P2_RETRIEVE（检索失败）= 5（ms_003、ss_google_scanned_001/003、ss_ycb_001/002）；P4（内容正确性）= 2（ss_mujoco_003/004）
- 全部 23 题前端流程均可正常运行至终态；7 个 FAIL 均非系统崩溃，而是业务性检索失败或交付内容错误。

---

## 二、逐题测试明细

| # | case_id | 目标输入 | 判定 | 数据源（最终） | 文件数 | run_id / 数据包 | 异常摘要 |
|---|---|---|---|---|---|---|---|
| 1 | ms_003 | Kinova Gen3 picks up EGAD mug in Isaac Sim | FAIL(P2) | isaac | 1 | 20260820-152332-ac3eca3a / package-20260820-153109 | EGAD mug mesh 全源缺失（google_scanned 60s 超时、ycb/graspnet 未收录）；sim_config 命中 franka.py 而非 Kinova（P4 隐患） |
| 2 | ss_allegro_001 | 获取 Allegro Hand 手部 URDF 模型 | PASS | allegro | 12 | 20260820-153442-ca29efac / package-20260820-153516 | 无 |
| 3 | ss_allegro_002 | Allegro 左手/右手 URDF 变体 | PASS | allegro | 12 | 20260820-153633-5788c9de / package-20260820-153714 | 无 |
| 4 | ss_allegro_003 | Allegro Hand 抓取模型 | PASS | allegro | 12 | 20260820-153807-896685 / package-20260820-153840 | 无 |
| 5 | ss_franka_001 | 获取 Franka Panda 机器人 URDF | PASS_WITH_FALLBACK | github | 1 | 20260820-153934-9223e937 / package-20260820-154047 | franka 专用源 36s 超时→降级 github（panda_gz_moveit2），仅 URDF 无 mesh |
| 6 | ss_franka_002 | Franka Panda URDF（含网格） | PASS | franka | 19 | 20260820-154145-93882e05 / package-20260820-154225 | 无（pybullet_robots jsdelivr CDN 正常） |
| 7 | ss_franka_003 | Franka Panda URDF（口语化） | PASS_WITH_FALLBACK | github | 1 | 20260820-154325-2ea4e6f9 / package-20260820-154437 | 同 ss_franka_001：36s 超时降级 |
| 8 | ss_google_scanned_001 | Google Scanned Objects Banana for Scale mesh | FAIL(P2) | - | 0 | 20260820-154539-3bea8763 / package-20260820-155134 | tip/files 接口 404 + 3 轮 60s 超时，0 文件 |
| 9 | ss_google_scanned_002 | Google Scanned Objects 茶壶 mesh | PASS | google_scanned | 1 | 20260820-155259-c4de6a12 / package-20260820-155421 | 无（Threshold_Porcelain_Teapot_White，obj→stl 416KB） |
| 10 | ss_google_scanned_003 | Google Scanned Objects 家具/家电 mesh | FAIL(P2) | - | 0 | 20260820-155516-e7e46342 / package-20260820-160153 | 3 轮 60s 超时，0 文件 |
| 11 | ss_isaac_001 | Isaac Sim 中 Franka Panda 场景配置 | PASS_WITH_FALLBACK | isaac | 1 | 20260820-160314-1f1461b9 / package-20260820-160338 | IsaacLab franka.py mjcf 兜底，runtime_check 通过 |
| 12 | ss_isaac_002 | Isaac Sim 场景（无明确目标） | PASS_WITH_FALLBACK | isaac | 1 | 20260820-160453-c2bab659 / package-20260820-160523 | 无目标语义时固定返回 franka.py 默认资产 |
| 13 | ss_mujoco_001 | mujoco_menagerie Franka Panda 场景配置 | PASS | mujoco | 69 | 20260820-160641-37794e59 / package-20260820-160755 | 无（scene.xml+panda.xml+67 mesh） |
| 14 | ss_mujoco_002 | mujoco_menagerie Franka 抓取操作场景 | PASS_WITH_FALLBACK | isaac | 1 | 20260820-161102-59344423 / package-20260820-161257 | mujoco 源 90s 超时（per_req_timeout/2）→降级 isaac |
| 15 | ss_mujoco_003 | mujoco_menagerie UR5e 场景配置 | FAIL(P4) | isaac | 1 | 20260820-161653-0924f6d0 / package-20260820-161730 | **降级命中 ant.py（蚂蚁），与 UR5e 完全无关** |
| 16 | ss_mujoco_004 | mujoco_menagerie Kitchen 厨房场景 | FAIL(P4) | isaac | 1 | 20260820-161937-42f8301b / package-20260820-162017 | **降级命中 ant.py，与厨房场景完全无关** |
| 17 | ss_mujoco_005 | 口语化：MuJoCo 搭 Franka 找场景配置 | PASS | mujoco | 69 | 20260820-162310-bee9a6a1 / package-20260820-162430 | 无（口语化输入正确解析，直连命中） |
| 18 | ss_robotiq_001 | Robotiq 2F-85 夹爪 URDF | PASS | robotiq | 11 | 20260820-162636-1aa0c1fc / package-20260820-162716 | 无 |
| 19 | ss_robotiq_002 | Robotiq 2F-85 URDF + 手指开合参数 | PASS | robotiq | 11 | 20260820-162948-4843cd0f / package-20260820-163029 | 轻微：开合参数子意图未显式解析为独立需求（P4 轻微） |
| 20 | ss_robotiq_003 | 口语化：装 Robotiq 夹爪要模型 | PASS | robotiq | 11 | 20260820-163353-4326480f / package-20260820-163429 | 无 |
| 21 | ss_ycb_001 | YCB banana mesh | FAIL(P2) | - | 0 | 20260820-163813-edc17a8b / package-20260820-164240 | ycb 60s 超时+20 目标列表未收录 banana；google_scanned 404；graspnet 仅 2 目标 |
| 22 | ss_ycb_002 | YCB apple mesh | FAIL(P2) | - | 0 | 20260820-164552-1c24108f / package-20260820-165238 | 同 banana：全源未命中 |
| 23 | ss_ycb_003 | YCB mug（马克杯）mesh | PASS_WITH_FALLBACK | google_scanned | 1 | 20260820-172925-f0753e34 / package-20260820-173041 | ycb 60s 超时→降级 google_scanned 命中 ACE_Coffee_Mug |

---

## 三、发现的问题与初步分析

### 1. 【严重 P4】isaac 降级适配器兜底内容与目标完全无关（ss_mujoco_003/004）
- 现象：UR5e、Kitchen 两个目标，mujoco 源未命中后降级 isaac，返回的是 IsaacLab `robots/ant.py`（蚂蚁机器人），与目标（UR5e 机械臂、厨房场景）毫无关系；且 `retrieval_errors` 为空（mujoco 源未报超时/错误，仅无有效结果）。包 0 缺失、0 error、runtime_check 通过——验证的却是错误模型。
- 分析：isaac 适配器对"无匹配语义的目标"（非 Franka 的机器人、场景/物体）一律返回默认 ant.py 资产，**未校验目标对象名与兜底资产的匹配性**，系统将其标记为"降级"而非失败，导致错误内容被正常交付。这是本轮测试发现的最严重正确性缺陷。
- 建议：兜底前增加目标-资产语义匹配校验（如目标名关键字与资产名相似度），不匹配应判 FAIL 而非降级交付。

### 2. 【P3_SOURCE / P5】YCB 适配器已知目标列表覆盖不全（ss_ycb_001/002/003）
- 现象：ycb 适配器仅收录 20 个已知目标，banana/apple 均未收录（历史经验显示同类任务曾成功 38.4s，本次全失败，检索不稳定）；mug 检索也 60s 超时，靠 google_scanned 兜底成功。
- 分析：已知目标列表是硬编码/不完整枚举，导致大量 YCB 常见物体（banana/apple 为 YCB 核心物体）直接"有源但未收录"；graspnet 适配器更只有 2 个已知目标。
- 建议：ycb 适配器接入 YCB 官方模型仓库的物体枚举或动态检索，扩大覆盖；graspnet 扩充已知目标。

### 3. 【P3_SOURCE】google_scanned 适配器 tip/files 接口 404（ss_google_scanned_001、ss_ycb_001）
- 现象：`Banana for Scale` 等模型 `https://fuel.gazebosim.org/1.0/GoogleResearch/models/.../tip/files` 返回 404（zip 可手动下载但系统无法取文件树）；大体积物体连续 3 轮 60s 超时。
- 分析：fuel.gazebosim tip/files 对部分模型不存在/不稳定，适配器无 zip 直下兜底；迭代重试无快速失败，单题最长耗时约 4.5 分钟。
- 建议：404 时改走 zip 下载解析；超时重试加入快速失败或并发降级。

### 4. 【P3_SOURCE / P5】franka 专用源 raw.githubusercontent 直连超时（ss_franka_001/003）
- 现象：ss_franka_001/003 的 franka 源 36s（per_req_timeout/5）超时后降级 github；而 ss_franka_002 走 jsdelivr CDN 正常（19 文件）。
- 分析：raw.githubusercontent.com 直连在当前网络环境下不稳定，CDN 路径可靠；同一源不同路径稳定性差异大。
- 建议：franka 源默认走 jsdelivr CDN，raw 直连作为备选。

### 5. 【P5】mujoco 源检索稳定性差异（ss_mujoco_001/002/005 vs 003/004）
- 现象：同为 Franka 目标，001/005（"场景配置"）直连 62~64s 命中 69 文件；002（"抓取操作场景"）90s 超时；003/004 未命中且无错误记录。
- 分析：检索逻辑对不同语义（抓取/场景/机器人名）存在命中路径差异，耗时与命中不稳定，且无错误时静默跳源导致后续 isaac 错误兜底（见问题 1）。

### 6. 【P4 轻微】LLM 解析子意图丢失（ss_robotiq_002）
- 现象："获取 URDF，并确认其手指开合参数"只解析出 1 条 robot_urdf 需求，开合参数确认子意图未提取为独立验证项（参数内含于 URDF 关节 limit，用户需自行读取）。
- 建议：对"确认/验证某参数"类子意图增加显式解析与验证项生成。

### 7. 【前端/服务】human_review 状态恢复依赖内存 checkpoint（ss_ycb_002 观察）
- 现象：任务完成后 `_TASKS` 表 10 分钟清理，`/api/status/{task_id}` 返回 not found，但"继续运行"仍成功——resume 依赖模块级 `_pending_thread_id` 与内存 LangGraph checkpoint。
- 分析：任务中断后若服务重启，checkpoint 丢失将无法 resume；长期运行需持久化 checkpoint。

### 8. 【P4 隐患】ms_003 场景目标解析偏差
- 现象：目标明确为 Kinova Gen3 + EGAD mug，但 sim_config 需求命中 IsaacLab franka.py（非 Kinova），EGAD mug mesh 全源缺失。
- 分析：多源场景下优先满足"sim_config"类型，机器人名匹配未约束，且物体 mesh 无任何源覆盖。

---

## 四、结论

- 系统前端流程（输入 → 运行 → 人工审查中断 → 继续 → 打包）整体可用，23/23 可完成全流程，无崩溃。
- 检索成功率：10 PASS + 6 PASS_WITH_FALLBACK（降级可用）= 16/23 可交付，7/23 失败（其中 5 个为检索失败、2 个为交付内容错误）。
- **最需优先修复**：isaac 降级内容错误（问题 1）与 ycb/graspnet 已知目标覆盖不足（问题 2），前者直接交付错误模型、后者导致常见 YCB 物体不可用。
