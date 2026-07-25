# Checklist

## test_connectivity.py 修复
- [x] arXiv URL 改为 https://export.arxiv.org/api/query
- [x] HuggingFace / DexGraspNet / Google Scanned 超时设为 30s
- [x] Papers with Code 替换为 Semantic Scholar API 并测试通过（422 → rate_limited）
- [x] YCB URL 改为 S3 镜像并测试通过
- [x] Google Scanned URL 改为 GCS Storage API 并测试通过
- [x] Allegro URL 改为 GitHub API (simlabrobotics/allegro_hand_ros) 并测试通过
- [x] MuJoCo URL 改为 GitHub API (google-deepmind/mujoco) 并测试通过
- [x] DexGraspNet 数据集名修正为 lhrlhr/DexGraspNet2.0 并测试通过
- [x] httpx follow_redirects=True + User-Agent header
- [x] Semantic Scholar 429 标记为 rate_limited

## 连通性测试重跑
- [x] `python scripts/test_connectivity.py` 成功运行
- [x] 成功率 14/15（IEEE 需 API Key 为预期行为）

## 下载脚本修复
- [x] download_arxiv.py 基础 URL 改为 https
- [x] download_paperswithcode.py 改用 Semantic Scholar API
- [x] download_ycb.py URL 改为 S3 镜像
- [x] download_dexgraspnet.py 数据集名改为 lhrlhr/DexGraspNet2.0
