# tests/unit/test_logging.py
"""Task 16 (E2)：LOG_LEVEL / LOG_FORMAT 接线与五个关键节点日志点测试。

验证：
- configure_logging 从 settings.log_level / log_format 读取并生效（json/console）；
- 五个关键节点（retrieve_data / parse_convert / validate / assemble / human_review）
  每 req / 每节点输出含 req_id、source、耗时、状态的结构化日志；
- 日志级别过滤按 LOG_LEVEL 生效。
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING, Any
from unittest.mock import AsyncMock, Mock

import structlog

from rdi.config.settings import settings
from rdi.graph.nodes import (
    assemble,
    human_review,
    parse_convert,
    retrieve_data,
    validate,
)
from rdi.logging import configure_logging
from rdi.models import (
    DataReq,
    DataReqType,
    DataSource,
    Priority,
    RawData,
    RetrievalResult,
    SearchResult,
)

if TYPE_CHECKING:
    import pytest


def _json_records(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    """把 caplog 中 JSON 渲染的记录解析为事件 dict；跳过非 JSON 记录。"""
    out: list[dict[str, Any]] = []
    for record in caplog.records:
        try:
            out.append(json.loads(record.getMessage()))
        except (TypeError, json.JSONDecodeError):
            continue
    return out


def _events(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [d.get("event", "") for d in _json_records(caplog)]


# ─── LOG_LEVEL / LOG_FORMAT 接线 ───


def test_configure_logging_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """settings.log_level → root level；settings.log_format → renderer 选择。"""
    monkeypatch.setattr(settings, "log_level", "WARNING")
    monkeypatch.setattr(settings, "log_format", "console")
    configure_logging()

    assert logging.getLogger().level == logging.WARNING
    processors = structlog.get_config()["processors"]
    assert isinstance(processors[-1], structlog.dev.ConsoleRenderer)


def test_configure_logging_json_renderer() -> None:
    """fmt=json 时启用 JSONRenderer。"""
    configure_logging(fmt="json", level="DEBUG")
    processors = structlog.get_config()["processors"]
    assert isinstance(processors[-1], structlog.processors.JSONRenderer)


def test_log_level_filters_info(caplog: pytest.LogCaptureFixture) -> None:
    """LOG_LEVEL=ERROR 时 info 级节点日志被过滤。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="ERROR")
    validate.node_validate({})
    assert "validate.done" not in _events(caplog)


def test_console_format_output(caplog: pytest.LogCaptureFixture) -> None:
    """fmt=console 时输出人类可读 key=value，仍含事件名。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="console", level="DEBUG")
    validate.node_validate({})
    assert "validate.done" in caplog.text


# ─── retrieve_data：成功 / missing 日志点 ───


def _mock_hermes(monkeypatch: pytest.MonkeyPatch) -> Mock:
    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.record_experience = Mock()
    hermes.get_source_priority.return_value = ["github"]
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)
    return hermes


async def test_retrieve_data_logs_success_json(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve 成功：retrieve.success 含 req_id / source / 耗时 / 状态。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    _mock_hermes(monkeypatch)

    mock_adapter = AsyncMock()
    mock_adapter.search.return_value = [
        SearchResult(item_id="t-1", title="T", source=DataSource.GITHUB)
    ]
    mock_adapter.fetch.return_value = RawData(
        source=DataSource.GITHUB,
        item_id="t-1",
        format="json",
        data=b"x",
        url="https://example.com",
    )
    mock_cls = Mock(return_value=mock_adapter)
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data.select_adapter", lambda req_type: [mock_cls])
    # 该测试只关心日志点；mock 掉检索策略决策层（真实 adapter 的 source.value 为 str，
    # 此处 Mock 的 source.value 不是 str，且避免触发真实 LLM 请求）
    monkeypatch.setattr("rdi.intelligence.decisions.plan_retrieval", lambda **kwargs: None)

    payload = {"req_id": "req_log", "req_type": "code", "description": "d", "keywords": []}
    await retrieve_data.node_retrieve_single(payload)

    records = _json_records(caplog)
    success = next(d for d in records if d["event"] == "retrieve.success")
    assert success["req_id"] == "req_log"
    assert success["req_type"] == "code"
    assert success["status"] == "success"
    assert success["source"] == "github"
    assert success["elapsed_seconds"] >= 0
    # 每 req 开始也记录
    assert any(d["event"] == "retrieve.start" and d["req_id"] == "req_log" for d in records)


async def test_retrieve_data_logs_missing_json(
    caplog: pytest.LogCaptureFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    """retrieve missing（无内置数据源）：retrieve.missing 含 req_id / 状态 / 原因。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    _mock_hermes(monkeypatch)

    payload = {"req_id": "req_new", "req_type": "camera_calib", "description": "d", "keywords": []}
    await retrieve_data.node_retrieve_single(payload)

    missing = [
        d
        for d in _json_records(caplog)
        if d["event"] == "retrieve.missing" and d["req_id"] == "req_new"
    ]
    assert missing
    assert missing[-1]["status"] == "missing"


# ─── parse_convert：每 req 状态日志点 ───


def test_parse_convert_logs_item_status(caplog: pytest.LogCaptureFixture) -> None:
    """parse_convert.item 含 req_id / req_type / skill / 状态；done 汇总。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    req = DataReq(
        req_id="r1",
        req_type=DataReqType.MESH,
        description="mesh",
        priority=Priority.REQUIRED,
    )
    state = {
        "data_requirements": [req],
        "retrieval_results": {
            "r1": RetrievalResult(
                req_id="r1",
                status="success",
                data=RawData(source=DataSource.GITHUB, item_id="x", format="stl", data=b"bad"),
            )
        },
    }
    parse_convert.node_parse_convert(state)

    records = _json_records(caplog)
    item = next(d for d in records if d["event"] == "parse_convert.item")
    assert item["req_id"] == "r1"
    assert item["req_type"] == "mesh"
    assert item["status"] == "missing"  # 无效 stl 数据 → MissingItem
    assert item["elapsed_seconds"] >= 0
    done = next(d for d in records if d["event"] == "parse_convert.done")
    assert done["parsed"] == 0
    assert done["missing"] == 1


# ─── validate：每 req / 节点汇总日志点 ───


def test_validate_logs_done(caplog: pytest.LogCaptureFixture) -> None:
    """validate.done 汇总 parsed / issues / errors / iteration。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    validate.node_validate({})

    records = _json_records(caplog)
    done = next(d for d in records if d["event"] == "validate.done")
    assert done["parsed"] == 0
    assert done["issues"] == 0
    assert done["iteration"] == 1
    assert done["elapsed_seconds"] >= 0


# ─── assemble：数据包汇总日志点 ───


def test_assemble_logs_done(
    caplog: pytest.LogCaptureFixture,
    tmp_path: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """assemble.done 含 package_id / files / missing / status。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    monkeypatch.setattr(settings, "output_dir", str(tmp_path))
    assemble.node_assemble({})

    records = _json_records(caplog)
    done = next(d for d in records if d["event"] == "assemble.done")
    assert done["package_id"].startswith("package-")
    assert done["files"] == 0
    assert done["missing"] == 0
    assert done["status"] == "failed"
    assert done["elapsed_seconds"] >= 0


# ─── human_review：决策日志点 ───


def test_human_review_logs_decision(caplog: pytest.LogCaptureFixture) -> None:
    """human_review.decision 含 decision / iteration / forced。"""
    caplog.set_level(logging.DEBUG)
    configure_logging(fmt="json", level="DEBUG")
    human_review.node_human_review({"user_goal": "g", "provenance": []})

    records = _json_records(caplog)
    decision = next(d for d in records if d["event"] == "human_review.decision")
    assert decision["decision"] == "satisfied"
    assert decision["iteration"] == 0
    assert decision["forced"] is False
