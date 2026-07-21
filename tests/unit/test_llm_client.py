# tests/unit/test_llm_client.py
"""LLMClient 单元测试。

使用 respx mock OpenAI 兼容的 ``/chat/completions`` 端点，覆盖成功调用、
system 消息、结构化输出、JSON 解析失败、schema 不匹配、重试耗尽、重试后成功。
"""

import json
import time

import httpx
import pytest
import respx

from rdi.exceptions import LLMParseError, LLMUnavailableError
from rdi.intelligence.client import LLMClient
from rdi.models import GoalSpec

BASE_URL = "https://test.example.com/v1"
COMPLETIONS_URL = f"{BASE_URL}/chat/completions"


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> None:
    """time.sleep -> no-op, 避免重试测试变慢。"""
    monkeypatch.setattr(time, "sleep", lambda _: None)


def _make_client(max_retries: int = 3) -> LLMClient:
    """构造测试用 LLMClient，显式传参避免依赖真实 settings。"""
    return LLMClient(
        api_key="test-key",
        base_url=BASE_URL,
        model="test-model",
        max_retries=max_retries,
    )


def _ok_response(content: str) -> httpx.Response:
    """OpenAI 标准 200 响应。"""
    return httpx.Response(
        200,
        json={"choices": [{"message": {"content": content}, "finish_reason": "stop"}]},
    )


def _err_response() -> httpx.Response:
    """OpenAI 标准 500 错误响应。"""
    return httpx.Response(500, json={"error": {"message": "server error"}})


def test_call_success(no_sleep: None) -> None:
    """mock 200 响应，call 返回预期字符串。"""
    with respx.mock:
        respx.post(COMPLETIONS_URL).mock(return_value=_ok_response("hello world"))
        client = _make_client()
        assert client.call("你好") == "hello world"


def test_call_with_system(no_sleep: None) -> None:
    """验证 system 消息被正确发送。"""
    with respx.mock:
        route = respx.post(COMPLETIONS_URL).mock(return_value=_ok_response("ok"))
        client = _make_client()
        result = client.call("你好", system="你是助手")
        assert result == "ok"
        body = json.loads(route.calls[0].request.content)
        messages = body["messages"]
        assert messages[0] == {"role": "system", "content": "你是助手"}
        assert messages[-1] == {"role": "user", "content": "你好"}


def test_call_structured_success(no_sleep: None) -> None:
    """mock 返回合法 JSON，断言返回 GoalSpec 实例。"""
    payload = {"research_topic": "抓取实验", "experiment_type": "grasping"}
    with respx.mock:
        respx.post(COMPLETIONS_URL).mock(return_value=_ok_response(json.dumps(payload)))
        client = _make_client()
        result = client.call_structured("解析", GoalSpec)
        assert isinstance(result, GoalSpec)
        assert result.research_topic == "抓取实验"
        assert result.experiment_type == "grasping"


def test_call_structured_invalid_json(no_sleep: None) -> None:
    """mock 返回非法 JSON，断言抛 LLMParseError。"""
    with respx.mock:
        respx.post(COMPLETIONS_URL).mock(return_value=_ok_response("not json{"))
        client = _make_client()
        with pytest.raises(LLMParseError):
            client.call_structured("解析", GoalSpec)


def test_call_structured_schema_mismatch(no_sleep: None) -> None:
    """mock 返回合法 JSON 但缺必填字段，断言抛 LLMParseError。"""
    payload = {"experiment_type": "grasping"}
    with respx.mock:
        respx.post(COMPLETIONS_URL).mock(return_value=_ok_response(json.dumps(payload)))
        client = _make_client()
        with pytest.raises(LLMParseError):
            client.call_structured("解析", GoalSpec)


def test_call_retries_on_api_error(no_sleep: None) -> None:
    """mock 连续 500，断言重试 max_retries 次后抛 LLMUnavailableError。"""
    with respx.mock:
        route = respx.post(COMPLETIONS_URL).mock(return_value=_err_response())
        client = _make_client(max_retries=3)
        with pytest.raises(LLMUnavailableError) as exc_info:
            client.call("你好")
        assert exc_info.value.retry_count == 3
        assert route.call_count == 4  # 1 initial + 3 retries


def test_call_eventually_succeeds_after_retry(no_sleep: None) -> None:
    """mock 前两次 500 第三次 200，断言最终成功。"""
    with respx.mock:
        route = respx.post(COMPLETIONS_URL).mock(
            side_effect=[_err_response(), _err_response(), _ok_response("ok")]
        )
        client = _make_client(max_retries=3)
        assert client.call("你好") == "ok"
        assert route.call_count == 3
