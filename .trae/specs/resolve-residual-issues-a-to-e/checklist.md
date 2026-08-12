# Checklist

## A 组：实现 gap 补齐
- [x] A1：含 assets 的 item 落盘后，manifest 含资产条目（downloaded=true、checksum 与磁盘一致）且 checksums.txt 覆盖资产文件
- [x] A2：MJCF include 链深层 mesh/texture 递归下载进 assets；include 循环/超深递归终止不抛异常
- [x] A2'：`_mujoco_runtime_check` 用 assets 落地临时目录后加载，不再恒为 skipped
- [x] A3：`package://` 引用按 xml 目录为基准解析下载（pybullet_robots 场景实测成功）；无效 package:// 跳过并产生 validate 警告
- [x] A4：合成抓取 StandardResult.is_fallback=True，ParsedItem.is_fallback 合并语义正确（retrieval 层 or skill 层任一 True 即 True）

## B 组：可复现性
- [x] B1：全库无 `master`/`main` 分支 raw URL 残留；franka 等源 URL 钉 commit 且注释记录 pin 日期
- [x] B2：流程运行后 `state.run_id` 非空；manifest.package_info.run_id 与其一致；前端可见；不设 run_id 的单跑兼容（为空）
- [x] B3：缓存 TTL 过期失效（cache_ttl_seconds 生效）；query 乱序 URL 命中同一缓存键；franka 主/降级路径缓存互不覆盖

## C 组：业务链路
- [x] C1：DataReq.object_name 从目标提取；retrieve 透传到 graspnet/ycb；「banana 的抓取标注」按 banana 取文件而非仓库第一个
- [x] C2：清单外目标 search 返回可诊断语义（reason 含「仅收录已知目标」+ 清单大小 +「有源但未收录」），不静默空；多 query 场景不回归 C1
- [x] C3：数据集仅元数据时 grasp_parse 返回 MissingItem（reason 含「原始数据缺失、合成占位仅作参考」），不再 success 交付合成数据
- [x] C4：GRASP 期望 CanonicalGrasp 却拿到 obj 时记 MissingItem（reason 含期望/实际格式 +「类型错配」，无抓取标注时追加说明）；合法格式不误报
- [x] C5：unsatisfied/revised 只重跑 `retry_req_ids` 覆盖的失败 req，已成功项沿用不重拉

## D 组：P2 演进
- [x] D1：ParsedItem.units/coordinate_frame/timestamp_epoch 非空（装配后）；CanonicalGrasp 带单位标注；包内 units.json 含每 req 的旋转/原点/单位约定（来自 DATASET_CONVENTIONS）
- [x] D2：DataReqType 新增 CAMERA_CALIB/TEACHING_TRAJECTORY/ROBOT_CONFIG/BENCHMARK_TASK；新类型可识别且无内置源时 missing + reason「暂无内置数据源」
- [x] D3：settings.local_datasets 配置后，adapter 命中本地文件直接使用（provenance source=local），未命中走网络；与 per-req local_files 并存

## E 组：体验与可观测性
- [x] E1：前端分步展示 retrieve/parse/validate/assemble 阶段状态与中间结果，非黑盒一次性提交
- [x] E2：structlog 生效，LOG_LEVEL/LOG_FORMAT 配置起作用；核心节点有结构化日志
- [x] E3：演示流程产物带 demo 标记（独立目录或 manifest 标记），不混入真实 output_packages；真实流程不伪造 fallback 包

## 回归
- [x] `uv run pytest tests/ -q` 全量通过（无回归）
- [x] `uv run python scripts/smoke_adapters.py` 冒烟通过
- [x] 端到端核对：URDF/MJCF 包离线完整（资产含 checksum）、run_id 在 manifest、object_name 生效、清单外可诊断、合成降级为 missing、units.json 落盘、前端分步可见
