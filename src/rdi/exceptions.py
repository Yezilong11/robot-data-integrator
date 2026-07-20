# src/rdi/exceptions.py
"""项目异常体系。

所有模块使用统一的异常类型，便于上层捕获和处理。
"""


class RDIError(Exception):
    """项目基础异常。"""

    def __init__(self, message: str = "") -> None:
        self.message = message
        super().__init__(self.message)


class AdapterError(RDIError):
    """数据源 Adapter 异常。

    当数据获取失败（超时、限流、认证失败等）时抛出。
    """

    def __init__(
        self,
        message: str = "",
        source: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.source = source
        self.status_code = status_code
        super().__init__(message)


class SkillError(RDIError):
    """Skill 处理异常。

    当数据解析或格式转换失败时抛出。
    """

    def __init__(
        self,
        message: str = "",
        skill_name: str | None = None,
        input_format: str | None = None,
    ) -> None:
        self.skill_name = skill_name
        self.input_format = input_format
        super().__init__(message)


class LLMError(RDIError):
    """LLM 调用异常。

    当千问模型调用失败时抛出。
    """

    def __init__(
        self,
        message: str = "",
        model: str | None = None,
        status_code: int | None = None,
    ) -> None:
        self.model = model
        self.status_code = status_code
        super().__init__(message)


class ValidationError(RDIError):
    """数据校验异常。

    当数据包校验失败时抛出。
    """

    def __init__(
        self,
        message: str = "",
        validation_errors: list[str] | None = None,
    ) -> None:
        self.validation_errors = validation_errors or []
        super().__init__(message)


class HermesError(RDIError):
    """Hermes 持续学习引擎异常。"""

    def __init__(
        self,
        message: str = "",
        component: str | None = None,
    ) -> None:
        self.component = component
        super().__init__(message)
