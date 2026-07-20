# robot-data-integrator

面向机器人操作与抓取领域的多源异构数据智能整合系统

## 数据源 Adapter 文档

### arXiv Adapter

- **API 文档**：http://export.arxiv.org/api/query
- **速率限制**：建议每 3 秒 1 次请求（`rate_limit=3`）
- **认证**：无需 API Key
- **数据需求类型**：`DataReqType.PAPER`（主源）
