# src/rdi/intelligence/client.py
"""OpenAI 兼容 LLM 客户端封装。

通过 ``llm_base_url`` 切换厂商（Qwen / DeepSeek / OpenAI 等），统一封装重试与
异常转换：所有 ``openai.OpenAIError`` 子类视为可重试错误，耗尽后抛
``LLMUnavailableError``；结构化输出的 JSON 解析失败抛 ``LLMParseError``。
"""

import time
from typing import Any, TypeVar, cast

from openai import OpenAI, OpenAIError
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from rdi.config import settings
from rdi.exceptions import LLMParseError, LLMUnavailableError

T = TypeVar("T", bound=BaseModel)


class LLMClient:
    """OpenAI 兼容 LLM 客户端。

    通过 ``settings.llm_base_url`` 切换厂商，对外提供 ``call`` / ``call_structured``
    两个方法。重试循环手写实现（ponytail：不引入 tenacity），固定 1 秒间隔。
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
        max_retries: int | None = None,
        temperature: float | None = None,
    ) -> None:
        # 允许显式传入覆盖 settings（便于测试）
        self._api_key = api_key if api_key is not None else settings.llm_api_key
        self._base_url = base_url if base_url is not None else settings.llm_base_url
        self._model = model if model is not None else settings.llm_model
        self._max_retries = max_retries if max_retries is not None else settings.llm_max_retries
        self._temperature = temperature if temperature is not None else settings.llm_temperature
        # API Key 缺失时抛 LLMUnavailableError（而非让 OpenAI SDK 抛原始报错），
        # 使上层降级逻辑能统一捕获。
        if not self._api_key:
            raise LLMUnavailableError(
                "LLM API Key 未配置（settings.llm_api_key 为空，请检查 .env 的 LLM_API_KEY）",
                model=self._model,
                retry_count=0,
            )
        # SDK 自带 max_retries=2 会与我们的手写重试叠加，故关闭内置重试
        self._client = OpenAI(
            api_key=self._api_key,
            base_url=self._base_url,
            max_retries=0,
        )

    def call(self, prompt: str, system: str | None = None) -> str:
        """普通文本调用，返回 LLM 生成的字符串。"""
        messages = self._build_messages(prompt, system)
        return self._invoke_with_retry(messages=messages)

    def call_structured(
        self,
        prompt: str,
        schema: type[T],
        system: str | None = None,
    ) -> T:
        """结构化输出调用，返回 Pydantic 模型实例。

        通过 ``response_format={"type": "json_object"}`` 让 LLM 返回 JSON，
        再用 ``schema.model_validate_json`` 解析；解析失败抛 ``LLMParseError``。
        """
        messages = self._build_messages(prompt, system)
        raw = self._invoke_with_retry(
            messages=messages,
            response_format={"type": "json_object"},
        )
        try:
            return schema.model_validate_json(raw)
        except PydanticValidationError as e:
            raise LLMParseError(
                f"LLM 返回的 JSON 不符合 schema: {e}; raw={raw[:200]}",
                model=self._model,
                retry_count=0,
            ) from e

    @staticmethod
    def _build_messages(prompt: str, system: str | None) -> list[dict[str, str]]:
        """构造 chat completion messages：system 非空时前置，user 始终在后。"""
        messages: list[dict[str, str]] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _invoke_with_retry(
        self,
        messages: list[dict[str, str]],
        response_format: dict[str, str] | None = None,
    ) -> str:
        """带重试的底层 ``chat.completions.create`` 调用。

        所有 ``OpenAIError`` 子类视为可重试；固定 1 秒间隔，达到 ``max_retries``
        后抛 ``LLMUnavailableError``。
        """
        last_err: OpenAIError | None = None
        # dict[str,str] 与 SDK 的 TypedDict 参数运行时兼容但 mypy 无法静态验证，
        # 故 cast(Any, ...) 让 overload 解析落到 stream=False 的 ChatCompletion 分支。
        sdk_messages: Any = cast("Any", messages)
        for attempt in range(self._max_retries + 1):
            try:
                if response_format is not None:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=sdk_messages,
                        temperature=self._temperature,
                        response_format=cast("Any", response_format),
                    )
                else:
                    response = self._client.chat.completions.create(
                        model=self._model,
                        messages=sdk_messages,
                        temperature=self._temperature,
                    )
                content = response.choices[0].message.content
                if content is None:
                    # LLM 返回 200 但 content 为空（极端情况），不重试直接报错
                    raise LLMUnavailableError(
                        "LLM 返回空 content",
                        model=self._model,
                        retry_count=attempt,
                    )
                return content
            except OpenAIError as e:
                last_err = e
                if attempt < self._max_retries:
                    time.sleep(1)
        raise LLMUnavailableError(
            f"LLM 调用失败，重试 {self._max_retries} 次后仍不可用: {last_err}",
            model=self._model,
            retry_count=self._max_retries,
        ) from last_err
