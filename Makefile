# Makefile - 常用命令快捷入口

.PHONY: setup test lint format typecheck clean run docker-up docker-down \
        init-data \
        connectivity download download-papers download-code download-models \
        download-hardware download-sim download-datasets verify-data \
        download-arxiv download-paperswithcode download-github download-huggingface \
        download-zenodo download-franka download-robotiq download-allegro \
        download-mujoco download-isaac download-graspnet download-ycb \
        download-google-scanned download-dexgraspnet

# 一键初始化：安装依赖 + pre-commit hooks
setup:
	uv sync --extra dev
	uv run pre-commit install
	@echo "Setup complete! Copy .env.example to .env and fill in your keys."

# 重建 data 目录结构（data/ 已 gitignored，克隆仓库后需要重新创建）
init-data:
	uv run python scripts/init_data_dirs.py

# 一键跑测试 + lint + type check
test:
	uv run ruff check src tests
	uv run mypy src
	uv run pytest tests -v --cov=rdi --cov-report=term-missing

# 仅运行单元测试
test-unit:
	uv run pytest tests/unit -v

# 运行集成测试
test-integration:
	uv run pytest tests/integration -v

# 仅 lint
lint:
	uv run ruff check src tests

# 格式化
format:
	uv run ruff format src tests
	uv run ruff check --fix src tests

# 类型检查
typecheck:
	uv run mypy src

# 启动前端
run:
	uv run python -m rdi.frontend.app

# 启动本地服务依赖
docker-up:
	docker-compose up -d

docker-down:
	docker-compose down

# 清理
clean:
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
	rm -rf data/experience_db/* data/output_packages/*
	find . -type d -name __pycache__ -exec rm -rf {} +

# ============================================================
# 数据源连通性测试与数据下载
# ============================================================

# 连通性测试
connectivity:
	uv run python scripts/test_connectivity.py

# 数据完整性校验
verify-data:
	uv run python scripts/verify_data.py

# 一键下载全部数据（论文 + 代码模型 + 硬件仿真 + 数据集）
download: download-papers download-code download-models download-hardware download-sim download-datasets
	@echo "=== 全部数据下载完成 ==="
	@echo "运行 make verify-data 检查数据完整性"

# 论文数据（arXiv + Semantic Scholar）
download-papers: download-arxiv download-paperswithcode

# 代码与模型（GitHub + HuggingFace + Zenodo）
download-code: download-github download-zenodo
download-models: download-huggingface

# 硬件 URDF（Franka + Robotiq + Allegro）
download-hardware: download-franka download-robotiq download-allegro

# 仿真配置（MuJoCo + Isaac Sim）
download-sim: download-mujoco download-isaac

# 大型数据集（GraspNet + YCB + Google Scanned + DexGraspNet）
download-datasets: download-graspnet download-ycb download-google-scanned download-dexgraspnet

# --- 单个数据源 ---

download-arxiv:
	uv run python scripts/download_arxiv.py --max-results 50

download-paperswithcode:
	uv run python scripts/download_paperswithcode.py --q "robot grasping" --limit 50

download-github:
	uv run python scripts/download_github.py --max-repos 30 --query "robot grasping"

download-huggingface:
	uv run python scripts/download_huggingface.py --search "robot grasping" --limit 10

download-zenodo:
	uv run python scripts/download_zenodo.py --query "robot grasping" --size 10

download-franka:
	uv run python scripts/download_franka.py

download-robotiq:
	uv run python scripts/download_robotiq.py

download-allegro:
	uv run python scripts/download_allegro.py

download-mujoco:
	uv run python scripts/download_mujoco.py

download-isaac:
	uv run python scripts/download_isaac.py

download-graspnet:
	uv run python scripts/download_graspnet.py

download-ycb:
	uv run python scripts/download_ycb.py

download-google-scanned:
	uv run python scripts/download_google_scanned.py

download-dexgraspnet:
	uv run python scripts/download_dexgraspnet.py --max-size-mb 500
