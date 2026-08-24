# A 二轮问题测试总结

> 执行人：A ｜ 执行日期：2026-08-22 ｜ 执行方式：前端真实流程（非 mock）
> LLM 引擎：qwen3.7-plus（OpenAI 兼容） ｜ 分支：feat/integration-v3 @ 5fffe26
> 覆盖范围：A 二轮新题 12 题（P0×1、P1×4、P2×7），其中 ms_012 多源、其余单源

## 一、总体结果

| 判定 | 数量 | 占比 |
|---|---|---|
| PASS | 0 | 0% |
| PASS_WITH_FALLBACK | 1 | 8.3% |
| FAIL | 11 | 91.7% |
| **可用率** | **1/12** | **8.3%** |

- vs_expected：match 8 / partial 3（ms_012、ss_allegro_005、ss_graspnet_003）/ mismatch 2（ss_code_github_001、ss_zenodo_007）
- 全部 12 题均已归档 record.json + 截图（每题 3~6 张，对齐 C 命名规范 01_manifest/02_provenance_log/04_req_file/05_explorer）

## 二、逐题结果

| # | case_id | 优先级 | 目标 | 判定 | 数据源 | 文件数 | 数据包 | 异常摘要 |
|---|---|---|---|---|---|---|---|---|
| 1 | ms_012 | P1 | UR5+Robotiq 抓 GSO 物体 | FAIL(P4_FORMAT) | github+google_scanned+graspnet | 3 | package-20260822-071239 | URDF 为 xacro 模板未展开；grasp 为 116B 占位；LLM 多解析出 grasp |
| 2 | ss_allegro_005 | P2 | Allegro 手 URDF | FAIL(P2_RETRIEVE) | github+internet | 17 | package-20260822-075152 | URDF mesh 全缺失；grasp 0B 占位；sim_config 错配为 Cassie 机器人 |
| 3 | ss_code_github_001 | P1 | GitHub 运动学求解 Python 代码 | FAIL(P5_RUNTIME) | — | 0 | package-20260822-080947 | parse_goal LLM 调用失败(LLMParseError)，降级空需求，全程跳过，空包 |
| 4 | ss_github_006 | P2 | 机械臂控制 GitHub 项目(中文) | FAIL(P4_FORMAT) | github | 1 | package-20260822-082500 | CodeRepoSummary json 摘要≠md；英文≠题设中文；file_tree/framework 全空 |
| 5 | ss_google_scanned_004 | P2 | GSO 椅子 mesh | FAIL(P2_RETRIEVE) | ycb+graspnet | 0 | package-20260822-084002 | 未检索题设源 google_scanned；ycb 3 轮源级超时(60s×3)；空包 |
| 6 | ss_grasp_dexgrasp_002 | P2 | DexGraspNet bowl 抓取(中文) | FAIL(P2_RETRIEVE) | dexgrasp | 1 | package-20260822-084943 | 114B 元数据占位，无真实 pkl |
| 7 | ss_graspnet_003 | P1 | GraspNet camera_0 抓取 | FAIL(P2_RETRIEVE) | graspnet(HF) | 2 | package-20260822-085700 | dataset 空占位 106B；grasp 116B 占位；LLM 多解析 dataset |
| 8 | ss_kinova_001 | P0 | Kinova Gen3 URDF | FAIL(P4_FORMAT) | github(非目标源) | 1 | package-20260822-090719 | 命中非目标源静默降级；URDF 8 个 STL mesh 全未下载 |
| 9 | ss_mujoco_009 | P2 | 无机械臂纯物体 MuJoCo 场景 | FAIL(P3_SOURCE) | mujoco | 69 | package-20260822-091602 | 内容错配：产出 franka_emika_panda 完整机械臂场景，与题设"无机械臂"语义相反；validate 0 error 假象 |
| 10 | ss_robotiq_004 | P1 | Robotiq 2F-85 URDF 供 MoveIt | **PWF** | github(非目标源) | 11 | package-20260822-092940 | URDF+10 mesh 完整可用，yourdfpy 加载通过(11 links/10 joints)；命中非目标源静默降级 |
| 11 | ss_urdf_github_001 | P2 | GitHub 上 UR5 URDF | FAIL(P4_FORMAT) | github | 1 | package-20260822-094052 | 命中目标源但拿到 ur_common.xacro 宏库(369 处宏引用)，yourdfpy 加载 KeyError |
| 12 | ss_zenodo_007 | P2 | Zenodo 关节传感器数据集 | FAIL(P2_RETRIEVE) | zenodo | 1 | package-20260822-095157 | 68B 占位(无 signals)；req_type sensor_data vs 题设 dataset mismatch；自评严重高估 |

## 三、FAIL 聚类分析

| 聚类 | 涉及题 | 根因方向 |
|---|---|---|
| **检索降级占位**（P2_RETRIEVE） | ss_allegro_005、ss_google_scanned_004、ss_grasp_dexgrasp_002、ss_graspnet_003、ss_zenodo_007（5/11） | 小源未收录/弱命中，产出 0~116B 元数据占位冒充数据；源级超时(60s)无 fallback |
| **URDF/xacro 处理链**（P4_FORMAT） | ms_012、ss_kinova_001、ss_urdf_github_001（3/11） | 检索规划未筛选具体模型文件（拿到宏库/非目标文件）；parse_convert 无 xacro 展开；URDF mesh 不随包下载 |
| **内容语义错配**（P3_SOURCE） | ss_mujoco_009、ss_allegro_005（sim_config 部分） | validate 只做结构校验不查语义（0 error 假象），错配场景未被拦截 |
| **LLM 自评不可靠** | ms_012、ss_mujoco_009、ss_zenodo_007 等多题 | 自评"可用/质量极高"与实际数据错配/空占位严重不符，不能作为质量依据 |
| **非目标源静默降级** | ss_kinova_001、ss_robotiq_004 | manifest 不标 is_fallback，系统降级不可见（仅第 4 轮修正时人工补标） |
| **LLM 解析过度/req_type 对齐** | ss_graspnet_003、ss_allegro_005、ss_zenodo_007 | 单源题多解析需求；req_type 与题设 category 不一致（sensor_data vs dataset） |
| **LLM 调用失败无兜底** | ss_code_github_001 | parse_goal LLM 失败降级返回空需求，后续全跳过产空包，无重试/熔断 |

## 四、异常与风险记录

1. **截图规范缺口（校验口径冲突）**：全库 FAIL 题均报 `FAIL 必须包含报错截图`——record 截图 desc 无 error/报错关键词即触发；C/D 一轮复测与全部 FAIL record 均如此，属摸底口径待修复阶段统一（本次未修，如实保留）。
2. **校验与真实的对抗项**：PASS 判定遇降级会报 ERROR（存在降级不能判 PASS）→ 本批唯一可用数据 ss_robotiq_004 按 PWF 记录；"命中非目标源未标记"ERROR 靠人工补标 is_fallback 消除，需组长 B 在系统侧补 manifest 标记。
3. **数据包落盘路径**：record 的 package.dir 统一按 `data/output_packages/package-<时间戳>` 完整路径记录（D 格式），避免校验路径 WARNING。
4. **runtime_check 枚举**：`ALLOWED_RUNTIME_CHECKS={passed, failed, not_applicable, not_run}`（无 not_required）；URDF 类题必须真实加载验证（yourdfpy），本批 ss_robotiq_004=passed、ss_urdf_github_001/ss_kinova_001=failed。

## 五、给组长 B 的修复方向（按优先级）

1. **URDF/xacro 处理链**（影响 3 题，P0 题 ss_kinova_001 在内）：检索规划增加"具体模型文件"筛选 + parse_convert 实现 xacro 展开 + mesh 随包下载
2. **检索源规划**：题设指定源（source 字段）优先；受限小源（ycb 仅 20 目标、graspnet 仅 2 目标）纳入源选择约束；源级超时缩短或启用并行
3. **降级占位拦截**：0~116B 元数据占位不应视为可用数据，需 quality 校验拦截或标 FAIL
4. **LLM 自评机制**：自评需基于真实文件内容核验（当前自评与实际严重不符），或自评结果不作为判定依据
5. **validate 语义校验**：增加需求语义匹配检查（如"无机械臂"vs"含机械臂"），避免 0 error 假象
6. **manifest 降级标记**：非目标源命中时系统自动标 is_fallback
7. **LLM 失败兜底**：parse_goal 失败重试/熔断，避免直接空包

## 六、交付物清单

- `records/ms_012/`、`records/ss_allegro_005/`、`records/ss_code_github_001/`、`records/ss_github_006/`、`records/ss_google_scanned_004/`、`records/ss_grasp_dexgrasp_002/`、`records/ss_graspnet_003/`、`records/ss_kinova_001/`、`records/ss_mujoco_009/`、`records/ss_robotiq_004/`、`records/ss_urdf_github_001/`、`records/ss_zenodo_007/`（record.json + screenshots/）
- 本报告：`records/A_round2_summary.md`
- 全部数据包：`data/output_packages/package-20260822-*`（12 个）
- 复核状态：reviewer/reviewed_at 均待 F 复核后填写
