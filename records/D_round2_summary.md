# D 二轮 12 题测试汇总（Round 2 · D）

> 执行人：D ｜ 分支：`feat/integration-v3`（bbaffb7）｜ 前端真实流程（输入 → 运行 → human_review → 继续运行 → 提取结果）
> 日期：2026-08-21 ｜ 引擎：qwen-plus ｜ 依据：二轮计划 `docs/second_round_plan.md` 验收口径
> 对应记录：`records/<case_id>/record.json`

## 1. 总体结果

| 判定 | 数量 | 用例 |
|---|---|---|
| PASS | 0 | — |
| PASS_WITH_FALLBACK | 4 | ss_arxiv_006、ss_google_scanned_006、ss_ieee_002、ss_mujoco_006 |
| FAIL | 8 | ms_009、ms_014、ss_dexgrasp_006、ss_isaac_003、ss_kinova_003、ss_mesh_ycb_008、ss_policy_hf_001、ss_sensor_github_002 |

**成功率（含降级）= 4/12 = 33.3%**，纯 PASS = 0。相比一轮（D 组 16/23 可用），二轮新题难度与源覆盖缺口显著放大，命中率大幅下降，符合二轮计划"先全量摸底、接受高 FAIL 率"的既定预期。

## 2. 逐题结果与判定

| case_id | 目标（摘要） | verdict | 类别 | 关键发现 |
|---|---|---|---|---|
| ms_009 | Kinova Gen3 grasps YCB bottle in MuJoCo | FAIL | P4_FORMAT | 4 需求 3 异常：URDF 8 STL 缺失、grasp 空文件（0 字节）、sim_config 命中 Cassie 非 Kinova |
| ms_014 | 抓取策略开源代码 + HF 权重 | FAIL | P2_RETRIEVE | huggingface.co 连接超时；降级仅 agents-course README 摘要，无权重 |
| ss_arxiv_006 | 检索机器人抓取 arXiv 论文（中文） | PASS_WITH_FALLBACK | — | 命中 2104.02271，PDF 未下载仅元数据 json |
| ss_dexgrasp_006 | 找 DexGraspNet 抓取标注（中文） | FAIL | P3_SOURCE | dexgrasp 源 3 轮 30s 超时；降级报"格式不支持 markdown"，0 文件 |
| ss_google_scanned_006 | GSO 任意物体 mesh for MuJoCo | PASS_WITH_FALLBACK | — | mesh 完美命中；over-parse 出 sim_config→ant.py 错配 |
| ss_ieee_002 | 检索 IEEE 抓取论文 | PASS_WITH_FALLBACK | — | IEEE 缺 API Key 静默降级 arXiv（内容类型偏离） |
| ss_isaac_003 | Isaac Sim 中 UR5 场景配置 | FAIL | P4_FORMAT | UR5 → franka.py 内容错配（isaac 兜底固定 franka） |
| ss_kinova_003 | Kinova 协作臂 URDF | FAIL | P4_FORMAT | 命中真实 URDF 但 9 个 STL 未落盘，解析失败 |
| ss_mesh_ycb_008 | YCB 钳子（pliers）mesh | FAIL | P4_FORMAT | ycb 60s 超时→咖啡机 mesh，语义错配且 0 issue 掩盖 |
| ss_mujoco_006 | MuJoCo 中 Franka 抓取场景配置 | PASS_WITH_FALLBACK | — | mujoco 90s 超时→franka.py（内容正确）；场景缺物体 |
| ss_policy_hf_001 | HF 抓取策略权重 | FAIL | P2_RETRIEVE | hf-mirror 命中真实仓库 config.json（126B），权重 bin 未获取 |
| ss_sensor_github_002 | GitHub 关节位置/速度传感器日志 | FAIL | P2_RETRIEVE | zenodo 降级产出 68B 占位 json（缺 signals 键），数据全缺失 |

## 3. 问题聚类（8 处 FAIL 根因）

### 3.1 内容错配 / 语义错配（P4，4 例）
- ss_isaac_003：UR5 → franka.py；ms_009：sim_config → Cassie；ss_google_scanned_006：sim_config → ant.py；ss_mesh_ycb_008：pliers → 咖啡机
- 根因：**isaac 适配器无目标资产时兜底固定返回默认资产（franka.py/ant.py），降级产物无目标语义过滤**。ms_009 的 mujoco 场景检索同样因无 Kinova 场景随意命中 Cassie。

### 3.2 URDF 外部网格依赖缺失（P4/P6，2 例）
- ms_009、ss_kinova_003：URDF 本体真实，但 8~9 个 STL 网格未随包落盘 → 解析失败
- 根因：**github URDF 源只取 URDF 不收集 mesh 依赖**，validate 报 error 但包仍 complete/0 missing。

### 3.3 源级检索超时 / 源不稳定（P2/P3，4 例）
- ss_dexgrasp_006（3 轮 30s）、ss_mesh_ycb_008（60s）、ss_mujoco_006（90s，同目标一轮 62s 成功）、ms_014（HF 连接超时）
- 根因：**源级超时无快速失败、重试 3 轮全挂后才降级**；mujoco 源稳定性波动（同目标结果不可复现）。

### 3.4 降级产物"有文件无内容"（P2/P4，3 例）
- ss_policy_hf_001（126B config 无权重）、ss_sensor_github_002（68B 占位 json）、ms_014（126B README 摘要）
- 根因：**降级链路无内容有效性把关**，占位/文档被当交付物，且 0 error 通过校验。

### 3.5 配置缺失静默降级（P3，1 例）
- ss_ieee_002：IEEE API Key 未配置，无提示直接降级 arXiv（内容类型偏离用户指定源）。

### 3.6 校验体系盲区（横切）
- ss_mesh_ycb_008：语义错配 0 validation issue；ss_sensor_github_002：占位元数据 0 error 通过
- 结论：**校验只查格式/文件存在性，对"文件存在但内容不可用/不匹配"无感知**，清单层面 0 missing 与内容真实可用性严重脱节。

### 3.7 前端展示一致性（横切）
- 多题侧栏"fallback 否"与 manifest `is_fallback=true` 不一致（ss_arxiv_006、ss_isaac_003、ss_policy_hf_001、ss_sensor_github_002）。

## 4. 异常情况记录

| 现象 | 影响 | 说明 |
|---|---|---|
| huggingface.co 不可达（信号灯超时） | ms_014/ss_policy_hf_001 权重检索失败 | 网络环境因素；hf-mirror 镜像可部分缓解 |
| IEEE API Key 缺失 | ss_ieee_002 降级 | 环境配置因素 |
| 截图工具 IDE 命令超时 | 部分题截图落盘失败 | 浏览器会话保持、页面状态不受影响；按 plan 5.3 兜底 DOM 断言 |
| UI"fallback 否"与 manifest 矛盾 | 判定依据以 manifest 为准 | 前端状态展示缺陷，多题复现 |

## 5. 初步分析与修复方向（供组长 B 聚类参考）

1. **isaac 兜底语义化**：无目标资产时拒绝交付或返回明确错误，禁止固定返回 franka.py/ant.py（对应 3.1）。
2. **URDF 依赖收集**：github URDF 源解析 `<mesh filename>` 并收集落盘，validate 失败时应置包 status=partial/failed（对应 3.2）。
3. **快速失败**：源级超时 1 轮即停并转降级/报错，不等满 3 轮（对应 3.3）。
4. **降级内容把关**：对 policy_model/sensor_data 等类型校验产出文件大小与格式白名单（safetensors/bin/CSV），拒绝占位交付（对应 3.4）。
5. **语义匹配校验**：mesh/sim_config/robot_urdf 增加目标关键词匹配检查，错配记 error（对应 3.6）。
6. **前端 fallback 标志**：以 manifest is_fallback 为准统一展示（对应 3.7）。
7. **sensor_data 解析链路**：JSON dict 缺 signals 键时做格式校验错误而非占位交付。

## 6. 交付物清单

- 12 份 `records/<case_id>/record.json`（含 observations/verdict/failure 字段，FAIL 已填 failure_category + failure_reason）
- 截图按二轮 SOP 3 张/题（系统资源管理器 + 前端 explorer + provenance 长截图），由执行人本地归档至 `records/<case_id>/screenshots/`
