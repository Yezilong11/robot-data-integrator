# tests/unit/hermes/test_strategy.py
"""StrategyEvolver 单元测试。

用 Mock 替代真实 ExperienceDB，验证演化触发、日志写入与优先级排序。
"""

import datetime
from pathlib import Path
from typing import Any
from unittest.mock import Mock

import pytest

from rdi.hermes.experience_db import ExperienceDB
from rdi.hermes.strategy import StrategyEvolver


def make_db(stats: list[dict[str, Any]]) -> Mock:
    """构造 mock ExperienceDB，固定 get_source_stats 返回 stats。"""
    db = Mock(spec=ExperienceDB)
    db.get_source_stats.return_value = stats
    return db


def test_evolve_deprioritize_low_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """成功率 30% < 50% 时记录 deprioritize 日志。"""
    monkeypatch.chdir(tmp_path)
    db = make_db(
        [
            {
                "source_name": "github",
                "total_requests": 10,
                "success_count": 3,
                "avg_elapsed": 1.0,
                "last_updated": "",
            }
        ]
    )
    evolver = StrategyEvolver(db)
    evolver.evolve()
    log = (tmp_path / "data" / "hermes_evolution.log").read_text(encoding="utf-8")
    assert "deprioritize" in log
    assert "github" in log


def test_evolve_promote_high_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """成功率 93% > 90% 且 total>10 时记录 promote 日志。"""
    monkeypatch.chdir(tmp_path)
    db = make_db(
        [
            {
                "source_name": "arxiv",
                "total_requests": 15,
                "success_count": 14,
                "avg_elapsed": 0.5,
                "last_updated": "",
            }
        ]
    )
    evolver = StrategyEvolver(db)
    evolver.evolve()
    log = (tmp_path / "data" / "hermes_evolution.log").read_text(encoding="utf-8")
    assert "promote" in log
    assert "arxiv" in log


def test_get_source_priority_orders_by_success_rate() -> None:
    """arxiv 90% 成功率高于其他候选默认 0.5，应排在最前。

    paper 候选源为 [arxiv, ieee, paperswithcode]，github 不在其中，
    其统计仅作为无关上下文（验证非候选源被正确忽略）。
    """
    db = make_db(
        [
            {
                "source_name": "github",
                "total_requests": 10,
                "success_count": 4,
                "avg_elapsed": 1.0,
                "last_updated": "",
            },
            {
                "source_name": "arxiv",
                "total_requests": 10,
                "success_count": 9,
                "avg_elapsed": 0.5,
                "last_updated": "",
            },
        ]
    )
    evolver = StrategyEvolver(db)
    ordered = evolver.get_source_priority("paper")
    # arxiv 90% 应排在默认 0.5 的 ieee/paperswithcode 之前
    assert ordered[0] == "arxiv"
    # github 非候选源，不应出现在结果中
    assert "github" not in ordered


def test_maybe_evolve_respects_interval() -> None:
    """间隔未到不演化；间隔已到则演化。"""
    db = make_db([])
    evolver = StrategyEvolver(db)
    # 刚演化过：不触发 evolve
    evolver.last_evolve_time = datetime.datetime.now()
    evolver.maybe_evolve()
    assert db.get_source_stats.call_count == 0
    # 很久以前：触发 evolve
    evolver.last_evolve_time = datetime.datetime.min
    evolver.maybe_evolve()
    assert db.get_source_stats.call_count == 1
