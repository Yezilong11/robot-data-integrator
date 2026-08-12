# tests/unit/skills/test_sensor_data.py
"""SensorDataSkill 单元测试（SYNC）。

覆盖 spec「SensorDataSkill — 传感器与实验数据对齐」全部 scenario：
- CSV 时间序列对齐（含时间戳列）
- 缺失时间戳列降级（行号兜底 + warning + completeness<100）
- JSON dict 形 / list 形解析
- 多源采样率统一（线性插值到最小公共采样率）
- ROS bag 降级（rosbag 不可用）
- 未知格式失败
- 校验：空信号 WARNING
"""

from pathlib import Path

import numpy as np

from rdi.models.common import Severity, StandardResult
from rdi.skills.sensor_data import SensorDataset, SensorDataSkill

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "sensor"


def _read(name: str) -> bytes:
    return (_SAMPLE_DIR / name).read_bytes()


class TestSensorCsv:
    """CSV 解析路径测试。"""

    def test_parse_csv_with_timestamp(self) -> None:
        result = SensorDataSkill().process(_read("joints.csv"), fmt="csv")
        assert result.success is True
        assert result.canonical_format == "SensorDataset"
        assert isinstance(result.data, SensorDataset)
        ds = result.data
        assert ds.timestamps.shape == (6,)
        assert {"joint_0", "joint_1", "force"} <= set(ds.signals)
        assert abs(ds.sample_rate_hz - 10.0) < 1e-6
        assert result.confidence_score == 1.0

    def test_parse_csv_missing_timestamp_degrades(self) -> None:
        result = SensorDataSkill().process(_read("no_timestamp.csv"), fmt="csv")
        assert result.success is True
        assert result.warnings  # 非空：推断时间戳
        assert result.completeness_pct < 100.0
        assert result.confidence_score < 1.0
        ds = result.data
        assert np.array_equal(ds.timestamps, np.arange(ds.timestamps.size))


class TestSensorJson:
    """JSON 解析路径测试。"""

    def test_parse_json_dict_form(self) -> None:
        result = SensorDataSkill().process(_read("signals.json"), fmt="json")
        assert result.success is True
        assert isinstance(result.data, SensorDataset)
        assert {"joint_0", "joint_1"} <= set(result.data.signals)

    def test_parse_json_list_form(self) -> None:
        result = SensorDataSkill().process(_read("events.json"), fmt="json")
        assert result.success is True
        ds = result.data
        assert "x" in ds.signals
        # timestamps 来自 timestamp 键，非行号兜底
        assert "infer_timestamps_from_index" not in ds.transformations
        assert ds.timestamps[0] == 0.0
        assert result.confidence_score == 1.0


class TestSensorAlign:
    """多源采样率统一测试。"""

    def test_align_multiple_rates(self) -> None:
        skill = SensorDataSkill()
        ds1 = skill.parse_csv(_read("joints.csv"))  # 10Hz, 0.0-0.5
        ds2 = skill.parse_json(_read("events.json"))  # 20Hz, 0.0-0.3
        merged = skill.align_signals([ds1, ds2])
        assert merged.sample_rate_hz == 10.0  # 最小公共采样率（最慢源）
        assert any("resample_to_10.0Hz" in t for t in merged.transformations)
        # 两路信号都存在
        assert {"joint_0", "joint_1", "force", "x"} <= set(merged.signals)
        # 公共时间基在重叠区间 [0.0, 0.3) 内以 0.1 步长
        assert merged.timestamps.size >= 2
        assert merged.timestamps[0] == 0.0
        assert merged.timestamps[-1] < 0.3


class TestSensorDegradation:
    """降级与失败路径测试。"""

    def test_bag_degrades(self) -> None:
        result = SensorDataSkill().process(b"x", fmt="bag")
        assert result.success is False
        assert any("rosbag" in e for e in result.errors)

    def test_unknown_format_fails(self) -> None:
        result = SensorDataSkill().process(b"x", fmt="unknown")
        assert result.success is False


class TestSensorValidate:
    """校验路径测试。"""

    def test_validate_empty_signals_warning(self) -> None:
        ds = SensorDataset(
            timestamps=np.arange(3, dtype=np.float64),
            signals={},
            sample_rate_hz=0.0,
            source_format="csv",
        )
        result = StandardResult(success=True, canonical_format="SensorDataset", data=ds)
        report = SensorDataSkill().validate(result)
        assert report.is_valid is True  # WARNING 不影响 is_valid
        assert any(vi.severity == Severity.WARNING for vi in report.issues)


class TestSensorRealDataFixes:
    """覆盖 spec「SensorDataSkill 真实生数据修复」5 个 scenario。"""

    def test_dirty_string_column_dropped(self) -> None:
        # 脏字符串列（NaN/nan）被 _to_float_array 清洗为 None 后丢弃，不进 signals
        result = SensorDataSkill().process(_read("dirty_nan.csv"), fmt="csv")
        assert result.success is True
        ds = result.data
        assert "fx" in ds.signals
        assert "fz" in ds.signals
        assert "fy" not in ds.signals  # 含 NaN/nan 脏值，整列丢弃

    def test_degraded_sample_rate_zero(self) -> None:
        # 缺时间戳列走行号兜底：sample_rate_hz=0.0 + degraded_sample_rate_unknown 标记
        result = SensorDataSkill().process(_read("no_timestamp.csv"), fmt="csv")
        assert result.success is True
        ds = result.data
        assert ds.sample_rate_hz == 0.0
        assert "degraded_sample_rate_unknown" in ds.transformations

    def test_empty_signals_fails(self) -> None:
        # 全非数值列 → signals 空 → 显式失败（不再静默 success=True）
        result = SensorDataSkill().process(_read("empty_signals.csv"), fmt="csv")
        assert result.success is False
        assert result.errors  # 非空，提示分隔符/表头/格式问题

    def test_timestamp_variants_matched(self) -> None:
        # time_sec 列名变体被识别为时间戳列：confidence=1.0，采样率 100Hz
        result = SensorDataSkill().process(_read("ts_variants.csv"), fmt="csv")
        assert result.success is True
        assert result.confidence_score == 1.0
        ds = result.data
        assert abs(ds.sample_rate_hz - 100.0) < 1e-6
        assert "time_sec" not in ds.signals

    def test_timestamp_column_not_in_signals(self) -> None:
        # 时间戳列被识别后不进 signals 字典的 keys（语义清晰）
        result = SensorDataSkill().process(_read("ts_variants.csv"), fmt="csv")
        assert result.success is True
        assert "time_sec" not in result.data.signals.keys()
