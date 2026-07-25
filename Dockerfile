# Dockerfile - 多阶段构建
# builder 阶段安装依赖，runtime 阶段只拷贝必要文件

FROM python:3.13-slim AS builder
WORKDIR /app
RUN pip install uv
COPY pyproject.toml README.md .
RUN uv sync --no-dev
COPY src/ src/

FROM python:3.13-slim AS runtime
WORKDIR /app
COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/src /app/src
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app/src"
EXPOSE 7860
CMD ["python", "-m", "rdi.frontend.app"]
