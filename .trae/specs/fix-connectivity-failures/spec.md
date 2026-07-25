# 修复连通性测试失败数据源 Spec

## Why
连通性测试 15 个数据源中有 9 个失败/超时，根因各异：URL 协议错误（arXiv 用了 HTTP）、API 已停服（Papers with Code 2025年7月被 Meta 关闭）、超时太短（HuggingFace/DexGraspNet/Google Scanned）、原始站点已迁移（YCB 搬到 S3、Allegro/MuJoCo 需用 GitHub 仓库）。需逐一修复才能保证后续 Adapter 层有真实数据可对接。

## What Changes

### test_connectivity.py 修复
- arXiv URL `http://` → `https://export.arxiv.org/api/query`
- HuggingFace / DexGraspNet / Google Scanned：超时从 10s 提升到 30s（单独为这些源设更长超时）
- Papers with Code：API 已停服，替换为 **Semantic Scholar API**（`https://api.semanticscholar.org/graph/v1/paper/search`），搜索 robot grasping 论文
- YCB：URL 从 `rse-lab.cs.washington.edu` 改为 S3 镜像 `http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/`
- Google Scanned：URL 改为 GCS Storage JSON API `https://storage.googleapis.com/gresearch/`
- Allegro：URL 从 `wonikrobotics.com` 改为 GitHub `https://api.github.com/repos/WinikRobotics/allegro`
- MuJoCo：URL 从 `mujoco.readthedocs.io` 改为 GitHub `https://api.github.com/repos/deepmind/mujoco`

### download_*.py 脚本修复
- **download_paperswithcode.py**：替换为 Semantic Scholar API 实现论文-代码关联获取（Semantic Scholar 返回 `externalIds` 含 arXiv ID，可关联 GitHub）
- **download_arxiv.py**：将基础 URL 从 `http://` 改为 `https://`
- **download_ycb.py**：将下载源从官网改为 S3 镜像 `http://ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/`
- **download_allegro.py**：确保从 GitHub `WinikRobotics/allegro` 仓库获取 URDF（应该已经走 GitHub，验证即可）
- 其他下载脚本已通过 GitHub raw 获取，无需修改

## Impact
- Affected code: `scripts/test_connectivity.py`、`scripts/download_paperswithcode.py`、`scripts/download_arxiv.py`、`scripts/download_ycb.py`
- 数据源对接清单更新：Papers with Code → Semantic Scholar

## MODIFIED Requirements

### Requirement: 连通性测试
test_connectivity.py 中 9 个失败源的测试 URL 需更新为可用地址，超时策略需区分快源（10s）和慢源（30s）。

### Requirement: Papers with Code 替换
Papers with Code API 于 2025年7月被 Meta 关闭，替换为 Semantic Scholar API 做论文-代码关联。Semantic Scholar 返回论文元数据 + `externalIds`（含 arXiv ID），可通过 arXiv ID 关联 GitHub 仓库。

### Requirement: YCB 数据源迁移
YCB 官网 `rse-lab.cs.washington.edu` 已不可访问，数据集迁移至 S3 镜像 `ycb-benchmarks.s3-website-us-east-1.amazonaws.com`。
