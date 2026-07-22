# src/rdi/hermes/strategy.py
"""策略演化模块：根据历史统计数据调整数据源优先级。"""

import datetime
import os
from typing import Any

from rdi.adapters.registry import get_sources_for_type
from rdi.hermes.experience_db import ExperienceDB
from rdi.models import DataReqType, DataSource

_LOG_PATH = "data/hermes_evolution.log"


class StrategyEvolver:
    """数据源优先级策略演化器。

    定期检查各数据源成功率：成功率低于 50% 降级，高于 90% 且请求充足时提升。
    """

    def __init__(self, db: ExperienceDB) -> None:
        self.db = db
        self.last_evolve_time: datetime.datetime = datetime.datetime.min
        self.evolve_interval_hours: int = 6

    def maybe_evolve(self) -> None:
        """距上次演化超过 evolve_interval_hours 小时则执行 evolve，并刷新时间。"""
        now = datetime.datetime.now()
        if now - self.last_evolve_time < datetime.timedelta(hours=self.evolve_interval_hours):
            return
        self.evolve()
        self.last_evolve_time = now

    def evolve(self) -> None:
        """遍历数据源统计，对异常成功率记录演化日志。"""
        stats = self.db.get_source_stats()
        for stat in stats:
            total = stat.get("total_requests", 0)
            if total == 0:
                continue
            success_count = stat.get("success_count", 0)
            success_rate = success_count / total
            source_name = stat.get("source_name", "")
            if success_rate < 0.5:
                self._log_evolution(source_name, "deprioritize", f"success_rate={success_rate:.1%}")
            elif success_rate > 0.9 and total > 10:
                self._log_evolution(source_name, "promote", "high_reliability")

    def get_source_priority(self, req_type: str) -> list[str]:
        """按成功率降序返回 req_type 候选数据源名称列表。

        候选源通过 get_sources_for_type() 查询；
        统计中缺失或 total_requests 为 0 的源默认成功率 0.5。
        """
        try:
            req_enum = DataReqType(req_type)
        except ValueError:
            return []
        candidates = get_sources_for_type(req_enum)
        stats = self.db.get_source_stats()
        stat_map: dict[str, dict[str, Any]] = {stat.get("source_name", ""): stat for stat in stats}

        def rate(source_name: str) -> float:
            stat = stat_map.get(source_name)
            if stat is None:
                return 0.5
            total = int(stat.get("total_requests", 0))
            if total == 0:
                return 0.5
            return float(stat.get("success_count", 0)) / total

        ordered = sorted(candidates, key=rate, reverse=True)
        return ordered

    def _log_evolution(self, source: str, action: str, reason: str) -> None:
        """追加演化日志到 _LOG_PATH。"""
        os.makedirs(os.path.dirname(_LOG_PATH) or ".", exist_ok=True)
        entry = (
            f"[{datetime.datetime.now().isoformat()}] Hermes策略演化: "
            f"source={source}, action={action}, reason={reason}\n"
        )
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(entry)
