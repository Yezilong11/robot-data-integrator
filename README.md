# Robot Data Integrator

面向机器人操作与抓取领域的多源异构数据智能整合系统

2026 挑战杯揭榜挂帅 · 阿里云榜题 · 赛道2 维度A

## 快速开始

```bash
# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 填入真实 API Key

# 运行连通性测试
python scripts/test_connectivity.py
```

## LLM 配置

本项目采用 **OpenAI 兼容接口**接入大语言模型，通过 `LLM_BASE_URL` 切换厂商，无需修改代码。

`.env` 中相关配置项：

```env
LLM_API_KEY=sk-xxxx                  # LLM 服务 API Key
LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1  # OpenAI 兼容端点
LLM_MODEL=qwen-plus                  # 模型名称
LLM_EMBEDDING_MODEL=text-embedding-v3
LLM_MAX_RETRIES=3
LLM_TEMPERATURE=0.3
```

### 切换 LLM 厂商

只需修改 `LLM_BASE_URL` 和 `LLM_MODEL`（必要时同步改 `LLM_EMBEDDING_MODEL`）：

| 厂商 | `LLM_BASE_URL` | `LLM_MODEL` 示例 |
|------|---------------|------------------|
| 阿里云 Qwen | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-plus` |
| DeepSeek | `https://api.deepseek.com/v1` | `deepseek-chat` |
| 智谱 GLM | `https://open.bigmodel.cn/api/paas/v4` | `glm-4-plus` |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o-mini` |

> **BREAKING CHANGE**：本版本将原 `QWEN_*` 环境变量重命名为 `LLM_*` 并新增 `LLM_BASE_URL`。
> 迁移方式：将 `.env` 中 `QWEN_API_KEY` 改为 `LLM_API_KEY`，`QWEN_MODEL` 改为 `LLM_MODEL`，依此类推。
