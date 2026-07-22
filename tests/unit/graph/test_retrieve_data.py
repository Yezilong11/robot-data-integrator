"""retrieve_data 节点的单元测试。

验证骨架节点接入 Hermes 后：
1. 查找前调用 ``HermesEngine.inject_experience``；
2. 查找后调用 ``HermesEngine.record_experience``；
3. 仍返回占位 ``RetrievalResult``。
"""

from unittest.mock import Mock

import pytest

from rdi.graph.nodes.retrieve_data import node_retrieve_single


@pytest.fixture
def mock_hermes(monkeypatch: pytest.MonkeyPatch) -> Mock:
    """用 Mock 替换懒加载的 HermesEngine 单例。"""
    hermes = Mock()
    hermes.inject_experience.return_value = ""
    hermes.record_experience = Mock()
    monkeypatch.setattr("rdi.graph.nodes.retrieve_data._get_hermes_engine", lambda: hermes)
    return hermes


def test_retrieve_single_calls_hermes_inject_and_record(mock_hermes: Mock) -> None:
    """验证 inject_experience 与 record_experience 均被正确调用。"""
    payload = {
        "req_id": "req_000",
        "req_type": "code",
        "description": "查找代码",
        "keywords": ["test"],
    }
    result = node_retrieve_single(payload)

    # 验证 inject_experience 被调用
    mock_hermes.inject_experience.assert_called_once_with("查找代码", "code")

    # 验证 record_experience 被调用
    mock_hermes.record_experience.assert_called_once()
    call_kwargs = mock_hermes.record_experience.call_args.kwargs
    assert call_kwargs["task_desc"] == "查找代码"
    assert call_kwargs["req_type"] == "code"
    assert call_kwargs["result_status"] == "success"
    assert call_kwargs["sources_used"] == ["github"]
    assert call_kwargs["elapsed_seconds"] == 0.1

    # 验证返回结构正确
    assert "retrieval_results" in result
    assert "req_000" in result["retrieval_results"]
    assert result["retrieval_results"]["req_000"].status == "success"


def test_retrieve_single_returns_placeholder_result(mock_hermes: Mock) -> None:
    """验证骨架节点仍返回占位 RetrievalResult。"""
    payload = {
        "req_id": "req_001",
        "req_type": "robot_urdf",
        "description": "查找URDF",
        "keywords": [],
    }
    result = node_retrieve_single(payload)

    retrieval = result["retrieval_results"]["req_001"]
    assert retrieval.req_id == "req_001"
    assert retrieval.status == "success"
    assert retrieval.data is not None
    assert "provenance" in result
