# E 工程师 14 题测试总结报告

> 统计范围：E 负责的 14 个测试 case  
> 数据来源：各 case 的 `records/<case_id>/record.json`  
> 复核人：F  
> 测试结论：14 题中，8 题 `PASS_WITH_FALLBACK`，6 题 `FAIL`，0 题纯 `PASS`

## 一、总体结果

| 结果 | 数量 | 占比 |
|---|---:|---:|
| PASS | 0 | 0% |
| PASS_WITH_FALLBACK | 8 | 57.1% |
| FAIL | 6 | 42.9% |
| 合计 | 14 | 100% |

本轮测试可以说明：系统主流程大多数情况下能够完成“目标解析 → 数据检索 → 解析转换 → 质量校验 → 整合打包”，但真实数据源命中质量仍不稳定，主要问题集中在数据源偏移、检索不足、格式不合格三类。

## 二、逐题结果汇总

| case_id | 轮次 | 目标 | 结论 | 主要说明 |
|---|---|---|---|---|
| ms_004 | 一轮 | UR5 with Robotiq 2F-85 grasps YCB apple | FAIL / P3_SOURCE | 包完整，但 mesh 实际为 coffeemaker，不是 YCB apple |
| ms_007 | 一轮 | 抓取 YCB 香蕉（未指定仿真器） | PASS_WITH_FALLBACK | mesh 成功，grasp 走 GraspNet 元数据降级 |
| ms_010 | 二轮 | 用 Franka Panda 抓取 YCB 马克杯（无仿真器指定） | PASS_WITH_FALLBACK | URDF、mesh、grasp 均有产物，但多项为 fallback |
| ms_015 | 二轮 | 结合 Zenodo 传感器数据与 GitHub 代码做机械臂力控 | PASS_WITH_FALLBACK | 满足最小文件数，但 Zenodo 传感器数据为轻量 fallback |
| ss_arxiv_007 | 二轮 | 检索 robot learning manipulation 领域的 arXiv 最新论文 2 篇 | FAIL / P2_RETRIEVE | 只落盘 1 篇 metadata，未满足 2 篇要求 |
| ss_dataset_hf_002 | 二轮 | Find a robot manipulation dataset with action labels on Hugging Face | FAIL / P3_SOURCE | 实际命中 Zenodo eclipse soundscapes，来源和主题均错误 |
| ss_franka_004 | 二轮 | 帮我找 Franka Panda 的 URDF，并确认末端抓爪型号 | PASS_WITH_FALLBACK | URDF 和 mesh 完整，末端抓爪可确认，但来源为镜像 |
| ss_ieee_003 | 二轮 | 检索机器人灵巧操作的 IEEE 综述论文 | PASS_WITH_FALLBACK | IEEE 未直接命中，走 OpenAlex 元数据兜底 |
| ss_isaac_004 | 二轮 | 我要在 Isaac Sim 里搭抓取环境，帮我找场景配置 | PASS_WITH_FALLBACK | 找到 IsaacLab 配置，但不是完整抓取场景 |
| ss_kinova_004 | 二轮 | 获取 Kinova Gen3 的 URDF 并与 Franka Panda 对比关节数 | PASS_WITH_FALLBACK | URDF 成功，关节数可比对，但 mesh 依赖未完整下载 |
| ss_mujoco_007 | 二轮 | 获取 MuJoCo 中 UR5 机械臂搭配物体抓取的任务场景配置 | FAIL / P3_SOURCE | 实际返回 IsaacLab Ant 配置，不是 MuJoCo UR5 抓取场景 |
| ss_policy_github_001 | 二轮 | Find a GitHub repo releasing a learned manipulation policy checkpoint | FAIL / P2_RETRIEVE | 只有 README/接口元数据，缺少 checkpoint 权重 |
| ss_sensor_zenodo_001 | 二轮 | 帮我找 Zenodo 上的 IMU 传感器数据 | FAIL / P4_FORMAT | JSON 缺少 signals、时间戳、单位等传感器核心字段 |
| ss_ycb_006 | 二轮 | 获取 YCB 数据集中的瓶子（bottle）mesh 模型 | PASS_WITH_FALLBACK | 成功生成 STL，但来源为 Gazebo Fuel/GoogleResearch，不是 YCB 官方源 |

## 三、主要问题分类

### 1. 数据源偏移 P3_SOURCE

典型 case：

- `ms_004`：目标是 YCB apple，实际 mesh 是 coffeemaker。
- `ss_dataset_hf_002`：目标是 Hugging Face 机器人数据集，实际命中 Zenodo 日食声音数据。
- `ss_mujoco_007`：目标是 MuJoCo UR5 抓取场景，实际是 IsaacLab Ant 配置。

说明当前系统能检索到“看起来像数据”的内容，但对数据源、对象名称、任务语义的校验仍不够严格。

### 2. 检索不足 P2_RETRIEVE

典型 case：

- `ss_arxiv_007`：要求最新论文 2 篇，实际只有 1 条 metadata。
- `ss_policy_github_001`：要求 policy checkpoint，但没有权重文件或下载链接。

说明系统需要进一步强化数量约束、文件类型约束和 checkpoint 证据检查。

### 3. 格式不合格 P4_FORMAT

典型 case：

- `ss_sensor_zenodo_001`：虽然落盘 JSON，但缺少 `signals` 字段，不能算可用 IMU 数据。

说明“有文件”不等于“格式可用”，传感器类数据需要检查字段结构。

## 四、有效能力表现

本次测试中，系统在以下方面表现较稳定：

- 能够完成基础流程并生成 `manifest.json`、`provenance.log`、数据包目录。
- 能够对 URDF、STL、JSON、Python 配置等多种格式进行落盘。
- fallback 机制有效，能在官方源不可用时给出替代来源。
- 前端和记录流程可以支撑人工复核，便于定位失败原因。

表现较好的 case：

- `ss_franka_004`：URDF 完整，末端抓爪型号可确认。
- `ss_kinova_004`：URDF 可用，关节数对比明确。
- `ss_ycb_006`：STL mesh 成功生成，包质量完整。
- `ms_010`：多源端到端流程可跑通，虽然依赖 fallback。

## 五、风险与改进建议

1. 增加目标语义校验  
   对 object name、source、task type 做强校验，避免 apple 变 coffeemaker、MuJoCo 变 Isaac。

2. 增加关键字段校验  
   对 sensor 数据要求 `signals`、timestamp、units；对 policy 要求 checkpoint 文件或权重链接；对 paper 要求数量和 PDF/metadata 约束。

3. fallback 需要更清晰标注  
   当前大量 case 依赖 fallback。建议在前端和 `manifest.json` 中明确显示 fallback 原因、原始目标源、实际命中源。

4. 区分“包完整”和“任务达标”  
   很多 FAIL case 的 package 状态仍是 `complete`，但人工复核发现不达标。后续应把验收规则前置到质量校验阶段。

5. 截图证据仍需补齐  
   多数 record 中已登记截图路径，但实际图片仍需要按 SOP 补入，尤其是失败 case 的错误截图。

## 六、结论

E 负责的 14 个测试覆盖了端到端任务、论文检索、数据集检索、机器人 URDF、仿真配置、策略模型、传感器数据和 mesh 模型等类型。

整体来看，系统已经具备基础流程执行和数据包生成能力，但真实可用性仍依赖人工复核。当前最关键的短板不是“跑不起来”，而是“跑出来的东西是否真符合题目”。后续优化重点应放在数据源语义一致性、关键字段完整性和 fallback 可解释性上。