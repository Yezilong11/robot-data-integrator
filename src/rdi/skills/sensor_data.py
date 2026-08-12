# src/rdi/skills/sensor_data.py
"""SensorDataSkill — 传感器与实验数据时间序列对齐 Skill.

将 CSV / JSON 时间序列解析为 ``SensorDataset``（统一时间戳 + 对齐信号 + 采样率），
支持多源按最小公共采样率（最慢源速率）线性插值对齐。ROS bag 在缺少 ``rosbag``
模块时走降级路径，不抛异常（符合 BaseSkill 契约）。

校准（ponytail: 真实数据 ≠ spec 理想）：``E:\\数据收集\\data2\\sources\\`` 实测无
``.bag``，bag 仅兜底；「最大公共采样率」实为最小采样率；``np.asarray([None,1.0])``
不抛错而产生 nan，故数值列识别需先排除 None 再转 float；脏字符串（nan/NaN/""/inf/
-inf/null/none，不区分大小写）已在 ``_to_float_array`` 清洗为 None 后丢弃，不再以
nan 形式保留污染下游插值（已处理，非仅已知坑）。
"""

import csv
import importlib
import io
import json
from dataclasses import dataclass, field
from typing import Any

import numpy as np

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# 候选时间戳列/键名（小写匹配），首个命中者生效
_TIMESTAMP_KEYS = (
    "timestamp", "time", "t", "time_sec", "t_sec", "secs", "seconds",
    "stamp", "t_s", "time_s", "timestamp_sec",
)
# 缺时间戳列时写入 transformations 的标记，供 process 识别并降级 completeness
_INFER_FLAG = "infer_timestamps_from_index"
# 降级（行号兜底）时采样率未知，追加此标记提示下游
_DEGRADED_RATE_FLAG = "degraded_sample_rate_unknown"
# 脏字符串（不区分大小写）：清洗为 None 后由 _to_float_array 丢弃该列
_DIRTY_TOKENS = {"nan", "", "inf", "-inf", "null", "none"}
_CANONICAL_FORMAT = "SensorDataset"


@dataclass
class SensorDataset:
    """传感器时间序列中间表示。

    Attributes:
        timestamps: 1D float64 时间戳数组（秒）
        signals: 信号名 → 与 timestamps 等长的 1D float64 数组
        sample_rate_hz: 采样率（Hz）；无法推断时为 0.0
        source_format: 源格式（"csv" / "json" / "aligned"）
        transformations: 经历的转换步骤列表（如时间戳推断、重采样）
    """

    timestamps: np.ndarray
    signals: dict[str, np.ndarray]
    sample_rate_hz: float
    source_format: str
    transformations: list[str] = field(default_factory=list)


def _to_float_array(values: list[Any]) -> np.ndarray | None:
    """把值列表转为一维 float64 数组；含 None/脏字符串/非数值时返回 None。

    先把脏字符串（"nan"/"NaN"/""/"inf"/"-inf"/"null"/"none"，不区分大小写）
    规整为 None，再走现有 ``any(v is None) → return None`` 逻辑：含脏值的列
    被识别为非纯数值列而丢弃，避免 nan 污染下游插值。
    """
    cleaned = [
        None if (isinstance(v, str) and v.strip().lower() in _DIRTY_TOKENS) else v
        for v in values
    ]
    if any(v is None for v in cleaned):
        return None
    try:
        return np.asarray(cleaned, dtype=np.float64)
    except (ValueError, TypeError):
        return None


def _compute_rate(timestamps: np.ndarray) -> float:
    """由时间戳差分中位数推采样率：n<2 或中位差分<=0 返回 0.0。"""
    if timestamps.size < 2:
        return 0.0
    med = float(np.median(np.diff(timestamps)))
    return 1.0 / med if med > 0.0 else 0.0


def _issue(severity: Severity, message: str, suggestion: str = "") -> ValIssue:
    """构造 sensor_data req_id 的 ValIssue（validate 内复用，消除重复）。"""
    return ValIssue(severity=severity, req_id="sensor_data", message=message, suggestion=suggestion)


class SensorDataSkill(BaseSkill):
    """传感器/实验数据 Skill：CSV/JSON 解析 → 多源采样率统一 → 校验。"""

    skill_name = "sensor_data"

    def parse_csv(self, data: bytes) -> SensorDataset:
        """解析 CSV 字节为 ``SensorDataset``。

        时间戳列匹配首个 ``timestamp``/``time``/``t``（大小写不敏感）；缺失则以
        ``np.arange(n)`` 兜底并在 ``transformations`` 标记 ``infer_timestamps_from_index``
        供 ``process`` 识别。非数值列被跳过。ValueError: 无数据行或时间戳列非数值。
        """
        reader = csv.DictReader(io.StringIO(data.decode("utf-8")))
        rows = list(reader)
        if not rows:
            raise ValueError("CSV 无数据行")
        fieldnames = reader.fieldnames or []

        lower_map = {name.lower(): name for name in fieldnames}
        ts_col: str | None = None
        for key in _TIMESTAMP_KEYS:
            if key in lower_map:
                ts_col = lower_map[key]
                break

        transformations: list[str] = []
        n = len(rows)
        if ts_col is not None:
            ts_arr = _to_float_array([row[ts_col] for row in rows])
            if ts_arr is None:
                raise ValueError(f"时间戳列 {ts_col} 非数值")
            timestamps = ts_arr
        else:
            timestamps = np.arange(n, dtype=np.float64)
            transformations.append(_INFER_FLAG)
            transformations.append(_DEGRADED_RATE_FLAG)

        signals: dict[str, np.ndarray] = {}
        for name in fieldnames:
            if name == ts_col:
                continue
            arr = _to_float_array([row[name] for row in rows])
            if arr is not None:
                signals[name] = arr

        return SensorDataset(
            timestamps=timestamps,
            signals=signals,
            sample_rate_hz=(
                0.0 if _INFER_FLAG in transformations else _compute_rate(timestamps)
            ),
            source_format="csv",
            transformations=transformations,
        )

    def parse_json(self, data: bytes) -> SensorDataset:
        """解析 JSON 字节为 ``SensorDataset``，支持 list / dict 两种结构。

        list 形: ``[{"timestamp": 0.0, "x": 1.0}, ...]``
        dict 形: ``{"signals": {...}, "timestamps": [...]}`` 或 ``{"signals": {...}}``
        """
        obj = json.loads(data.decode("utf-8"))
        if isinstance(obj, list):
            return self._parse_json_list(obj)
        if isinstance(obj, dict):
            return self._parse_json_dict(obj)
        raise ValueError(f"不支持的 JSON 顶层结构: {type(obj).__name__}")

    @staticmethod
    def _parse_json_list(items: list[Any]) -> SensorDataset:
        """list 形 JSON：从每条记录提取 timestamp/time 与其他数值键。"""
        if not items:
            raise ValueError("JSON list 为空")
        first = items[0]
        ts_key: str | None = None
        if isinstance(first, dict):
            lower_keys = {k.lower(): k for k in first}
            for cand in _TIMESTAMP_KEYS:
                if cand in lower_keys:
                    ts_key = lower_keys[cand]
                    break

        transformations: list[str] = []
        n = len(items)
        if ts_key is not None:
            ts_arr = _to_float_array([item.get(ts_key) for item in items if isinstance(item, dict)])
            if ts_arr is None:
                raise ValueError(f"时间戳键 {ts_key} 非数值")
            timestamps = ts_arr
        else:
            timestamps = np.arange(n, dtype=np.float64)
            transformations.append(_INFER_FLAG)
            transformations.append(_DEGRADED_RATE_FLAG)

        signals: dict[str, np.ndarray] = {}
        if isinstance(first, dict):
            for key in first:
                if key == ts_key:
                    continue
                arr = _to_float_array(
                    [item.get(key) if isinstance(item, dict) else None for item in items]
                )
                if arr is not None:
                    signals[key] = arr

        return SensorDataset(
            timestamps=timestamps,
            signals=signals,
            sample_rate_hz=(
                0.0 if _INFER_FLAG in transformations else _compute_rate(timestamps)
            ),
            source_format="json",
            transformations=transformations,
        )

    @staticmethod
    def _parse_json_dict(obj: dict[str, Any]) -> SensorDataset:
        """dict 形 JSON：``signals`` 必填，``timestamps`` 可选（缺则 arange）。"""
        if "signals" not in obj:
            raise ValueError("JSON dict 缺少 signals 键")
        raw_signals = obj["signals"]
        if not isinstance(raw_signals, dict) or not raw_signals:
            raise ValueError("signals 必须为非空 dict")
        signals: dict[str, np.ndarray] = {}
        for name, vals in raw_signals.items():
            arr = _to_float_array(list(vals))
            if arr is not None:
                signals[name] = arr

        transformations: list[str] = []
        if obj.get("timestamps") is not None:
            ts_arr = _to_float_array(list(obj["timestamps"]))
            if ts_arr is None:
                raise ValueError("timestamps 非数值")
            timestamps = ts_arr
        else:
            n = max((arr.size for arr in signals.values()), default=0)
            timestamps = np.arange(n, dtype=np.float64)
            transformations.append(_INFER_FLAG)
            transformations.append(_DEGRADED_RATE_FLAG)

        return SensorDataset(
            timestamps=timestamps,
            signals=signals,
            sample_rate_hz=(
                0.0 if _INFER_FLAG in transformations else _compute_rate(timestamps)
            ),
            source_format="json",
            transformations=transformations,
        )

    def align_signals(self, datasets: list[SensorDataset]) -> SensorDataset:
        """多源按最小公共采样率（最慢源速率）线性插值对齐到公共时间基。

        公共时间基：``[max(starts), min(ends))`` 以 ``1/target_rate`` 步长；
        target_rate = min(各正采样率)。信号长度与源时间戳不等时跳过该信号。
        """
        if not datasets:
            raise ValueError("datasets 为空")
        if len(datasets) == 1:
            return datasets[0]

        positive_rates = [ds.sample_rate_hz for ds in datasets if ds.sample_rate_hz > 0.0]
        if not positive_rates:
            raise ValueError("所有数据集采样率为 0，无法对齐")
        target_rate = min(positive_rates)

        nonempty = [ds for ds in datasets if ds.timestamps.size]
        if not nonempty:
            raise ValueError("所有数据集时间戳为空")
        start = max(float(ds.timestamps[0]) for ds in nonempty)
        end = min(float(ds.timestamps[-1]) for ds in nonempty)
        if end <= start:
            raise ValueError("数据集时间区间无重叠")

        common_ts = np.arange(start, end, 1.0 / target_rate)
        merged_signals: dict[str, np.ndarray] = {}
        transformations = [f"resample_to_{target_rate}Hz"]
        for ds in datasets:
            for name, arr in ds.signals.items():
                if arr.size != ds.timestamps.size:
                    continue
                merged_signals[name] = np.interp(common_ts, ds.timestamps, arr)

        return SensorDataset(
            timestamps=common_ts,
            signals=merged_signals,
            sample_rate_hz=target_rate,
            source_format="aligned",
            transformations=transformations,
        )

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """按 fmt 解析传感器数据；bag 路径降级；未知格式失败。"""
        fmt = str(kwargs.get("fmt", "csv")).lower()
        name = kwargs.get("name")
        ext = "csv" if fmt == "csv" else "json"
        output_path = f"scripts/{name}.{ext}" if isinstance(name, str) and name else None

        if fmt in ("csv", "json"):
            parse = self.parse_csv if fmt == "csv" else self.parse_json
            try:
                dataset = parse(data)
            except Exception as exc:  # noqa: BLE001 — 任意解析失败均降级
                return StandardResult(
                    success=False,
                    canonical_format=_CANONICAL_FORMAT,
                    errors=[f"{fmt} 解析失败: {exc}"],
                )
            if not dataset.signals:
                return StandardResult(
                    success=False,
                    canonical_format=_CANONICAL_FORMAT,
                    errors=["解析完成但未识别到任何数值信号列，可能是分隔符/表头/格式问题"],
                )
            warnings_list: list[str] = []
            completeness = 100.0
            confidence = 1.0
            if _INFER_FLAG in dataset.transformations:
                warnings_list.append("缺少时间戳列，已用行号生成单调递增时间戳")
                completeness = 70.0
                confidence = 0.7
            return StandardResult(
                success=True,
                canonical_format=_CANONICAL_FORMAT,
                data=dataset,
                output_path=output_path,
                completeness_pct=completeness,
                confidence_score=confidence,
                warnings=warnings_list,
                # D1: 传感器信号单位异构（电压/温度/加速度…）无法单一标注，坐标系标注 unknown
                units="",
                coordinate_frame="unknown",
            )

        if fmt == "bag":
            try:
                importlib.import_module("rosbag")
            except ImportError:
                return StandardResult(
                    success=False,
                    canonical_format=_CANONICAL_FORMAT,
                    errors=["ROS bag 解析需要 rosbag 模块"],
                )
            # rosbag 可用时仍需文件路径而非内存字节，环境通常不可用，仅兜底降级
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=["ROS bag 内存解析未实现，请提供文件路径"],
            )

        return StandardResult(
            success=False,
            canonical_format=_CANONICAL_FORMAT,
            errors=[f"不支持的格式: {fmt}"],
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验：失败→invalid；信号空 → WARNING；时间戳非严格单调 → WARNING。"""
        if not result.success or result.data is None:
            return ValidationReport(
                is_valid=False,
                issues=[_issue(Severity.ERROR, "传感器数据处理失败，无可校验数据")],
                summary="传感器数据处理失败",
            )
        dataset = result.data
        if not isinstance(dataset, SensorDataset):
            return ValidationReport(
                is_valid=False,
                issues=[_issue(Severity.ERROR, "中间表示类型错误")],
                summary="中间表示类型错误",
            )

        issues: list[ValIssue] = []
        if not dataset.signals:
            issues.append(_issue(Severity.WARNING, "信号集为空", "检查源数据是否含数值列"))
        if dataset.timestamps.size >= 2 and not bool(np.all(np.diff(dataset.timestamps) > 0)):
            issues.append(
                _issue(Severity.WARNING, "时间戳非严格单调递增", "检查时间戳列或对齐后的公共时间基")
            )
        return ValidationReport(
            is_valid=True,
            issues=issues,
            summary=(
                f"传感器数据校验完成 (signals={len(dataset.signals)}, "
                f"rate={dataset.sample_rate_hz}Hz, warnings={len(issues)})"
            ),
        )
