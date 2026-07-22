# 数据源连通性测试与数据准备 Spec

## Why
项目系统依赖 14 个外部数据源（arXiv、GitHub、GraspNet、Franka 等），在开发 Adapter 层之前需要先验证这些数据源的连通性、获取真实样本数据用于测试和开发。没有真实数据，后续的 Skill 解析、校验、打包功能全部无法验证。

## What Changes
- 新建 `scripts/` 目录，存放测试和下载脚本（与 `src/` 分离，这些脚本不属于运行时代码）
- 新建 `scripts/test_connectivity.py`：异步测试 14 个数据源 HTTP 连通性，生成 Markdown 报告
- 新建 `scripts/download_arxiv.py`：从 arXiv 下载抓取领域论文元数据 + PDF
- 新建 `scripts/download_github.py`：从 GitHub API 下载 Top 30 仓库 README + Release 资产
- 新建 `scripts/download_huggingface.py`：从 HuggingFace 下载抓取相关模型
- 新建 `scripts/download_zenodo.py`：从 Zenodo 下载科研数据集
- 新建 `scripts/download_paperswithcode.py`：从 Papers with Code 提取论文-代码关联
- 新建 `scripts/download_franka.py`：下载 Franka Panda URDF
- 新建 `scripts/download_robotiq.py`：下载 Robotiq 夹爪 URDF
- 新建 `scripts/download_allegro.py`：下载 Allegro 灵巧手 URDF
- 新建 `scripts/download_mujoco.py`：下载 MuJoCo 配置示例 XML
- 新建 `scripts/download_isaac.py`：下载 Isaac Sim 配置示例
- 新建 `scripts/download_graspnet.py`：下载 GraspNet 数据集（含校验）
- 新建 `scripts/download_ycb.py`：下载 YCB 物体模型
- 新建 `scripts/download_google_scanned.py`：下载 Google Scanned Objects
- 新建 `scripts/download_dexgraspnet.py`：下载 DexGraspNet 数据集
- 新建 `scripts/verify_data.py`：校验已下载数据的完整性
- 新建 `data/sources/` 目录结构（api/web/datasets/papers）
- 修复 `pyproject.toml` L2 缺少引号的语法错误
- 修复 `src/rdi/config/settings.py` 中 `qwen_api_key` 无默认值导致启动崩溃的问题
- 新增 `IEEE_API_KEY` 配置项到 settings.py 和 .env.example

## Impact
- Affected code: `pyproject.toml`、`src/rdi/config/settings.py`、`.env.example`
- New code: `scripts/` 目录下 16 个脚本文件
- New data: `data/sources/` 目录结构

## ADDED Requirements

### Requirement: 数据源连通性测试
系统 SHALL 提供一个独立脚本 `scripts/test_connectivity.py`，异步测试 14 个数据源的 HTTP 连通性。

#### Scenario: 正常连通
- **WHEN** 运行 `python scripts/test_connectivity.py`
- **THEN** 脚本并发请求所有 14 个数据源
- **AND** 记录每个源的状态码、响应时间、认证需求
- **AND** 验证响应格式是否符合预期（XML/JSON/HTML）
- **AND** 生成 `data/connectivity_report.md` 报告

#### Scenario: 凭证缺失
- **WHEN** IEEE API Key 未配置
- **THEN** IEEE 测试标记为 `auth_required` 而非 `failed`
- **AND** 报告中注明"未配置凭证"

#### Scenario: 超时或网络不可达
- **WHEN** 某数据源请求超时（默认 10 秒）
- **THEN** 标记为 `timeout`，不中断其他源的测试

### Requirement: 分数据源下载脚本
系统 SHALL 为每个数据源提供独立的下载脚本，存放在 `scripts/download_*.py`。

#### Scenario: arXiv 下载
- **WHEN** 运行 `python scripts/download_arxiv.py`
- **THEN** 按关键词搜索抓取领域论文
- **AND** 下载元数据 JSON 到 `data/sources/api/arxiv/metadata/`
- **AND** 下载 PDF 到 `data/sources/api/arxiv/pdfs/`
- **AND** 支持通过命令行参数控制下载数量和关键词

#### Scenario: 已存在文件跳过
- **WHEN** 目标文件已存在且大小 > 0
- **THEN** 跳过下载，不重复请求

### Requirement: 数据完整性校验
系统 SHALL 提供 `scripts/verify_data.py` 校验已下载数据。

#### Scenario: 校验通过
- **WHEN** 运行 `python scripts/verify_data.py`
- **THEN** 检查每个数据源目录下文件数量是否符合预期
- **AND** 检查文件大小是否 > 0
- **AND** 对有 MD5 校验和的文件做完整性校验
- **AND** 生成 `data/verification_report.md`

### Requirement: 配置修复
系统 SHALL 修复阻碍脚本运行的配置问题。

#### Scenario: pyproject.toml 修复
- **WHEN** 修复 L2 `name = "robot-data-integrator` → `name = "robot-data-integrator"`
- **THEN** `uv sync` 可以正常执行

#### Scenario: settings.py 修复
- **WHEN** `qwen_api_key` 添加 `default=""`
- **THEN** 无 `.env` 文件时 `Settings()` 也能实例化
- **AND** 添加 `ieee_api_key` 配置项

## MODIFIED Requirements

### Requirement: .env.example 更新
在现有 `.env.example` 基础上新增 `IEEE_API_KEY` 占位项。
