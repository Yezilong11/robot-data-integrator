# 测试任务分配表

> 来源：`records/_management/assignments.csv`，共 **122 题**（一轮 + 二轮）。
> 执行人：A / C / D / E / F；复核：除 F 自执外统一 F（F 自执由 A 复核）。

## A（15 题：一轮 3 + 二轮 12）

| case_id | 轮次 | 目标 | 复核 |
|---|---|---|---|
| ms_001 | 一轮 | Franka Panda grasps YCB banana in MuJoCo | F |
| ms_002 | 一轮 | 我想在 MuJoCo 里用 Franka Panda 机器人抓取 YCB 香蕉 | F |
| ms_006 | 一轮 | 用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词） | F |
| ms_012 | 二轮 | UR5 with Robotiq 2F-85 grasps a Google Scanned object | F |
| ss_allegro_005 | 二轮 | 我要在仿真里用 Allegro 手抓物体，帮我找它的 URDF 模型 | F |
| ss_code_github_001 | 二轮 | 获取一个 GitHub 上用于机械臂运动学求解的 Python 仓库代码 | F |
| ss_github_006 | 二轮 | 帮我找一个机械臂控制的 GitHub 开源项目（中文描述） | F |
| ss_google_scanned_004 | 二轮 | 获取 Google Scanned Objects 中的椅子（chair）mesh 模型 | F |
| ss_grasp_dexgrasp_002 | 二轮 | 获取 DexGraspNet 中 bowl 的抓取文件（中文） | F |
| ss_graspnet_003 | 二轮 | 获取 GraspNet-1Billion 中物体 camera_0 的抓取数据 | F |
| ss_kinova_001 | 二轮 | 获取 Kinova Gen3 机械臂的 URDF 模型 | F |
| ss_mujoco_009 | 二轮 | 获取一个不含机械臂、只有物体的 MuJoCo 仿真场景 | F |
| ss_robotiq_004 | 二轮 | 获取 Robotiq 2F-85 夹爪 URDF 用于 MoveIt 规划 | F |
| ss_urdf_github_001 | 二轮 | 检索 GitHub 上的 UR5 机械臂 URDF 模型 | F |
| ss_zenodo_007 | 二轮 | Find a robotic arm joint sensor dataset on Zenodo | F |

## C（46 题：一轮 34 + 二轮 12）

| case_id | 轮次 | 目标 | 复核 |
|---|---|---|---|
| ms_005 | 一轮 | Franka Panda stacks YCB blocks in PyBullet | F |
| ms_013 | 二轮 | 用 Franka Panda 在 MuJoCo 里执行抓取，并加载一个策略模型权重 | F |
| ss_allegro_006 | 二轮 | Allegro hand URDF with 4-finger tactile layout | F |
| ss_arxiv_001 | 一轮 | 检索 robot grasping 的论文 | F |
| ss_arxiv_002 | 一轮 | 检索 dexterous manipulation 灵巧操作的论文 | F |
| ss_arxiv_003 | 一轮 | 检索 robot grasping 仿真的论文 | F |
| ss_arxiv_004 | 一轮 | 检索机器人触觉感知抓取论文 | F |
| ss_arxiv_005 | 一轮 | 检索 robot grasping 综述论文 | F |
| ss_code_hf_001 | 二轮 | Find a Hugging Face Space/Repo with robot grasping inference code | F |
| ss_dexgrasp_001 | 一轮 | 获取 banana 的 DexGrasp 抓取文件 | F |
| ss_dexgrasp_002 | 一轮 | 获取 apple 的 DexGrasp 抓取文件 | F |
| ss_dexgrasp_003 | 一轮 | 获取 mug 的 DexGrasp 抓取文件 | F |
| ss_dexgrasp_004 | 一轮 | 获取 bottle 的 DexGrasp 抓取文件 | F |
| ss_dexgrasp_005 | 一轮 | 获取 scissors 的 DexGrasp 抓取文件 | F |
| ss_github_001 | 一轮 | 检索 Franka 抓取开源仓库 | F |
| ss_github_002 | 一轮 | 检索 GitHub 上的 Franka Panda URDF 模型 | F |
| ss_github_003 | 一轮 | 检索 YCB 抓取数据集 | F |
| ss_github_004 | 一轮 | 检索抓取策略权重仓库 | F |
| ss_github_005 | 一轮 | 检索机械臂关节数据集 | F |
| ss_google_scanned_005 | 二轮 | 获取 Google Scanned Objects 中一个杯子的 mesh 模型用于仿真 | F |
| ss_graspnet_001 | 一轮 | 检索 GraspNet 数据集 | F |
| ss_graspnet_002 | 一轮 | 获取 banana 的单个 grasp 文件 | F |
| ss_graspnet_004 | 二轮 | 我要做抓取规划，帮我找 GraspNet 数据集的抓取标签 | F |
| ss_graspnet_005 | 二轮 | 获取 GraspNet-1Billion 数据集的说明和目录结构 | F |
| ss_huggingface_001 | 一轮 | 检索 robot grasp dataset | F |
| ss_huggingface_002 | 一轮 | 检索 ACT 机器人操作策略 | F |
| ss_huggingface_003 | 一轮 | 检索机器人操作代码仓库 | F |
| ss_huggingface_004 | 一轮 | 检索 robot manipulation 数据集 | F |
| ss_huggingface_005 | 一轮 | 检索灵巧操作策略权重 | F |
| ss_ieee_001 | 一轮 | 检索 robot grasping 的论文 | F |
| ss_kinova_002 | 二轮 | 获取 Kinova Gen3 Lite 机械臂 URDF，并确认其自由度 | F |
| ss_mesh_gso_001 | 二轮 | 获取 Google Scanned Objects 中一个香蕉 mesh 模型（中文） | F |
| ss_paperswithcode_001 | 一轮 | 检索 grasp detection 相关论文 | F |
| ss_paperswithcode_002 | 一轮 | 检索 grasp detection 论文及其代码 | F |
| ss_paperswithcode_003 | 一轮 | 检索机器人抓取论文 | F |
| ss_robotiq_005 | 二轮 | 帮我获取 Robotiq 2F-85 夹爪模型文件并转换为 URDF | F |
| ss_sensor_github_001 | 二轮 | 帮我找 GitHub 上的机械臂关节力矩传感器数据 | F |
| ss_urdf_kinova_005 | 二轮 | Find a Kinova Gen3 URDF with gripper for ROS | F |
| ss_ycb_004 | 一轮 | 获取 banana 的 grasp 数据 | F |
| ss_ycb_005 | 一轮 | 获取 mug 的 grasp 数据 | F |
| ss_zenodo_001 | 一轮 | 检索 robot grasp dataset | F |
| ss_zenodo_002 | 一轮 | 检索机械臂关节数据 | F |
| ss_zenodo_003 | 一轮 | 检索机器人操作仿真数据集 | F |
| ss_zenodo_004 | 一轮 | 检索机械臂力觉传感器数据 | F |
| ss_zenodo_005 | 一轮 | 检索抓取姿态标注数据集 | F |
| ss_zenodo_006 | 二轮 | 帮我找 Zenodo 上机器人抓取数据集（中文描述） | F |

## D（35 题：一轮 23 + 二轮 12）

| case_id | 轮次 | 目标 | 复核 |
|---|---|---|---|
| ms_003 | 一轮 | Kinova Gen3 picks up EGAD mug in Isaac Sim | F |
| ms_009 | 二轮 | Kinova Gen3 grasps YCB bottle in MuJoCo | F |
| ms_014 | 二轮 | 找一个机械臂抓取策略的开源代码并加载其 Hugging Face 权重 | F |
| ss_allegro_001 | 一轮 | 获取 Allegro Hand 灵巧手的 URDF 模型 | F |
| ss_allegro_002 | 一轮 | 获取 Allegro Hand 的 URDF，需要包含 4 指 16 关节定义 | F |
| ss_allegro_003 | 一轮 | 灵巧手做抓取，帮我找 Allegro 手的模型文件 | F |
| ss_arxiv_006 | 二轮 | 检索机器人抓取的 arXiv 论文（中文描述） | F |
| ss_dexgrasp_006 | 二轮 | 帮我找 DexGraspNet 数据集的抓取标注（中文描述） | F |
| ss_franka_001 | 一轮 | 获取 Franka Panda 机器人的 URDF 模型 | F |
| ss_franka_002 | 一轮 | 我需要 Franka Panda 的完整 URDF 模型，包含碰撞网格与视觉网格 | F |
| ss_franka_003 | 一轮 | 我要用 Franka Panda 做抓取仿真，先把它的模型文件给我 | F |
| ss_google_scanned_001 | 一轮 | 获取 Google Scanned Objects 数据集中的任意一个物体 mesh 模型 | F |
| ss_google_scanned_002 | 一轮 | 获取 Google Scanned Objects 中的水壶（kettle）mesh 模型 | F |
| ss_google_scanned_003 | 一轮 | 获取 Google Scanned Objects 中大体积物体的 mesh（验证下载超时/失败降级路径） | F |
| ss_google_scanned_006 | 二轮 | Retrieve any object mesh from Google Scanned Objects for MuJoCo tabletop | F |
| ss_ieee_002 | 二轮 | 检索机械臂抓取相关的 IEEE 论文 | F |
| ss_isaac_001 | 一轮 | 获取 Isaac Sim 中 Franka Panda 的仿真场景配置（允许最小 MJCF fallback） | F |
| ss_isaac_002 | 一轮 | 获取 Isaac Sim 场景配置（验证无真实场景时的失败可追溯性） | F |
| ss_isaac_003 | 二轮 | 获取 Isaac Sim 中 UR5 的仿真场景配置 | F |
| ss_kinova_003 | 二轮 | 帮我找 Kinova 协作机械臂的 URDF 文件 | F |
| ss_mesh_ycb_008 | 二轮 | 获取 YCB 数据集中钳子（pliers）的 mesh 模型 | F |
| ss_mujoco_001 | 一轮 | 获取 mujoco_menagerie 中 Franka Panda 的 MuJoCo 场景配置 | F |
| ss_mujoco_002 | 一轮 | 获取 mujoco_menagerie 中 Franka Panda 的抓取操作场景配置 | F |
| ss_mujoco_003 | 一轮 | 获取 mujoco_menagerie 中 UR5e 机器人的 MuJoCo 场景配置 | F |
| ss_mujoco_004 | 一轮 | 获取 mujoco_menagerie 中的厨房（Kitchen）场景配置 | F |
| ss_mujoco_005 | 一轮 | 我要在 MuJoCo 里搭 Franka 的仿真环境，帮我找场景配置文件 | F |
| ss_mujoco_006 | 二轮 | 我要在 MuJoCo 里搭建 Franka 抓取场景，帮我找场景配置 | F |
| ss_policy_hf_001 | 二轮 | 获取一个 Hugging Face 上的机械臂抓取策略模型权重 | F |
| ss_robotiq_001 | 一轮 | 获取 Robotiq 2F-85 夹爪的 URDF 模型 | F |
| ss_robotiq_002 | 一轮 | 获取 Robotiq 2F-85 夹爪 URDF，并确认其手指开合参数 | F |
| ss_robotiq_003 | 一轮 | 抓取实验要装 Robotiq 夹爪，我需要它的模型 | F |
| ss_sensor_github_002 | 二轮 | Find joint position/velocity sensor log data on GitHub | F |
| ss_ycb_001 | 一轮 | 获取 YCB 数据集中的香蕉（banana）mesh 模型 | F |
| ss_ycb_002 | 一轮 | 获取 YCB 数据集中的苹果（apple）mesh 模型 | F |
| ss_ycb_003 | 一轮 | 获取 YCB 数据集中的马克杯（mug）mesh 模型 | F |

## E（14 题：一轮 2 + 二轮 12）

| case_id | 轮次 | 目标 | 复核 |
|---|---|---|---|
| ms_004 | 一轮 | UR5 with Robotiq 2F-85 grasps YCB apple | F |
| ms_007 | 一轮 | 抓取 YCB 香蕉（未指定仿真器） | F |
| ms_010 | 二轮 | 用 Franka Panda 抓取 YCB 马克杯（无仿真器指定） | F |
| ms_015 | 二轮 | 结合 Zenodo 传感器数据与 GitHub 代码做机械臂力控 | F |
| ss_arxiv_007 | 二轮 | 检索 robot learning manipulation 领域的 arXiv 最新论文 2 篇 | F |
| ss_dataset_hf_002 | 二轮 | Find a robot manipulation dataset with action labels on Hugging Face | F |
| ss_franka_004 | 二轮 | 帮我找 Franka Panda 的 URDF，并确认末端抓爪型号 | F |
| ss_ieee_003 | 二轮 | 检索机器人灵巧操作的 IEEE 综述论文 | F |
| ss_isaac_004 | 二轮 | 我要在 Isaac Sim 里搭抓取环境，帮我找场景配置 | F |
| ss_kinova_004 | 二轮 | 获取 Kinova Gen3 的 URDF 并与 Franka Panda 对比关节数 | F |
| ss_mujoco_007 | 二轮 | 获取 MuJoCo 中 UR5 机械臂搭配物体抓取的任务场景配置 | F |
| ss_policy_github_001 | 二轮 | Find a GitHub repo releasing a learned manipulation policy checkpoint | F |
| ss_sensor_zenodo_001 | 二轮 | 帮我找 Zenodo 上的 IMU 传感器数据 | F |
| ss_ycb_006 | 二轮 | 获取 YCB 数据集中的瓶子（bottle）mesh 模型 | F |

## F（12 题：一轮 1 + 二轮 11）

| case_id | 轮次 | 目标 | 复核 |
|---|---|---|---|
| ms_008 | 一轮 | 只要 Franka Panda 的 URDF | A |
| ms_011 | 二轮 | Allegro dexterous hand manipulates YCB cup in Isaac Sim | A |
| ss_allegro_004 | 二轮 | 获取 Allegro 灵巧手的 URDF，并确认其 16 个关节是否齐全 | A |
| ss_dataset_graspnet_001 | 二轮 | 获取 GraspNet 数据集中某个物体的点云与标注（中文） | A |
| ss_franka_005 | 二轮 | Franka Panda URDF with 7-DOF joint limits | A |
| ss_grasp_ycb_001 | 二轮 | 获取 YCB 数据集中马克杯的抓取标注 | A |
| ss_huggingface_006 | 二轮 | 帮我找 Hugging Face 上的机器人操作数据集（中文描述） | A |
| ss_ieee_004 | 二轮 | IEEE papers on 6-DOF grasp pose estimation | A |
| ss_isaac_005 | 二轮 | Isaac Sim kitchen environment config for robot manipulation | A |
| ss_mujoco_008 | 二轮 | MuJoCo tabletop manipulation scene with a single object | A |
| ss_sensor_zenodo_002 | 二轮 | Find a force-torque sensor dataset for a robotic gripper on Zenodo | A |
| ss_ycb_007 | 二轮 | 获取 YCB 数据集中的香蕉 mesh 模型并确认是闭合流形 | A |
