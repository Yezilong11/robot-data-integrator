# tests/unit/skills/test_sim_config_honesty.py
"""SimConfig 降级场景诚实标记单测（Task 3: extend-kinova-isaac-format-coverage）。

覆盖：
- 非 MJCF（python/未知）或解析失败的降级产物必须携带降级标记
  （warnings 中 "降级场景：" 前缀中文说明，语义为占位场景不含机器人/任务语义）；
- 真实 MJCF 直通产物无标记；
- 装配（SkillRegistry）透传标记；
- validate 节点将带标记产物呈现为独立 WARNING，且不改变 passed 判定
  （不触发占位 ERROR）。
"""

from datetime import datetime

from rdi.graph.nodes.validate import node_validate
from rdi.models import DataReqType, DataSource, ParsedItem, Priority
from rdi.models.common import ProvenanceEntry, Severity
from rdi.models.goal import DataReq
from rdi.models.retrieval import RawData, RetrievalResult
from rdi.skills.registry import SkillRegistry
from rdi.skills.sim_config import SimConfigSkill

_FIXED_TIME = datetime(2026, 7, 23, 12, 0, 0)

# 极简 python 配置（IsaacLab 资产为 Python 配置，sim_config 无法直接解析为 MJCF）
_PYTHON_CFG = b"import numpy as np\nrobot_cfg = {'name': 'franka'}\n"

# 极简但真实合法的 MJCF（含 <mujoco> 根与 <worldbody>，可直通）
_MJCF = (
    b'<mujoco model="box_scene">'
    b"<worldbody>"
    b'<geom name="box" type="box" size="0.1 0.1 0.1" pos="0 0 0.5"/>'
    b"</worldbody></mujoco>"
)

_DEGRADED_MARK = "降级场景："


def _has_degraded_mark(warnings: list[str]) -> bool:
    return any(w.startswith(_DEGRADED_MARK) for w in warnings)


def _provenance(fmt: str) -> ProvenanceEntry:
    return ProvenanceEntry(
        source=DataSource.KINOVA,
        source_url="https://example.com/franka.py",
        retrieved_at=_FIXED_TIME,
        original_format=fmt,
    )


# ─── sim_config 层：降级路径必须带标记 ───


def test_python_input_marks_degraded_scene() -> None:
    """fmt=python（非 MJCF）→ 最小 MJCF 结果携带降级标记。"""
    result = SimConfigSkill().process(_PYTHON_CFG, fmt="python")
    assert result.success is True
    assert result.canonical_format == "mjcf"
    assert result.is_fallback is True
    assert result.data_source_quality == "fallback"
    assert _has_degraded_mark(result.warnings)
    assert any("不含真实机器人/任务语义" in w for w in result.warnings)


def test_invalid_mjcf_fallback_marks_degraded() -> None:
    """MJCF 解析失败的降级路径亦携带标记。"""
    result = SimConfigSkill().process(b"<not-xml>", fmt="mjcf")
    assert result.success is True
    assert _has_degraded_mark(result.warnings)


def test_unknown_format_fallback_marks_degraded() -> None:
    """未知格式（yaml/未知）降级路径亦携带标记。"""
    result = SimConfigSkill().process(b"objects: []\n", fmt="yaml")
    assert result.success is True
    assert _has_degraded_mark(result.warnings)


# ─── sim_config 层：真实 MJCF 直通无标记 ───


def test_real_mjcf_passthrough_has_no_mark() -> None:
    """真实 MJCF XML 直通（C13）不产生降级标记。"""
    result = SimConfigSkill().process(_MJCF, fmt="mjcf")
    assert result.success is True
    assert result.canonical_format == "xml"
    assert result.data_source_quality == "real"
    assert not _has_degraded_mark(result.warnings)


def test_rebuilt_mjcf_has_no_mark() -> None:
    """parse_mujoco → to_mjcf 重建分支（非完整 MJCF 的 XML）不产生降级标记。"""
    # 可被 parse_mujoco 解析、但非完整 MJCF（缺 <mujoco> 根/<worldbody>）→ 重建分支
    rebuilt_input = (
        b'<scene>'
        b'<geom name="box" type="box" size="0.1 0.1 0.1" pos="0 0 0.5"/>'
        b"</scene>"
    )
    result = SimConfigSkill().process(rebuilt_input, fmt="xml")
    assert result.success is True
    assert result.canonical_format == "xml"
    assert not _has_degraded_mark(result.warnings)


# ─── 装配层：SkillRegistry 透传标记 ───


def test_registry_assembly_preserves_mark() -> None:
    """python 输入经 SkillRegistry 装配后 ParsedItem.warnings 保留降级标记。"""
    raw = RawData(
        source=DataSource.KINOVA,
        item_id="franka",
        format="python",
        data=_PYTHON_CFG,
        url="https://example.com/franka.py",
        retrieved_at=_FIXED_TIME,
    )
    result = RetrievalResult(req_id="req_001", data=raw, status="success")
    req = DataReq(
        req_id="req_001",
        req_type=DataReqType.SIM_CONFIG,
        description="kinova sim",
        priority=Priority.REQUIRED,
    )
    outcome = SkillRegistry().process_retrieval_result(result, req)
    assert isinstance(outcome, ParsedItem)
    assert outcome.data_source_quality == "fallback"
    assert outcome.is_fallback is True
    assert _has_degraded_mark(outcome.warnings)


# ─── validate 层：带标记项呈现为 WARNING，真实 MJCF 不触发 ───


def _item_from_result(req_id: str, result, fmt: str) -> ParsedItem:
    return ParsedItem(
        req_id=req_id,
        req_type=DataReqType.SIM_CONFIG,
        name=req_id,
        canonical_format=result.canonical_format,
        output_path=result.output_path or "",
        data=result.data,
        provenance=_provenance(fmt),
        completeness_pct=result.completeness_pct,
        confidence_score=result.confidence_score,
        warnings=result.warnings,
        data_source_quality=result.data_source_quality,
        is_fallback=result.is_fallback,
    )


def test_validate_emits_warning_for_degraded_item() -> None:
    """带降级标记的产物在 validate 呈现为独立 WARNING，且不改变 passed 判定。"""
    res = SimConfigSkill().process(_PYTHON_CFG, fmt="python")
    item = _item_from_result("r1", res, "python")
    out = node_validate({"parsed_data": {"r1": item}})
    degraded = [
        i
        for i in out["validation_issues"]
        if i.req_id == "r1"
        and i.severity == Severity.WARNING
        and i.message.startswith(_DEGRADED_MARK)
    ]
    assert degraded, "降级场景标记未呈现为 WARNING"
    # 诚实标记不把「原本 passed」误判为 ERROR（最小 MJCF 非占位，不触发占位 ERROR）
    errs = [i for i in out["validation_issues"] if i.severity == Severity.ERROR]
    assert not errs


def test_validate_no_warning_for_real_mjcf() -> None:
    """真实 MJCF 直通产物不触发降级 WARNING。"""
    res = SimConfigSkill().process(_MJCF, fmt="mjcf")
    item = _item_from_result("r1", res, "mjcf")
    out = node_validate({"parsed_data": {"r1": item}})
    assert not any(
        i.message.startswith(_DEGRADED_MARK) for i in out["validation_issues"]
    )