# Tasks

- [x] Task 1: 修复 test_connectivity.py 中 9 个失败源的 URL 和超时设置
  - [x] SubTask 1.1: arXiv URL 从 http 改为 https
  - [x] SubTask 1.2: HuggingFace / DexGraspNet / Google Scanned 超时从 10s 提升到 30s
  - [x] SubTask 1.3: Papers with Code 替换为 Semantic Scholar API
  - [x] SubTask 1.4: YCB URL 改为 S3 镜像
  - [x] SubTask 1.5: Google Scanned URL 改为 GCS Storage API
  - [x] SubTask 1.6: Allegro URL 改为 GitHub API (simlabrobotics/allegro_hand_ros)
  - [x] SubTask 1.7: MuJoCo URL 改为 GitHub API (google-deepmind/mujoco)
  - [x] SubTask 1.8: DexGraspNet 数据集名修正为 lhrlhr/DexGraspNet2.0
  - [x] SubTask 1.9: httpx 加 follow_redirects=True + User-Agent
  - [x] SubTask 1.10: Semantic Scholar 429 标记为 rate_limited

- [x] Task 2: 重新运行连通性测试，确认修复效果
  - [x] SubTask 2.1: 运行 `python scripts/test_connectivity.py`
  - [x] SubTask 2.2: 检查报告，确认成功率提升到 14/15（唯一未通过是 IEEE 需 API Key）

- [x] Task 3: 修复 download_arxiv.py（http → https）
  - [x] SubTask 3.1: 将基础 URL 从 http://export.arxiv.org 改为 https://export.arxiv.org

- [x] Task 4: 重写 download_paperswithcode.py 使用 Semantic Scholar API
  - [x] SubTask 4.1: 用 Semantic Scholar API 搜索 robot grasping 论文
  - [x] SubTask 4.2: 提取论文元数据 + arXiv ID + 关联 GitHub 仓库信息
  - [x] SubTask 4.3: 存储到 data/sources/web/paperswithcode/papers/

- [x] Task 5: 修复 download_ycb.py 下载源
  - [x] SubTask 5.1: 将 URL 基础从 rse-lab 改为 S3 镜像 ycb-benchmarks.s3-website-us-east-1.amazonaws.com/data/

- [x] Task 6: 修复 download_dexgraspnet.py 数据集名
  - [x] SubTask 6.1: DATASET_REPO 从 "dexgraspnet" 改为 "lhrlhr/DexGraspNet2.0"

# Task Dependencies
- [Task 2] depends on [Task 1]
- [Task 3-6] 可与 [Task 1] 并行但建议 [Task 1] 先完成确认 URL 可用
