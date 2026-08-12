# Checklist

- [x] `_to_float_array` 清洗脏字符串（"NaN"/"nan"/""/等，不区分大小写）为 None，含脏值列被丢弃而非以 nan 保留
- [x] `_TIMESTAMP_KEYS` 扩展常见变体（time_sec/t_sec/secs/seconds/stamp/t_s/time_s/timestamp_sec）
- [x] 降级（行号兜底）时 `sample_rate_hz = 0.0`，不再误推 1.0Hz
- [x] 降级时 `transformations` 含 `degraded_sample_rate_unknown` 标记
- [x] 解析成功但 `signals` 为空 → `success=False` + 清晰错误说明
- [x] 真实时间戳列（含变体）不进 `signals` 字典
- [x] 现有 8 个单元测试仍全绿（向后兼容）
- [x] 新增测试覆盖 5 个修复点（脏字符串/降级采样率/空信号/时间戳变体/时间戳列不进信号）
- [x] 新增测试样本到 `tests/unit/skills/sample_data/sensor/`
- [x] 下载真实末端 6 轴 F/T 数据并存 `data/sensor_real/`
- [x] 用修复后 skill 跑末端 F/T 数据：6 路信号识别、采样率合理、无静默失败
- [x] 记录补测结果（success/confidence/signals/sample_rate/validation）
