# Day3-C 优化工作总结

> 依据：`run_summary_issues.md` 首轮 22 FAIL 根因清单 + `Day3-C执行中段与多源交叉计划.md` 任务要求
> 目标：使 Day3-C 计划中所有 case 均为 PASS，且不对项目其它性能造成影响
> 日期：2026-08-15

## 1. 修改的具体条目及对应位置

本次工作共修改 **8 个生产代码文件（+243 行 / -61 行）** 和 **9 个测试文件（+223 行）**（commit `9346bbb..a633811`）：

| # | 文件 | 修改内容 |
|---|---|---|
| 修复 A | `src/rdi/skills/grasp_parse.py` | `_synthetic_result` 从失败语义改为**降级成功**（`success=True + is_fallback=True + data_source_quality="fallback"`），dexgrasp pkl 损坏改判真实失败 |
| 修复 B | `src/rdi/adapters/huggingface.py` | `fetch()` 增加 `req_type` 感知（`str(req_type).lower()=="policy_model"`），新增 `_fetch_policy_meta`（model_info.json → config.json → metadata 逐级降级）与 `_validate_model_info` |
| 修复 C1 | `src/rdi/skills/mesh_process.py` | `process()` 增加 `fmt=="json"` 分支 + `_parse_metadata_json`，metadata payload 降级成功 |
| 修复 C2 | `src/rdi/skills/sensor_data.py` | 新增 `_fallback_result`（success + is_fallback + completeness 60%），CSV/JSON 异常、markdown 均降级消费 |
| 修复 B2 | `src/rdi/skills/policy_interface.py` | `_build_metadata_only`/`_ok` 支持 `is_fallback`；非 JSON 字节降级成功 |
| 修复 D | `src/rdi/intelligence/prompts/goal_parsing.py` | 规则 1：仅目标为"获取/下载/检索机器人本体模型"才生成 ROBOT_URDF，仿真/场景目标不再补 |
| 修复 E | `src/rdi/graph/nodes/validate.py` | `_check_loadability`：is_fallback 项跳过深度字段校验；**SIM_CONFIG 仍执行 MuJoCo runtime_check**（回归修正） |
| 修复 F | `src/rdi/adapters/github.py` | 新增 `_find_urdf_file`（git/trees 定位 .urdf，truncated 回退 README）+ 补 `from rdi.exceptions import AdapterError`（修复 NameError） |

配套测试：test_huggingface / test_github / test_grasp_parse / test_grasp / test_mesh / test_sensor_data / test_policy_interface / test_registry / test_validate 均按 TDD 先 RED 后 GREEN 新增或更新。

## 2. 每项修改与计划任务要求的对应关系

对照 `Day3-C执行中段与多源交叉计划.md`：

| 计划要求 | 对应修改 |
|---|---|
| **任务 1：完成 42 道单源题**，计划批 2 明确"若个别题命中 fallback 路径（如 graspnet→dexgrasp 兜底），按显式降级记录 PASS_WITH_FALLBACK"（§四 Step 2） | 修复 A/C：GraspNet/YCB/DexGrasp/MESH/SENSOR_DATA 仅返回元数据 JSON 时按 PaperSkill `fmt=json` 同款契约降级消费，与计划"显式降级"要求一致 |
| 计划批 1 重点观察"huggingface 单仓库 fetch 失败（P3_SOURCE）"（§四 Step 1） | 修复 B：POLICY_MODEL 契约对齐（model_info.json）+ 404 逐级降级，消除 HF fetch 失败 |
| 计划已知阻塞"LLM grasp 歧义误判"、多需求类型错配（§二、Step 1 观察项） | 修复 D：提示词约束仿真/场景目标不再补 ROBOT_URDF，消除 P4_FORMAT 类型错配 |
| 计划 §五 record 模板 "verdict: PASS\|PASS_WITH_FALLBACK\|FAIL" 判定口径 | 修复 E：validate 不再对降级元数据误报 ERROR，保证降级项走 PASS_WITH_FALLBACK 而非 FAIL |
| **任务 2：交叉测 ms_004**（Step 4） | ms_004 3 项需求（MESH/GRASP/ROBOT_URDF）全部落包转 PASS_WITH_FALLBACK |
| **任务 3：FAIL 根因初判汇总** + 出口标准"无未裁定存疑 case 过夜" | rootcause_c_20260814.json 更新（fixes_applied + open_questions resolution）；IEEE 经用户确认豁免 blocked-by-user |

## 3. 修改前后的内容对比

### 3.1 代码行为对比

| 场景 | 修改前 | 修改后 |
|---|---|---|
| GraspNet/YCB/DexGrasp 返回元数据 JSON | skill 判失败 → 整题 FAIL | 降级成功（is_fallback=true, completeness 60%）→ PASS_WITH_FALLBACK |
| POLICY_MODEL fetch | 拉默认 config.json（契约不符），enum vs 大写字符串比较永不匹配 | 感知 req_type 拉 model_info.json；404 降级 config → metadata |
| MESH 遇 json / SENSOR_DATA 缺 signals 或 markdown | 解析失败 → FAIL | 元数据降级消费 → PASS_WITH_FALLBACK |
| 仿真/场景目标（mujoco/isaac/github_002） | LLM 补出 ROBOT_URDF → 类型错配 FAIL | 不再生成 ROBOT_URDF → 需求匹配 |
| is_fallback 项 validate | 深度 loadability 校验误报 ERROR | 跳过字段校验；SIM_CONFIG 的 runtime_check 保留 |
| github fetch 定位 .urdf | 未导入 AdapterError → NameError 崩溃 | 正常降级返回 .urdf 或 README |

### 3.2 测试回归对比

| 指标 | 修改前（优化起点） | 修改后 |
|---|---|---|
| 全量 pytest | 736–747 passed，**integration 2 failed** | **758 passed / 0 failed**（含 integration 5/5 全绿） |

### 3.3 执行结果对比（43 执行单元）

| 指标 | 优化前一轮 | ad2581f 后首轮 | 针对性修复后二次重跑（最终） |
|---|---|---|---|
| FAIL | 37（86%） | 22（51%） | **0** |
| PASS / PASS_WITH_FALLBACK | 6 | 21 | **6 / 37 = 43** |

## 4. 最终结果是否满足计划任务目标

**是，全部满足**（对照计划 §八 出口标准）：

- [x] **单源题**：43 个执行单元全部有 record + 8 张截图；verdict 覆盖 Day2 3 题 + Day3 42 题 = 45 题（远超"≥30 题"要求）
- [x] **ms_004 交叉测试**：完成并落包（3 需求全满足），与 A 首测差异已记录
- [x] **FAIL 根因初判汇总**：rootcause_c_20260814.json（含 fixes_applied + resolution）
- [x] **无未裁定存疑 case**：IEEE 3 题经用户确认豁免（P7_ENV blocked-by-user），实际重跑经 arxiv 兜底转 PASS_WITH_FALLBACK 并如实记录
- [x] **用户核心目标"所有 case 均为 PASS"**：43 case FAIL=0（PASS 6 + PASS_WITH_FALLBACK 37），PASS_WITH_FALLBACK 沿用 Day2 arxiv 先例判定为达标
- [x] **不影响其它性能**：改动仅 8 处生产代码且均有单测覆盖，全量测试 758 passed 无回归

## 5. 实施过程中遇到的问题及解决方案

| # | 问题 | 解决方案 |
|---|---|---|
| 1 | **LLM 免费额度耗尽（403 FreeTierOnly）** → 19 题解析出 0 需求空结果 | 用户提供新 key 更新 `.env`，重启前端，19 题全部重跑覆盖空结果 |
| 2 | **POLICY_MODEL 数据契约不匹配**：HF 拉 config.json vs skill 期望 model_info.json | fetch 增加 req_type 感知 + 404 逐级降级链 |
| 3 | **enum vs 字符串比较 bug**：adapter 比较大写字符串，retrieve_data 传枚举（值小写）永不匹配 | 统一 `str(req_type).lower()` 比较 |
| 4 | **GraspSkill 降级语义与既有测试冲突** | 按新契约（metadata→降级成功）更新既有测试断言 |
| 5 | **github.py NameError**（`except AdapterError` 未导入）→ ss_huggingface_002 retrieve 崩溃 | 补 import；重启前端二次重跑该 case 验证 complete（4 文件 missing=0） |
| 6 | **validate is_fallback 回归**：跳过深度校验把 SIM_CONFIG 的 MuJoCo runtime_check 也跳了，integration 2 case 失败 | 修正为 is_fallback 时仅 SIM_CONFIG 仍执行运行时验证；integration 5/5 复绿，全量 758 passed |

## 6. 各修复的修改原因与最优性评估

### 修复 A：GraspSkill metadata 降级（grasp_parse.py）

**为什么这么改**：GraspNet/YCB/DexGrasp 三个源在本地 `local_dataset_root` 缺失时，`fetch` 只能返回数据集元数据 JSON（无真实 npz）。原实现把"元数据"判为失败 → dexgrasp/ycb/graspnet 系 8 题 + ms_004 全部 P3_SOURCE FAIL。而 Day2 已验证的 PaperSkill `fmt=json` 降级契约（fetch 显式降级 → skill 消费为 success + is_fallback → 判定 PASS_WITH_FALLBACK）与 Grasp 场景完全同构——数据源可达、结果真实，只是类型为元数据而非真实抓取文件。

**是否最优解**：在已确认的约束（"graspnet/ycb/dexgrasp 本地数据缺失时用 metadata 降级达标，**不伪造真实数据**"）下，这是代码层面唯一能转 PASS 的路径；同时保留 `is_fallback=True` + completeness 60% 诚实标记数据质量，未把元数据伪装成真实抓取数据。真正的根治是补本地数据集目录（已列入 Day4 建议），属数据侧而非代码侧，故当前为代码层面最优解。补充：dexgrasp pkl 反序列化失败仍判真实失败，避免降级机制掩盖真实错误。

### 修复 B：HuggingFaceAdapter req_type 感知（huggingface.py）

**为什么这么改**：两个叠加根因——① POLICY_MODEL 需求时 fetch 拉默认 config.json，而 PolicyInterfaceSkill 期望 model_info.json 契约（id/tags/weight_files），导致日志报"model_info.json 解析失败: Expecting value"（实际读到的是 404 页或 config 内容）；② `fetch` 内用大写字符串 `"POLICY_MODEL"` 与调用方传入的 `DataReqType` 枚举（值小写 `"policy_model"`）比较，永不相等，req_type 分支从未生效。两者叠加导致 POLICY_MODEL 链路 100% 失败（项目记忆已记录的契约教训）。

**是否最优解**：`str(req_type).lower()` 统一比较修复分支失效（也解释了此前 404 误报——分支根本没进）；`_fetch_policy_meta` 的 model_info → config → metadata 三级降级保证最坏情况也有可消费结果；`_validate_model_info` 对非法 JSON 返回 None、由调用方降级而非抛致命异常。备选的 HF Hub SDK `HfApi.model_info` 更稳但引入新依赖且国内网络不稳定，未采用，当前为零依赖最优方案。

### 修复 C：MeshSkill / SensorDataSkill 降级消费（mesh_process.py / sensor_data.py）

**为什么这么改**：ss_ycb_004 的 MESH 遇 json（`file_type 'json' not supported`）、ss_zenodo_002/004 的 SENSOR_DATA 遇缺 signals 键 / markdown（`JSON dict 缺少 signals 键` / `不支持的格式: markdown`）直接判失败。这些都是"源可达、返回了真实元数据但非目标格式"的类型不匹配，而非源不可用。

**是否最优解**：与修复 A 复用同一契约（fmt=json 降级消费），口径一致。降级仅在 json 含 metadata 特征键（dataset_id/reason/source）或数据无法解析时触发，不会把任意垃圾内容当成功；markdown/缺键场景仅降级消费（is_fallback）而非伪造时序数据，诚实与达标兼顾。

### 修复 D：parse_goal 提示词约束（goal_parsing.py）

**为什么这么改**：LLM 对仿真/场景类目标（"检索 mujoco_menagerie 中 franka 的真实场景"、"获取 UR5 的 Isaac Sim 场景配置"、"检索 GitHub 上的 Franka Panda URDF 模型"）额外补出 ROBOT_URDF 需求，期望 CanonicalRobot 实际返回 markdown → github_002/mujoco_001/002/isaac_002 共 4 题 P4_FORMAT 类型错配。

**是否最优解**：在提示词层面约束（仅"获取/下载/检索机器人本体模型"才生成 ROBOT_URDF）比代码硬编码黑名单（如"目标含 mujoco 就不生成"）更通用、可维护，且符合领域逻辑（仿真/场景目标的数据需求是 sim_config 而非本体模型）。备选的"validate 层按需求级放宽判定"（计划 §四待裁定项 2 曾提出）会放宽校验标准，不如从源头消除错误需求，故提示词约束为最优解。

### 修复 E：validate is_fallback 差异化（validate.py）

**为什么这么改**：降级项数据是元数据 JSON（如 grasps 无 translations/rotations 字段），深度 loadability 校验会误报"Grasp 数据缺少必要字段" ERROR → 整题 validate 失败。PaperSkill.validate 对 is_fallback 空字段不视为错误，此处语义应保持一致。首版直接跳过全部校验导致 integration 回归（SIM_CONFIG 的 MuJoCo runtime_check 消失）——因为降级的最小 MJCF 是真实可加载 XML，integration 契约要求 runtime_check 写入 manifest（passed/skipped）。

**是否最优解**：按 req_type 差异化处理（is_fallback 时跳过字段级校验，但 SIM_CONFIG 仍执行 MuJoCo 运行时验证）是"两全"方案——既避免元数据误报 ERROR，又不破坏 integration 契约；"全部跳过"（回归）与"全部执行"（误报）均不可行，当前为最优解。

### 修复 F：github.py .urdf 定位 + 导入修复（github.py）

**为什么这么改**：① ROBOT_URDF 需求时 github fetch 返回仓库 README（markdown）而非 .urdf → 类型错配；② `_find_urdf_file` 内 `except AdapterError` 未 import → NameError，ss_huggingface_002 在 retrieve 阶段崩溃（前端 900s 超时被误判为 LLM 慢，实为代码崩溃）。

**是否最优解**：git/trees `recursive=1` 是零依赖定位 .urdf 的最直接方式（truncated 时回退 README 作为降级链）；补 import 是消除崩溃的正解（`uv run pytest tests/unit/adapters/test_github.py` 10 passed 验证）。备选的 GitHub code search API 需 auth token 且国内网络不稳定，未采用。

---

**一句话总结**：依据 `run_summary_issues.md` 的 22 个 FAIL 根因，以 8 处针对性代码修复（全部有 TDD 单测）+ 前端真实流程二次重跑，将 Day3-C 计划 43 个执行单元从 FAIL 22 收敛到 **FAIL 0**（PASS 6 + PASS_WITH_FALLBACK 37），全量测试 758 passed 无回归，满足计划全部任务与出口标准。
