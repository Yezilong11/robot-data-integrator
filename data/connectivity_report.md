# 数据源连通性测试报告

> 测试时间：2026-07-14 18:13:30
> 测试环境：Windows 11, Python 3.11

## 测试结果汇总

| 数据源 | 状态 | 响应时间 | 认证需求 | 响应格式 | 备注 |
|--------|------|---------|---------|---------|------|
| arXiv | ✅ 成功 | 3.39s | False | ✅ | 返回 1 条记录 |
| IEEE Xplore | ❌ 失败 | 4.95s | False | ❌ | HTTP 418 |
| GitHub | 🔐 需认证 | 4.14s | True | ❌ | HTTP 401: 需要认证 |
| Papers with Code | ✅ 成功 | 11.7s | False | ❌ |  |
| HuggingFace | ✅ 成功 | 1.12s | False | ✅ |  |
| GraspNet | ✅ 成功 | 4.03s | False | ✅ |  |
| DexGraspNet | ❌ 失败 | 1.0s | False | ❌ | HTTP 404 |
| YCB | ❌ 失败 | 16.28s | False | ❌ | HTTP 404 |
| Google Scanned | ❌ 失败 | 3.14s | False | ❌ | HTTP 404 |
| Zenodo | ✅ 成功 | 14.77s | False | ✅ |  |
| Franka | ✅ 成功 | 2.59s | False | ✅ |  |
| Robotiq | ✅ 成功 | 2.43s | False | ✅ |  |
| Allegro | ⏱️ 超时 | 44.33s | False | ❌ | 请求超时（>30.0s） |
| MuJoCo | ✅ 成功 | 6.35s | False | ✅ |  |
| Isaac Sim | ✅ 成功 | 1.21s | False | ✅ |  |

## 详细结果

### arXiv

- URL: `http://export.arxiv.org/api/query?search_query=robot+grasping&max_results=1`
- 状态码: 200
- 响应时间: 3.39s
- 响应格式验证: ✅ 通过
- 额外信息: 返回 1 条记录

### IEEE Xplore

- URL: `https://ieeexplore.ieee.org/rest/search`
- 状态码: 418
- 响应时间: 4.95s
- 响应格式验证: ❌ 未通过
- 错误信息: HTTP 418

### GitHub

- URL: `https://api.github.com/search/repositories?q=robot+grasping&per_page=1`
- 状态码: 401
- 响应时间: 4.14s
- 响应格式验证: ❌ 未通过
- 认证: 需要认证
- 错误信息: HTTP 401: 需要认证

### Papers with Code

- URL: `https://paperswithcode.com/api/v1/search/?q=robot+grasping`
- 状态码: 200
- 响应时间: 11.7s
- 响应格式验证: ❌ 未通过

### HuggingFace

- URL: `https://huggingface.co/api/models?search=robot+grasping&limit=1`
- 状态码: 200
- 响应时间: 1.12s
- 响应格式验证: ✅ 通过

### GraspNet

- URL: `https://graspnet.net/`
- 状态码: 200
- 响应时间: 4.03s
- 响应格式验证: ✅ 通过

### DexGraspNet

- URL: `https://huggingface.co/datasets/dexgraspnet`
- 状态码: 404
- 响应时间: 1.0s
- 响应格式验证: ❌ 未通过
- 错误信息: HTTP 404

### YCB

- URL: `https://rse-lab.cs.washington.edu/projects/3d-object-reconstruction/`
- 状态码: 404
- 响应时间: 16.28s
- 响应格式验证: ❌ 未通过
- 错误信息: HTTP 404

### Google Scanned

- URL: `https://research.google/blog/scanned-objects-a-dataset-of-3d-scanned-everyday-objects/`
- 状态码: 404
- 响应时间: 3.14s
- 响应格式验证: ❌ 未通过
- 错误信息: HTTP 404

### Zenodo

- URL: `https://zenodo.org/api/records?q=robot+grasping&size=1`
- 状态码: 200
- 响应时间: 14.77s
- 响应格式验证: ✅ 通过

### Franka

- URL: `https://franka.de/`
- 状态码: 200
- 响应时间: 2.59s
- 响应格式验证: ✅ 通过

### Robotiq

- URL: `https://robotiq.com/`
- 状态码: 200
- 响应时间: 2.43s
- 响应格式验证: ✅ 通过

### Allegro

- URL: `https://www.wonikrobotics.com/`
- 状态码: N/A
- 响应时间: 44.33s
- 响应格式验证: ❌ 未通过
- 错误信息: 请求超时（>30.0s）

### MuJoCo

- URL: `https://mujoco.readthedocs.io/`
- 状态码: 200
- 响应时间: 6.35s
- 响应格式验证: ✅ 通过

### Isaac Sim

- URL: `https://docs.isaacsim.omniverse.nvidia.com/`
- 状态码: 200
- 响应时间: 1.21s
- 响应格式验证: ✅ 通过

## 统计

- 总计: 15 个数据源
- 成功: 9 个
- 失败: 6 个