# Day2 问题清单与经验教训

> 记录日期：2026-08-13
> 用途：问题复盘，供 Day3 及以后吸取教训
> 状态：问题均已处理（处理方式见各条）

## 一、技术问题（代码 / 运行）

### 1.1 前端真实流程在数据检索阶段中断（async/sync 混用）

| 项 | 内容 |
|---|---|
| 现象 | E 报告每轮测试都跑不通，真实流程跑到 retrieve_data 就中断 |
| 根因 | 前端 `run_graph` 用同步 `graph.stream`，而 `retrieve_data` 是 async 节点（内部 `asyncio.gather` 并发）。langgraph 同步运行时遇到 coroutine 节点直接抛 `TypeError: No synchronous function provided to "retrieve_data"` |
| 处理 | 方案 B：builder 给 retrieve_data 包同步 wrapper（`asyncio.run`），改一处不碰前端 |
| 验证 | sync stream 全 6 节点跑通；pytest 727 passed |
| 教训 | LangGraph 图内混用 async/sync 节点时，同步 API（stream/invoke）不支持 async 节点，需二选一（改节点或改调用方式）；优先选改动面小的方案 |

### 1.2 franka / mujoco 检索 60s 超时（E 报"全部检索超时"的根源）

| 项 | 内容 |
|---|---|
| 现象 | robot_urdf / sim_config 两类需求全部超过 per_req_timeout（60s） |
| 根因 | search 主路径先爬国外文档站（franka.de / mujoco.readthedocs.io），国内连接挂起，每次请求 30s 超时 × 重试，60s 总预算在 search 阶段就被耗尽，fetch 根本没机会执行 |
| 处理 | franka / mujoco 的国外主路径 search/fetch 各包 `asyncio.timeout(10)`，挂起快速转 fallback 硬编码列表（命中集合不变） |
| 效果 | 60s 超时 → 19~22s success（franka URDF+18 资产、mujoco MJCF+68 资产全下载） |
| 教训 | 国内网络环境下，国外直连 URL 一律用短超时快速降级，不能依赖"重试等超时"；download 阶段已有 jsdelivr 镜像兜底，瓶颈在 search 的国外站点 |

### 1.3 GraspNet 检索成功但无真实 grasp 文件

| 项 | 内容 |
|---|---|
| 现象 | 检索 success 但仅 567B 元数据 JSON，无真实 npz |
| 根因 | GraspNet-1Billion 的标注只存在于大体积 tar/hdf5 归档中，无法按单个文件获取（对应已知风险 R1） |
| 处理 | 走 fallback（元数据 + 手动下载提示），判定 PASS_WITH_FALLBACK |
| 教训 | 已知风险要提前同步给执行人，避免现场执行时才暴露 |

### 1.4 arXiv PDF 超过体积阈值只回元数据

| 项 | 内容 |
|---|---|
| 现象 | 6MB PDF 超过 `arxiv_max_fetch_bytes=2MB`，返回 metadata JSON 而非 PDF |
| 根因 | 国内下载大 PDF 慢，2MB 阈值是保守默认 |
| 处理 | 保持默认（可经 `ARXIV_MAX_FETCH_BYTES` 调大），按 fallback 判定 |
| 教训 | 配置权衡点应提前记录在案，执行期不做现场决策 |

## 二、前端体验问题（E d2 文档报告）

| 问题 | 处理 | 状态 |
|---|---|---|
| 目标输入页停留约 5s 才进进度展示页，进度计时从进入才开始，与输入时间不一致 | 记录待处理 | 未修（非执行阻塞） |
| Provenance 记录不能翻页 | 记录待处理 | 未修（非执行阻塞） |

- 教训：执行期开始前应先做一轮前端 UI 冒烟，避免测试中反复打断。

## 三、文档口径问题

### 3.1 截图规范新旧口径并存（2 张 vs 4 张）

| 项 | 内容 |
|---|---|
| 现象 | Day2 文档写"截图至少 2 张"，Day1 已定稿 4 张（01_input/02_progress/03_package/04_validation + 05_error） |
| 处理 | 按定稿 4 张统一，避免执行与验收当场冲突 |
| 教训 | 口径变更后要全局搜一遍所有引用（文档 / 模板 / 脚本），防止新旧口径并存 |

### 3.2 任务分配描述残留

| 项 | 内容 |
|---|---|
| 现象 | Day2 文档写"E 执行流程类单源题第一批（如 ss_mujoco_001）"，实际 E 的正式分配是 ms_004 / ms_007 多源题 |
| 处理 | 以 `records/_management/assignments.csv` 为准，向 E 澄清 |
| 教训 | 任务分配以 assignments.csv 为唯一事实来源，文档引用必须同步，否则组员被旧信息误导 |

## 四、git / 工具链问题

### 4.1 pre-commit mypy 报 "Executable mypy not found"

| 项 | 内容 |
|---|---|
| 根因 | 钩子 `language: system` 在 commit 触发环境 PATH 中找不到 mypy（未激活项目 venv） |
| 处理 | 钩子 `entry` 改为 `uv run mypy`，统一走项目工具链 |
| 教训 | 钩子依赖项目依赖时用 `uv run` 显式指定，不能依赖隐式 PATH |

### 4.2 commitizen 拒绝提交信息

| 项 | 内容 |
|---|---|
| 现象 | 提交信息"问题集搭建Day1"无 type 前缀被拒 |
| 处理 | 按 `type(scope): description` 格式（本次用 `fix(retrieval): ...`） |
| 教训 | 项目 commit 强制 commitizen 格式，提交前先确认 type 与 scope |

### 4.3 ruff 钩子自动修复后提交失败

| 项 | 内容 |
|---|---|
| 现象 | ruff hook "files were modified by this hook"，提交中断 |
| 根因 | ruff 自动修复了 1 处 lint（import 空行），修改发生在暂存区之外 |
| 处理 | `git add` 被修文件后重新提交 |
| 教训 | ruff auto-fix 修改文件后必须重新暂存再提交；`MM` 状态提示工作区有未暂存改动 |

## 五、经验教训总结（原则）

1. **口径先统一再执行**：截图 4 张、判定三档（PASS / PASS_WITH_FALLBACK / FAIL）、P0 验收线 ≥8/11，任何变更全局同步。
2. **分配以 assignments.csv 为准**：文档/群消息只是引用，不另立事实来源。
3. **国内网络的国外源**：search/fetch 一律短超时快速降级，禁止依赖长超时重试。
4. **LangGraph async/sync**：改动优先选后端小改（wrapper），不轻易动前端调用链。
5. **已知风险提前分发**：graspnet 元数据、arxiv PDF 阈值等在执行前同步给执行人，落 fallback 预期。
6. **提交规范是底线**：commitizen 格式 + pre-commit 全绿，CI 严格检查前先本地过一遍。
