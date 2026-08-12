# Tasks

- [x] Task 1: 修复 `_to_float_array` 清洗脏字符串
  - [x] 1.1: 在 `src/rdi/skills/sensor_data.py` 的 `_to_float_array` 中，把脏字符串（`"nan"`/`"NaN"`/`""`/`"inf"`/`"-inf"`/`"null"`/`"none"`，不区分大小写）规整为 `None`，再走现有 `any(v is None) → return None` 逻辑
  - [x] 1.2: 更新模块 docstring 中 [sensor_data.py:8-10](../../src/rdi/skills/sensor_data.py) 的校准注释，标注脏字符串清洗已实现（不再只是已知坑）

- [x] Task 2: 扩展 `_TIMESTAMP_KEYS` 时间戳列名变体
  - [x] 2.1: 把 `_TIMESTAMP_KEYS` 从 `("timestamp","time","t")` 扩展为 `("timestamp","time","t","time_sec","t_sec","secs","seconds","stamp","t_s","time_s","timestamp_sec")`

- [x] Task 3: 降级时采样率设为 0.0
  - [x] 3.1: 在 `parse_csv` 中，降级（`_INFER_FLAG` in transformations）时 `sample_rate_hz = 0.0`，否则 `_compute_rate(timestamps)`
  - [x] 3.2: 在 `_parse_json_list` 和 `_parse_json_dict` 中做同样处理
  - [x] 3.3: 降级时 `transformations` 追加 `degraded_sample_rate_unknown` 标记

- [x] Task 4: 空信号显式失败
  - [x] 4.1: 在 `process` 中，解析成功后检查 `not dataset.signals` → 返回 `StandardResult(success=False, errors=["解析完成但未识别到任何数值信号列，可能是分隔符/表头/格式问题"])`

- [x] Task 5: 新增/更新单元测试覆盖修复点
  - [x] 5.1: 在 `tests/unit/skills/test_sensor_data.py` 新增测试：脏字符串列丢弃、降级采样率为 0、空信号失败、时间戳变体匹配、真实时间戳列不进 signals
  - [x] 5.2: 新增对应测试样本到 `tests/unit/skills/sample_data/sensor/`（dirty_nan.csv / ts_variants.csv / empty_signals.csv）
  - [x] 5.3: 跑 `uv run pytest tests/unit/skills/test_sensor_data.py -v` 全绿（含原 8 个 + 新增，实测 13 passed）

- [x] Task 6: 补测末端 F/T 传感器数据
  - [x] 6.1: 联网下载一份真实末端 6 轴 F/T 传感器时序数据（Mendeley Data DOI 10.17632/26674p3hvg.1，Kuka KR16 腕部 F/T，5152 行 83.33Hz）
  - [x] 6.2: 预处理为 CSV（time→timestamp, mx→tx, my→ty, mz→tz），存 `data/sensor_real/ft_end_effector_prepared.csv`
  - [x] 6.3: 用 `scripts/test_sensor_data_real.py --file` 跑修复后的 skill：success=True, confidence=1.0, signals=6, sample_rate=83.33Hz, validation 零 issue
  - [x] 6.4: 对比修复前后：合规数据正常解析；空信号修复前 success=True/signals=0（静默失败）→ 修复后 success=False + 明确错误；脏值列丢弃不再污染

# Task Dependencies
- Task 5 依赖 Task 1-4（测试覆盖修复点）
- Task 6 依赖 Task 1-4（用修复后的 skill 跑补测）
- Task 1/2/3/4 都在 `sensor_data.py`，建议顺序合并提交以避免冲突
