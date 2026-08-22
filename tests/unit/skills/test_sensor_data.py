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

import json
from pathlib import Path

import numpy as np

from rdi.models.common import Severity, StandardResult
from rdi.models.retrieval import RawReference
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

    def test_json_missing_signals_degrades_to_fallback(self) -> None:
        """fetch 返回数据集元数据 JSON（缺 signals 键，非时序数据）→ 降级成功 is_fallback。"""
        import json

        payload = {"dataset_id": "zenodo-1", "title": "robot joint dataset"}
        result = SensorDataSkill().process(
            json.dumps(payload).encode("utf-8"), fmt="json", name="joints"
        )
        assert result.success is True
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"
        assert result.data is not None

    def test_markdown_format_degrades_to_fallback(self) -> None:
        """源返回 markdown 文档（非时序数据）→ 降级成功 is_fallback。"""
        result = SensorDataSkill().process(b"# README", fmt="markdown", name="joints")
        assert result.success is True
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"


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


class TestSensorFallbackDownloadGuide:
    """降级产物 download_guide 结构扩展（Task 8）。"""

    def test_fallback_with_reference_kwarg_adds_download_guide(self) -> None:
        """registry 透传 RawReference → 降级产物含 download_guide（wget 命令可见）。"""
        payload = {"dataset_id": "zenodo-1", "title": "robot joint dataset"}
        ref = RawReference(
            url="https://zenodo.org/records/1/files/joints.csv",
            local_path="joints.csv",
            file_size=2048,
            reason="超过自动下载上限",
        )
        result = SensorDataSkill().process(
            json.dumps(payload).encode("utf-8"), fmt="json", name="joints", reference=ref
        )
        assert result.is_fallback is True
        assert result.data is not None
        # 原瘦 JSON 基础保留，顶层新增 download_guide
        assert "reason" in result.data["metadata"]
        guide = result.data["download_guide"]
        assert guide["status"] == "not_downloaded"
        assert guide["source_file_url"] == ref.url
        assert guide["file_size_bytes"] == 2048
        assert "超过自动下载上限" in guide["reason"]
        assert guide["method_hint"].startswith("wget ")
        assert guide["selected_by"]
        assert guide["alternatives"] == []

    def test_fallback_with_inline_download_guide_reuses(self) -> None:
        """data JSON 内嵌 download_guide（adapter 产出）→ 原样复用。"""
        guide = {
            "status": "not_downloaded",
            "reason": "超过 max_fetch_bytes 自动下载上限",
            "source_file_url": "https://zenodo.org/records/1/files/joints.csv",
            "file_size_bytes": 2048,
            "method_hint": "wget https://zenodo.org/records/1/files/joints.csv -O joints.csv",
            "selected_by": "ext=.csv; signals=joint",
            "alternatives": [],
        }
        payload = {"dataset_id": "zenodo-1", "downloaded": False, "download_guide": guide}
        result = SensorDataSkill().process(json.dumps(payload).encode("utf-8"), fmt="json", name="j")
        assert result.is_fallback is True
        assert result.data["download_guide"] == guide
        assert "reason" in result.data["metadata"]

    def test_fallback_without_reference_keeps_original(self) -> None:
        """无引用 → 产物保持 {"metadata": {"reason": ...}}，顶层无 download_guide（不回归）。"""
        result = SensorDataSkill().process(b"# README", fmt="markdown", name="joints")
        assert set(result.data) == {"metadata"}
        assert "download_guide" not in result.data

    def test_fallback_reference_without_url_keeps_original(self) -> None:
        """reference 无 url → 无下载指引，保持原结构。"""
        ref = RawReference(reason="无法下载")
        result = SensorDataSkill().process(b"# README", fmt="markdown", name="j", reference=ref)
        assert "download_guide" not in result.data
