"""Hermes 持续学习引擎：经验注入、经验记录、策略演化、用户反馈。"""

from rdi.hermes.experience_db import ExperienceDB
from rdi.hermes.strategy import StrategyEvolver


class HermesEngine:
    """Hermes 持续学习引擎的对外接口。

    组合 ExperienceDB + StrategyEvolver，提供：
    1. 经验注入 — 查找前检索相似经验，格式化为 Prompt 注入片段
    2. 经验记录 — 查找后记录结果到经验库 + 更新统计 + 触发策略演化
    3. 用户反馈 — 记录用户对结果的反馈
    4. 数据源优先级 — 获取当前策略下排序后的候选源
    """

    def __init__(self) -> None:
        self.db = ExperienceDB()
        self.evolver = StrategyEvolver(self.db)

    def inject_experience(self, task_description: str, req_type: str) -> str:
        """检索相似历史经验并格式化为 Prompt 注入片段。

        无相似经验时返回空字符串；否则返回以空行开头的「历史经验参考」块，
        每条经验一行，document 截取前 60 字符。
        """
        experiences = self.db.retrieve_similar_experiences(task_description, top_k=5)
        if not experiences:
            return ""
        lines: list[str] = ["", "[历史经验参考]"]
        for exp in experiences:
            doc = exp["document"][:60]
            sources = ",".join(exp["sources_used"])
            lines.append(
                f"- 类似任务「{doc}...」: 状态={exp['result_status']}, "
                f"源={sources}, 耗时={exp['elapsed_seconds']:.1f}s"
            )
        return "\n".join(lines)

    def record_experience(
        self,
        task_desc: str,
        req_type: str,
        result_status: str,
        sources_used: list[str],
        elapsed_seconds: float,
    ) -> None:
        """记录一次任务经验：写入经验库、更新数据源统计、触发策略演化。"""
        self.db.store_experience(task_desc, req_type, result_status, sources_used, elapsed_seconds)
        success = result_status == "success"
        for source in sources_used:
            self.db.update_source_stats(
                source, req_type=req_type, success=success, elapsed_seconds=elapsed_seconds
            )
        self.evolver.maybe_evolve()

    def record_feedback(
        self,
        task_desc: str,
        feedback_type: str,
        feedback_content: str,
        corrected_value: str = "",
    ) -> None:
        """记录用户对任务结果的反馈。"""
        self.db.store_feedback(task_desc, feedback_type, feedback_content, corrected_value)

    def get_source_priority(self, req_type: str, candidates: list[str] | None = None) -> list[str]:
        """获取当前策略下 req_type 候选数据源的优先级排序。"""
        return self.evolver.get_source_priority(req_type, candidates=candidates)
