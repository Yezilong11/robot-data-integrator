# Checklist

## 配置修复
- [x] pyproject.toml L2 引号修复，`uv sync` 可正常运行
- [x] settings.py qwen_api_key 有默认值，无 .env 时 Settings() 不崩溃
- [x] settings.py 新增 ieee_api_key 配置项
- [x] .env.example 新增 IEEE_API_KEY 占位项

## 目录结构
- [x] data/sources/api/arxiv/metadata/ 和 pdfs/ 存在
- [x] data/sources/api/github/repos/ 和 releases/ 存在
- [x] data/sources/api/huggingface/models/ 存在
- [x] data/sources/api/zenodo/records/ 存在
- [x] data/sources/web/franka/panda/ 存在
- [x] data/sources/web/robotiq/grippers/ 存在
- [x] data/sources/web/allegro/hand/ 存在
- [x] data/sources/web/paperswithcode/papers/ 存在
- [x] data/sources/web/mujoco/examples/ 存在
- [x] data/sources/web/isaac/examples/ 存在
- [x] data/sources/datasets/graspnet/dataset/ 存在
- [x] data/sources/datasets/dexgraspnet/data/ 存在
- [x] data/sources/datasets/ycb/models/ 存在
- [x] data/sources/datasets/google_scanned/models/ 存在
- [x] data/sources/papers/ 存在
- [x] scripts/ 目录存在

## 连通性测试脚本
- [x] test_connectivity.py 可正常执行 `python scripts/test_connectivity.py`
- [x] 测试 14 个数据源的 HTTP 连通性
- [x] 每个源记录状态码、响应时间、认证需求
- [x] 验证响应格式（XML/JSON/HTML）是否符合预期
- [x] 生成 data/connectivity_report.md 报告
- [x] 凭证缺失时标记 auth_required 而非 failed
- [x] 超时时标记 timeout，不中断其他源测试

## 下载脚本（每个）
- [x] arxiv: 元数据 JSON + PDF 下载到指定目录，支持命令行参数
- [x] github: Top 30 仓库 README + Release 资产，含速率控制
- [x] huggingface: 模型配置 + 权重下载
- [x] zenodo: 科研数据集元数据 + 数据文件
- [x] paperswithcode: 论文-代码关联提取
- [x] franka: Panda URDF + mesh 下载
- [x] robotiq: 夹爪 URDF 下载
- [x] allegro: 灵巧手 URDF 下载
- [x] mujoco: MJCF XML 示例下载
- [x] isaac: USD 配置示例下载
- [x] graspnet: 大型数据集下载 + MD5 校验（按设计方案：30GB数据集提供手动下载说明 + MD5 校验功能）
- [x] ycb: 物体模型下载
- [x] google_scanned: 3D 扫描物体下载
- [x] dexgraspnet: HuggingFace 数据集下载
- [x] 所有下载脚本支持已存在文件跳过（graspnet 为手动下载模式，通过目录结构校验实现跳过）

## 数据校验
- [x] verify_data.py 可执行 `python scripts/verify_data.py`
- [x] 检查文件数量符合预期
- [x] 检查文件大小 > 0
- [x] 对有 MD5 的文件做校验和验证
- [x] 生成 data/verification_report.md