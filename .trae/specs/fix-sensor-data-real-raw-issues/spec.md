# SensorDataSkill 真实生数据修复 Spec

## Why
二联测试中，`SensorDataSkill` 在真实 Franka 力矩时序数据上暴露 5 个问题，导致 skill 无法可靠处理真实生数据：静默失败（`success=True` 但 `signals` 空）、降级时采样率误推（1.0Hz vs 真实 1000Hz）、时间戳列名匹配过严、NaN 字符串未清洗、真实时间戳列被当信号。这些问题根因集中在 [sensor_data.py](../../src/rdi/skills/sensor_data.py) 的解析与降级逻辑，需一次性修复根因（ponytail：一处 guard 惠及所有调用方），并补测一份真正的末端 6 轴 F/T 传感器数据验证修复效果（先不测端到端）。

## What Changes
- **MODIFIED** [src/rdi/skills/sensor_data.py](../../src/rdi/skills/sensor_data.py)：
  - `_to_float_array`：先把脏字符串（`"nan"`/`"NaN"`/`""`/`"inf"`/`"-inf"`/`"null"`/`"none"`，不区分大小写）规整为 `None`，再走现有"含 None 返回 None"逻辑 → 含脏值的列被识别为非纯数值列而丢弃，不再以 nan 污染下游插值
  - `_TIMESTAMP_KEYS`：扩展常见变体 → `("timestamp","time","t","time_sec","t_sec","secs","seconds","stamp","t_s","time_s","timestamp_sec")`
  - `parse_csv` / `_parse_json_list` / `_parse_json_dict`：降级（行号兜底）时 `sample_rate_hz = 0.0`（不再 `_compute_rate(arange)` 误推 1.0Hz），`transformations` 追加 `degraded_sample_rate_unknown` 标记
  - `process`：解析成功后检查 `not dataset.signals` → 返回 `success=False` + 清晰错误（提示可能分隔符/表头/格式问题），不再静默返回 `success=True`
- **MODIFIED** [tests/unit/skills/test_sensor_data.py](../../tests/unit/skills/test_sensor_data.py)：新增覆盖 5 个修复点的测试
- **补测**：下载真实末端 6 轴 F/T 传感器时序数据，跑修复后的 skill 记录结果（复用 `scripts/test_sensor_data_real.py`，不新增测试脚本）

## Impact
- Affected code: `src/rdi/skills/sensor_data.py`
- Affected tests: `tests/unit/skills/test_sensor_data.py`
- 新增测试样本: `tests/unit/skills/sample_data/sensor/`（自包含小样本）
- 补测数据: `data/sensor_real/`（.gitignore，不入库）
- 向后兼容：现有 8 个单元测试不受影响（修复点不改变现有测试场景的预期行为）

## ADDED Requirements

### Requirement: 末端 F/T 传感器数据补测
系统 SHALL 提供一份真实末端 6 轴 F/T 传感器时序数据，用于验证修复后的 `SensorDataSkill` 能处理真实末端力/力矩数据（区别于之前测的关节力矩 tau_J）。

#### Scenario: 数据获取
- **WHEN** 实施补测
- **THEN** 下载一份真实末端 F/T 传感器时序数据（含 fx/fy/fz/tx/ty/tz 6 路力/力矩 + 时间戳，CSV 或可转 CSV 的 .mat/.bag）
- **AND** 若格式非 CSV，预处理为 CSV（只搬格式不改数值）
- **AND** 数据存放 `data/sensor_real/`（.gitignore）

#### Scenario: 修复验证（skill 层，非端到端）
- **WHEN** 用修复后的 skill 处理末端 F/T 数据
- **THEN** 复用 `scripts/test_sensor_data_real.py` 驱动 `SensorDataSkill.process` + `validate`
- **AND** 记录 success/confidence/signals/sample_rate/validation 结果
- **AND** 6 路 F/T 信号被正确识别、采样率合理、无静默失败

## MODIFIED Requirements

### Requirement: SensorDataSkill 真实生数据处理
`SensorDataSkill` SHALL 在真实生数据（非理想样例）上可靠工作：脏字符串清洗、时间戳列名放宽、降级时不误推采样率、空信号显式失败。

#### Scenario: 脏字符串列丢弃
- **WHEN** CSV 某列含 `"NaN"`/`"nan"`/`""`/`"inf"` 等脏字符串
- **THEN** 该列被 `_to_float_array` 识别为非纯数值列而丢弃（不进入 `signals`）
- **AND** 不以 nan 形式保留污染下游插值

#### Scenario: 降级时采样率未知
- **WHEN** CSV 缺时间戳列，走行号兜底降级
- **THEN** `sample_rate_hz = 0.0`（不再误推 1.0Hz）
- **AND** `transformations` 含 `degraded_sample_rate_unknown` 标记
- **AND** `completeness_pct < 100`、`confidence_score < 1.0`

#### Scenario: 空信号显式失败
- **WHEN** 解析成功但 `signals` 为空（如空格分隔无表头被误读为单字段）
- **THEN** `process` 返回 `success=False`
- **AND** `errors` 含清晰说明（提示可能分隔符/表头/格式问题）
- **AND** 不再返回 `success=True` 误导下游

#### Scenario: 时间戳列名变体匹配
- **WHEN** CSV 时间戳列名为 `time_sec`/`t_s`/`stamp`/`secs`/`seconds` 等常见变体
- **THEN** 被识别为时间戳列（不进 signals，不触发降级）
- **AND** `confidence_score = 1.0`、`completeness_pct = 100`

#### Scenario: 真实时间戳列不进信号
- **WHEN** 时间戳列被识别（无论标准名或变体）
- **THEN** 该列不出现在 `signals` 字典中
- **AND** 语义清晰：signals 只含数据信号

## REMOVED Requirements
无。本次为向后兼容修复 + 补测验证。
