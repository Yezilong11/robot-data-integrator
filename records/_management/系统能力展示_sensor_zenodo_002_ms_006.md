# 系统能力展示材料 — ss_sensor_zenodo_002 与 ms_006

> 用途：系统能力展示案例
> 判定口径：真实前端 API 全链路重放（LLM 为阿里云 MaaS qwen3.7-plus，全程真实调用，非降级）；
> 引用交付 = 大文件给 URL + 指引计完整交付（用户 2026-08-23 决策）
> 展示版本：2026-08-24（传感器修复轮 fix4c 收官后）

---

## 一、两道题展示定位

| 维度 | 🥇 ss_sensor_zenodo_002 | ms_006 |
| --- | --- | --- |
| 展示点 | 语义理解 + 跨源检索 + 真实验证 | 多源调度 + 缺失语义补全 + 可运行装配 |
| 类型 | sensor（Zenodo，英文题） | end_to_end 多源（Franka + YCB + MuJoCo，中文题） |
| 语言 | 英文 | 中文 |
| 结论 | **PASS**，0 缺失，0 ERROR | **PASS**，90 文件真实落盘 |

两道题互补：一题展示"找到正确数据"，一题展示"组装出可运行方案"。

---

## 二、🥇 ss_sensor_zenodo_002 — Find a force-torque sensor dataset for a robotic gripper on Zenodo

### 1. 成绩

| 指标 | 数据 |
| --- | --- |
| 判定 | **PASS** |
| 耗时 | 122.5 秒（7 题统一重放基准） |
| file_count | 2（1 数据文件 + 1 质量说明） |
| missing_count | **0** |
| validation_errors | **0** |
| 交付 | Zenodo 11096791 真实力/力矩时序 CSV（wrench），350,192 B 真实落盘 + SHA-256 校验 |

### 2. 修复故事（本题是本次传感器链路修复的核心实证）

**修复前（历史 FAIL）**：
- 检索期预筛把 RBO 数据集（记录 1036660，RGB-D 视频序列，与力觉无关）评成 2 分，
  盖过真实力觉记录——因为其 keywords 含 "Force-torque measurements"、"Robotics"，
  旧匹配规则对 ≥2 词短语逐词命中即算命中，"force torque sensor"（缺 sensor）、
  "robotic gripper"（缺 gripper）双双被误放行。
- 结果：装配期语义校验如实拦截（失败包 package-20260824-065559，missing 原因原文：
  *"内容与需求语义不符（需求目标: force torque sensor、robotic gripper、力/力矩传感器、
  时序数据，实际: 1036660）"*）。校验层行为正确，错在检索期选错。

**修复（fix4c）**：
- 匹配规则收紧：≥3 实义词短语要求**全部词命中**才判命中。
- 修复后 RBO 1036660 关联分降为仅 "robotic gripper" 单短语命中（1 分），
  真实 F/T 记录 11096791 排到前面并被选中。

**修复后（PASS）**：选中并下载 **Zenodo 11096791**（`2-vibrations_wrench.csv`，
真实 wrench 数据），PASS。7 题传感器重放 7/7 全 PASS（增至 39/48 总成绩）。

### 3. 交付明细（修复后包 package-20260824-072831，status=complete）

| 文件 | 格式 | 来源 | 大小 | 状态 |
| --- | --- | --- | --- | --- |
| resources/req_000.json | SensorDataset | `zenodo.org/records/11096791 ... 2-vibrations_wrench.csv` | 350,192 B | 真实下载，SHA-256 `63a93210…401c50` |
| quality_explanation.md | md | LLM 生成 | 823 B | 质量解释 |

- quality_report：confidence **1.0**、completeness **100%**、validation_issues **0**
- missing_items：**无**
- assemble_completeness_check：PASS

### 4. 能力亮点

1. **语义理解 → 精准命中**：英文自然语言需求分解为力/力矩传感器 + 机械手 + 时序数据目标；
2. **抗干扰检索**：从含 "Force-torque measurements" 关键词的无关记录中识别语义不符（fix4c 全词命中规则）；
3. **可信交付**：真实 CSV 落盘 + checksum 校验 + 装配完整性检查，0 缺失 0 ERROR。

---

## 三、ms_006 — 用 Franka 在 MuJoCo 里抓取香蕉（无 YCB 关键词）

### 1. 成绩

| 指标 | 数据 |
| --- | --- |
| 判定 | **PASS**（引用交付口径，计完整交付） |
| file_count | 91（**90 个文件真实落盘** + 1 项大文件引用交付） |
| missing_count | 1（grasp 标注大文件，已给 URL + wget 指引） |
| 需求拆分 | 4 类：robot_urdf / object mesh / grasp / sim_config 全部覆盖 |
| **运行时验证** | `runtime_check: MuJoCo 加载与一步仿真成功` |
| 装配质量 | avg_confidence **0.958**、completeness **95.8%**、全部文件含 SHA-256 |

### 2. 为什么选这题（核心卖点：**提问里没有 "YCB" 三个字**）

题目只写"抓取香蕉 + MuJoCo + Franka"，系统仍推断出：
- 需要 Franka Panda 完整 URDF + 全部链接 mesh；
- 抓取对象香蕉来自 **YCB 数据集**（自动补全缺失语义）；
- 需要可加载的 MuJoCo 场景配置。

→ 体现"需求补全与多源编排"能力，而不只是查询命中。

### 3. 交付明细（包 package-20260823-195407）

**跨 3 个真实源调度 90 个文件：**

| 源 | 内容 | 文件示例 |
| --- | --- | --- |
| GitHub `pybullet_robots` | Franka Panda URDF + 全链接 visual/collision mesh（obj） | robots/req_000.urdf、robots/meshes/*.obj（con 1MB+ 真实网格） |
| HF 镜像 `ll4ma-lab/ycb-fixed-meshes` | YCB 香蕉物体网格 | objects/req_001.stl（819,284 B） |
| GitHub `google-deepmind/mujoco_menagerie` | 官方 Franka scene.xml + 全套 assets | sim_config/scene 相关 xml/obj/stl（几十个） |

**组装结果**：按需求归类为 `robots/`、`objects/`、`sim_config/` 目录；
**可运行验证**：MuJoCo 实际加载场景并完成一步仿真（`runtime_check passed`）。

### 4. 能力亮点

1. **缺失语义补全**：无 YCB 关键词 → 自动推断 YCB 香蕉模型；
2. **多源调度**：一次请求顺序/并发协调 GitHub、HF 镜像、MuJoCo 官方仓 3 个源；
3. **按需装配**：90 个异构文件按需求结构落盘，附 checksum 与 provenance 日志；
4. **真实验证**：不止"给文件"，实际跑通 MuJoCo 一步仿真验证可用性。

---

## 四、展示注意事项

1. **引用交付口径**：ms_006 的 1 项（grasp 标注大文件约 30MB+）为引用交付（URL + wget 指引），
   按既定口径计 PASS；对观众建议如实一句话说明，避免被质疑"没下载完"。
2. **数据来源正版**：均为公开数据集官方源（pybullet_robots / mujoco_menagerie /
   Zenodo 11096791 / YCB-fixed-meshes）。
3. **可复现**：两题均可用 `scripts/replay_frontend_problem_set.py --only <case_id>` 真实重放
   （需按 README 启动 rdi.server）。

---

## 附：证据文件索引

- ss_sensor_zenodo_002 修复后包：`data/output_packages/package-20260824-072831/manifest.json`
- ss_sensor_zenodo_002 修复前失败包（铁证）：`data/output_packages/package-20260824-065559/manifest.json`
- ms_006 交付包：`data/output_packages/package-20260823-195407/manifest.json`
- 7 题统一重放明细：`records/_management/replay_frontend_20260824-071216.json`
- 48 题重判表：`records/_management/replay_frontend_refcounted.json`
- 修复说明：`records/_management/三轮测试总结报告.md`（第七节 fix4c）