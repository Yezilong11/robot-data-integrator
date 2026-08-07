# Robot Data Integrator — 第一次联调报告

> 报告日期：2026-08-05  
> 状态：**第一次联调完成，可进入第二次联调**

## 1. 联调目标

验证 RDI 系统从"自然语言目标输入"到"结构化数据包输出"的端到端（E2E）链路是否打通，确认各节点能协同工作并真实落盘。

## 2. 联调结论

**结论：第一次联调成功结束，E2E 链路已完全打通。**

达成标志：

- 前端可以接收用户目标与 PDF，调用后端 LangGraph 工作流；
- `parse_goal` 节点能调用 LLM 将自然语言拆解为结构化数据需求；
- `retrieve_data` 节点能从 15 个外部数据源中检索真实数据；
- `parse_convert` 节点能调用对应 Skill 将原始数据标准化；
- `validate` 节点执行基础质量校验；
- `assemble` 节点将文件真实写入 `data/output_packages/` 并生成 `manifest.json`；
- 前端能展示数据包目录、文件列表、缺失项和校验结果。

## 3. 当前系统状态

### 3.1 全链路逐节点状态

```
输入(目标+PDF) → parse_goal(LLM) → retrieve_data(Adapter×N) → parse_convert(Skill)
                → validate(基础校验) → assemble(真实落盘) → human_review → 前端展示
   ✅ 通             ✅ 通               ✅ 通                  ✅ 通
                        ✅ 通                  ✅ 通            ✅ 通
```

### 3.2 Adapter 真实命中率（探活结果）

使用 `scripts/_probe_adapters.py` 对 15 个 Adapter 进行探测：

| 结果 | 数量 | Adapter 名称 |
|------|------|--------------|
| search 成功 | 14/15 | arxiv, github, huggingface, zenodo, paperswithcode, dexgrasp, graspnet, ycb, franka, allegro, robotiq, mujoco, isaac, google_scanned |
| fetch 成功 | 13/15 | 除 google_scanned 超时、ieee 未配 key 外均成功 |

**关键发现**：角色 C 提交后，Franka / YCB / GraspNet / MuJoCo 等 Adapter 的 fetch 已修复，当前网络环境下能真实下载数据。

### 3.3 质量门禁

| 检查项 | 结果 |
|--------|------|
| 单元测试 | 282 passed, 1 skipped, 4 deselected |
| ruff check | All checks passed |
| ruff format | All files formatted |
| mypy src | Success: no issues found |

## 4. 已解决的问题

| 问题 | 原因 | 解决方式 |
|------|------|----------|
| `Expected dict, got [Send(...)]` | `retrieve_data` 普通节点返回 `list[Send]` 触发 LangGraph 异常 | 改为返回 dict，内部顺序调用单条检索 |
| 前端异步驱动错误 | 使用 `graph.invoke` 调用 async 图 | 改为 `graph.ainvoke` |
| `missing_items` 为空 | `assemble` 节点丢弃了缺失项 | `assemble` 保留缺失项并写入 manifest |
| 数据包不真实落盘 | `assemble` 使用 `package_placeholder` 路径 | 改为真实写入 `data/output_packages/package-<ts>/` |
| `validation_issues` 为空 | `validate` 节点是骨架 | 实现空数据、完整度、置信度、REQUIRED 缺失校验 |
| 审查决定不生效 | `human_review` 硬编码 `satisfied` | 尊重前端传入的 `review_decision` 并记录反馈 |
| `QualityReport` 置信度/完整度硬编码 | `avg_confidence=1.0`, `avg_completeness=100.0` | 按 `manifest_files` 实际值计算平均值 |
| paper/code/dataset 缺 Skill | 注册表未注册这三类 Skill | 补齐 `PaperSkill`，code/dataset 仍待实现 |
| Adapter fetch 失败 | 旧版 Adapter URL 或下载逻辑错误 | 角色 C 重写 `BaseAdapter` 并逐个修复 Adapter |

## 5. 可复现的完整示例

### 示例目标

> **"搜索关于 robot grasping 的 arXiv 论文，获取 PDF 并解析文本"**

### 运行方式

```bash
uv run python scripts/demo_paper_pipeline.py
```

或启动 Gradio 前端：

```bash
uv run python -m rdi.frontend.app
```

然后在"实验目标"框填入上述目标，选择"真实流程"，点击"运行"。

### 预期结果

```text
数据包 ID: package-20260805-143339
输出目录: data/output_packages/package-20260805-143339
文件数: 3
缺失项: 0
质量报告: 3/3 需求满足
状态: complete
```

数据包目录下包含：

```text
package-20260805-143339/
├── files/
│   ├── req_000.json    # 论文文本与元数据
│   ├── req_001.json    # 论文文本与元数据
│   └── req_002.json    # 论文文本与元数据
├── manifest.json       # 数据包清单
└── provenance.log      # 溯源日志
```

## 6. 当前已知限制

| 限制 | 说明 | 影响 |
|------|------|------|
| `GoogleScannedAdapter.fetch` 超时 | 当前网络下 .zip 下载超过 30s | 该数据源无法使用 |
| `IEEEXploreAdapter` 未启用 | `.env` 中 `IEEE_API_KEY` 未配置 | IEEE 论文检索不可用 |
| `CODE` / `DATASET` Skill 缺失 | 注册表中无对应 Skill | code/dataset 类型需求无法解析入包 |
| `validate` 校验深度有限 | 仅检查空/完整度/置信度/缺失 | 不检查 URDF 可加载、mesh 损坏等格式问题 |
| `revise` 未真正驱动重检索 | 用户反馈只记录，未触发目标修正 | 人机闭环不完整 |
| 输出路径 warning | `PaperSkill` 未设置 `output_path` | `validation_issues` 有 2 个良性 warning |
| 查询关键词偏长 | LLM 描述直接当搜索词 | 复杂目标可能降低命中率 |

## 7. 给第二次联调的建议

### 7.1 第二阶段目标

让系统产出**非空的机器人实验数据包**（包含 URDF / mesh / grasp / sim_config 等真实文件），而不仅是论文文本。

### 7.2 建议任务清单

1. **修复 `GoogleScannedAdapter.fetch` 超时**
   - 诊断是 URL 问题还是网络问题，必要时换源或增加 chunked 下载；
2. **补齐 `CODE` 和 `DATASET` Skill**
   - 实现代码仓库解析（README + 文件结构）和数据集元数据解析；
3. **增加格式深度校验**
   - URDF 可解析、mesh 文件可加载、XML 合法性等；
4. **实现 revise 真正闭环**
   - 把用户反馈传给 LLM 修正目标或关键词，再触发一次检索；
5. **优化查询关键词**
   - 在 `retrieve_data` 中对 LLM 描述做关键词压缩，提升 Adapter 命中率；
6. **修复 `PaperSkill.output_path` warning**
   - 让 `validation_issues` 完全为空；
7. **增加前端进度/日志展示**
   - 用更友好的方式展示当前检索哪个源、命中/失败原因；
8. **接入真实机器人实验目标验证**
   - 用"Franka Panda + YCB 香蕉 + MuJoCo"目标跑完整流程，确认能拿到真实文件。

### 7.3 第二阶段验收标准

- 至少一个包含 URDF / mesh / grasp / sim_config 中两类以上的真实数据包生成；
- `files` 目录下非空，且文件可被外部工具（如 MuJoCo / trimesh）加载；
- `missing_items` 可解释；
- 单元测试与集成测试全绿；
- 用户能在前端清晰看到进度与结果。

## 8. 环境信息

- Python 3.13.9
- 操作系统：Windows
- LLM 模型：`qwen3.7-pro` via DashScope
- 外部数据源：arxiv, github, huggingface(hf-mirror), zenodo, paperswithcode, dexgrasp, graspnet, ycb, franka, allegro, robotiq, mujoco, isaac 已验证可用

## 9. 备注

- 本报告基于当前 HEAD（含角色 C 的 Adapter 重构提交），状态以 `scripts/_probe_adapters.py` 与 `pytest` 实际输出为准；
- 数据包样例位于 `data/output_packages/package-20260805-143339/`；
- 探活原始证据保存在 `data/probe_adapters_results.json`。
