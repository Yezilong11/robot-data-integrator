# Makefile - 常用命令快捷入口

.PHONY: setup test lint format typecheck clean run docker-up docker-down

# 一键初始化：安装依赖 + pre-commit hooks
setup:
	uv sync --extra dev
	uv run pre-commit install
	@echo "Setup complete! Copy .env.example to .env and fill in your keys."

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