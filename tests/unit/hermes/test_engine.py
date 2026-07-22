"""HermesEngine 单元测试。

用 monkeypatch 替换 ExperienceDB 和 StrategyEvolver 构造函数，
使 HermesEngine.__init__ 创建 Mock 对象，避免真实 ChromaDB 副作用。
"""

from unittest.mock import Mock

import pytest

from rdi.hermes.engine import HermesEngine


@pytest.fixture
def engine(monkeypatch: pytest.MonkeyPatch) -> HermesEngine:
    """构造 HermesEngine，db 和 evolver 均为 Mock 对象。"""
    monkeypatch.setattr("rdi.hermes.engine.ExperienceDB", lambda *a, **kw: Mock())
    monkeypatch.setattr("rdi.hermes.engine.StrategyEvolver", lambda *a, **kw: Mock())
    return HermesEngine()


def test_inject_experience_with_results(engine: HermesEngine) -> None:
    """有相似经验时返回包含历史经验参考的格式化字符串。"""
    engine.db.retrieve_similar_experiences.return_value = [
        {
            "document": "查找Franka Panda URDF模型",
            "result_status": "success",
            "sources_used": ["franka", "github"],
            "elapsed_seconds": 1.5,
        }
    ]
    result = engine.inject_experience("查找URDF", "robot_urdf")
    assert "[历史经验参考]" in result
    assert "状态=success" in result
    assert "源=franka,github" in result
    assert "耗时=1.5s" in result


def test_inject_experience_empty(engine: HermesEngine) -> None:
    """无相似经验时返回空字符串。"""
    engine.db.retrieve_similar_experiences.return_value = []
    result = engine.inject_experience("test", "code")
    assert result == ""


def test_record_experience_calls_store_and_update_and_evolve(engine: HermesEngine) -> None:
    """record_experience 应调用 store_experience、每个源的 update_source_stats、maybe_evolve。"""
    engine.record_experience("test", "code", "success", ["github", "arxiv"], 2.0)

    engine.db.store_experience.assert_called_once_with(
        "test", "code", "success", ["github", "arxiv"], 2.0
    )
    assert engine.db.update_source_stats.call_count == 2
    called_sources = {call.args[0] for call in engine.db.update_source_stats.call_args_list}
    assert called_sources == {"github", "arxiv"}
    for call in engine.db.update_source_stats.call_args_list:
        assert call.kwargs["success"] is True
        assert call.kwargs["elapsed_seconds"] == 2.0
    engine.evolver.maybe_evolve.assert_called_once()


def test_record_feedback_delegates(engine: HermesEngine) -> None:
    """record_feedback 应委托给 db.store_feedback。"""
    engine.record_feedback("test", "missing", "缺少URDF文件", "手动提供路径")
    engine.db.store_feedback.assert_called_once_with(
        "test", "missing", "缺少URDF文件", "手动提供路径"
    )
