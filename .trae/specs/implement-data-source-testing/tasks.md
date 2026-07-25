# Tasks

- [x] Task 1: 修复阻塞配置问题（pyproject.toml + settings.py + .env.example）
  - [x] SubTask 1.1: 修复 pyproject.toml L2 缺少引号的语法错误
  - [x] SubTask 1.2: 修复 settings.py qwen_api_key 无默认值问题（加 default=""）
  - [x] SubTask 1.3: 在 settings.py 新增 ieee_api_key 配置项
  - [x] SubTask 1.4: 在 .env.example 新增 IEEE_API_KEY 占位项
  - [x] SubTask 1.5: 运行 `uv sync` 验证依赖可安装

- [x] Task 2: 创建 data/sources/ 目录结构
  - [x] SubTask 2.1: 创建 api/arxiv/metadata、api/arxiv/pdfs、api/github/repos、api/github/releases
  - [x] SubTask 2.2: 创建 api/huggingface/models、api/zenodo/records、api/ieee/metadata、api/ieee/pdfs
  - [x] SubTask 2.3: 创建 web/franka/panda、web/robotiq/grippers、web/allegro/hand、web/paperswithcode/papers
  - [x] SubTask 2.4: 创建 web/mujoco/examples、web/isaac/examples
  - [x] SubTask 2.5: 创建 datasets/graspnet/dataset、datasets/dexgraspnet/data、datasets/ycb/models、datasets/google_scanned/models
  - [x] SubTask 2.6: 创建 papers/、scripts/ 目录

- [x] Task 3: 实现 scripts/test_connectivity.py 连通性测试脚本
  - [x] SubTask 3.1: 定义 TestResult dataclass（source, url, status, status_code, response_time, auth_required, error_message, data_valid）
  - [x] SubTask 3.2: 实现 ConnectivityTester 类，含 15 个异步测试方法（test_arxiv ~ test_isaac）
  - [x] SubTask 3.3: 实现 test_all() 并发调度 + 超时控制（10s per source）
  - [x] SubTask 3.4: 实现 generate_report() 生成 Markdown 报告到 data/connectivity_report.md
  - [x] SubTask 3.5: 从环境变量读取 GitHub Token 和 IEEE API Key（可选认证）
  - [x] SubTask 3.6: 实现命令行入口 `python scripts/test_connectivity.py`

- [x] Task 4: 运行连通性测试，确认结果
  - [x] SubTask 4.1: 运行 `python scripts/test_connectivity.py`
  - [x] SubTask 4.2: 检查 data/connectivity_report.md，记录哪些源可用、哪些需要凭证

- [x] Task 5: 实现 scripts/download_arxiv.py
  - [x] SubTask 5.1: 按关键词搜索 arXiv（robot grasping, 6-DOF grasp, manipulation, dexterous hand）
  - [x] SubTask 5.2: 下载元数据 JSON 到 data/sources/api/arxiv/metadata/
  - [x] SubTask 5.3: 下载 PDF 到 data/sources/api/arxiv/pdfs/
  - [x] SubTask 5.4: 已存在文件跳过逻辑 + 命令行参数控制数量/关键词

- [x] Task 6: 实现 scripts/download_github.py
  - [x] SubTask 6.1: 按关键词搜索 GitHub 仓库，按 stars 排序，取 Top 30
  - [x] SubTask 6.2: 下载每个仓库 README 到 data/sources/api/github/repos/
  - [x] SubTask 6.3: 下载每个仓库 Release 资产到 data/sources/api/github/releases/
  - [x] SubTask 6.4: 已存在文件跳过 + 速率控制（认证 5000/h，未认证 60/h）

- [x] Task 7: 实现 scripts/download_huggingface.py
  - [x] SubTask 7.1: 搜索 robot grasping 相关模型
  - [x] SubTask 7.2: 下载模型配置文件 config.json 到 data/sources/api/huggingface/models/
  - [x] SubTask 7.3: 下载模型权重文件（.pt/.pth/.safetensors）

- [x] Task 8: 实现 scripts/download_zenodo.py
  - [x] SubTask 8.1: 搜索 robot grasping 相关记录
  - [x] SubTask 8.2: 下载元数据和数据文件到 data/sources/api/zenodo/records/

- [x] Task 9: 实现 scripts/download_paperswithcode.py
  - [x] SubTask 9.1: 搜索抓取相关论文-代码关联
  - [x] SubTask 9.2: 提取关联代码仓库链接，存储元数据到 data/sources/web/paperswithcode/papers/

- [x] Task 10: 实现 URDF 下载脚本（franka + robotiq + allegro）
  - [x] SubTask 10.1: 实现 scripts/download_franka.py，下载 Panda URDF + mesh 到 data/sources/web/franka/panda/
  - [x] SubTask 10.2: 实现 scripts/download_robotiq.py，下载夹爪 URDF 到 data/sources/web/robotiq/grippers/
  - [x] SubTask 10.3: 实现 scripts/download_allegro.py，下载灵巧手 URDF 到 data/sources/web/allegro/hand/

- [x] Task 11: 实现仿真配置下载脚本（mujoco + isaac）
  - [x] SubTask 11.1: 实现 scripts/download_mujoco.py，下载 MJCF XML 示例到 data/sources/web/mujoco/examples/
  - [x] SubTask 11.2: 实现 scripts/download_isaac.py，下载 USD 配置示例到 data/sources/web/isaac/examples/

- [x] Task 12: 实现大型数据集下载脚本（graspnet + ycb + google_scanned + dexgraspnet）
  - [x] SubTask 12.1: 实现 scripts/download_graspnet.py，含下载链接获取 + MD5 校验
  - [x] SubTask 12.2: 实现 scripts/download_ycb.py，下载标准 20 个物体模型
  - [x] SubTask 12.3: 实现 scripts/download_google_scanned.py
  - [x] SubTask 12.4: 实现 scripts/download_dexgraspnet.py，从 HuggingFace 下载

- [x] Task 13: 实现 scripts/verify_data.py 数据完整性校验
  - [x] SubTask 13.1: 检查每个数据源目录下文件数量是否符合预期
  - [x] SubTask 13.2: 检查文件大小 > 0
  - [x] SubTask 13.3: 对有 MD5 的文件做校验和验证
  - [x] SubTask 13.4: 生成 data/verification_report.md

# Task Dependencies
- [Task 3] depends on [Task 1]（脚本需要 import rdi.config.settings）
- [Task 4] depends on [Task 3]
- [Task 5-12] 可并行开发，但依赖 [Task 1]（配置可用）+ [Task 2]（目录结构存在）
- [Task 13] depends on [Task 5-12]（需要有数据才能校验）
