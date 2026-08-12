# src/rdi/exceptions.py
"""项目异常体系。

所有自定义异常继承自 RDIError，保证上层可以统一捕获。
禁止在代码中使用裸 `raise Exception`。

使用示例：
    raise AdapterError("Failed to fetch arXiv", source="arxiv", status_code=429)
"""


class RDIError(Exception):
    """项目基础异常，所有自定义异常的基类。"""

    message: str

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


# ─── 数据连接层异常（Adapter） ───


class AdapterError(RDIError):
    """数据源连接失败。

    由网络请求失败、API 返回错误状态码、数据格式异常等原因触发。

    Attributes:
        source: 数据源名称（如 "arxiv", "github"）
        status_code: HTTP 状态码（如有）
    """

    source: str
    status_code: int | None

    def __init__(self, message: str, source: str = "", status_code: int | None = None) -> None:
        super().__init__(message)
        self.source = source
        self.status_code = status_code

    def __str__(self) -> str:
        parts = [self.message]
        if self.source:
            parts.append(f"source={self.source}")
        if self.status_code is not None:
            parts.append(f"status={self.status_code}")
        return " | ".join(parts)


class AdapterTimeoutError(AdapterError):
    """数据源请求超时。"""


class AdapterRateLimitError(AdapterError):
    """数据源速率限制（HTTP 429）。"""


class AdapterNotFoundError(AdapterError):
    """数据源未找到匹配项（HTTP 404）。"""


class AdapterAuthError(AdapterError):
    """数据源认证失败（API Key 无效或过期）。"""


class AdapterCatalogError(AdapterError):
    """数据源硬编码清单未收录查询目标。

    与连接类错误（AdapterError）不同：数据源本身可达，但查询目标不在该源
    硬编码的已知目标清单内（有源但未收录），供上层生成可诊断的 missing 语义。
    """


# ─── 能力执行层异常（Skill） ───


class ParseError(RDIError):
    """数据解析失败。

    由 Skill 在处理原始数据时遇到无法解析的格式触发。

    Attributes:
        format_name: 原始格式名称（如 "URDF", "STL"）
        req_id: 关联的数据需求 ID
    """

    format_name: str
    req_id: str

    def __init__(self, message: str, format_name: str = "", req_id: str = "") -> None:
        super().__init__(message)
        self.format_name = format_name
        self.req_id = req_id

    def __str__(self) -> str:
        parts = [self.message]
        if self.format_name:
            parts.append(f"format={self.format_name}")
        if self.req_id:
            parts.append(f"req_id={self.req_id}")
        return " | ".join(parts)


class ValidationError(RDIError):
    """数据校验不通过。

    由校验规则引擎在检查数据质量时发现严重问题触发。

    Attributes:
        req_id: 关联的数据需求 ID
        issue_count: 校验问题数量
    """

    req_id: str
    issue_count: int

    def __init__(self, message: str, req_id: str = "", issue_count: int = 0) -> None:
        super().__init__(message)
        self.req_id = req_id
        self.issue_count = issue_count

    def __str__(self) -> str:
        parts = [self.message]
        if self.req_id:
            parts.append(f"req_id={self.req_id}")
        if self.issue_count:
            parts.append(f"issues={self.issue_count}")
        return " | ".join(parts)


# ─── 智能决策层异常（LLM） ───


class LLMUnavailableError(RDIError):
    """LLM 服务不可用。

    重试耗尽、API 返回错误、网络超时等场景触发。

    Attributes:
        model: 模型名称
        retry_count: 已重试次数
    """

    model: str
    retry_count: int

    def __init__(self, message: str, model: str = "", retry_count: int = 0) -> None:
        super().__init__(message)
        self.model = model
        self.retry_count = retry_count

    def __str__(self) -> str:
        parts = [self.message]
        if self.model:
            parts.append(f"model={self.model}")
        if self.retry_count:
            parts.append(f"retries={self.retry_count}")
        return " | ".join(parts)


class LLMParseError(LLMUnavailableError):
    """LLM 返回内容解析失败（JSON 格式错误或不符合 Schema）。"""


# ─── 配置层异常 ───


class ConfigurationError(RDIError):
    """配置错误。

    缺少必需的环境变量、配置文件格式错误、路径不可访问等。

    Attributes:
        key: 配置键名
    """

    key: str

    def __init__(self, message: str, key: str = "") -> None:
        super().__init__(message)
        self.key = key

    def __str__(self) -> str:
        parts = [self.message]
        if self.key:
            parts.append(f"key={self.key}")
        return " | ".join(parts)


# ─── 流程编排层异常（LangGraph） ───


class GraphExecutionError(RDIError):
    """工作流执行失败。

    由 LangGraph 节点运行时异常触发，封装底层错误。

    Attributes:
        node_name: 节点名称
    """

    node_name: str

    def __init__(self, message: str, node_name: str = "") -> None:
        super().__init__(message)
        self.node_name = node_name

    def __str__(self) -> str:
        parts = [self.message]
        if self.node_name:
            parts.append(f"node={self.node_name}")
        return " | ".join(parts)


# ─── 数据包异常 ───


class PackageError(RDIError):
    """数据包生成或操作失败。

    Attributes:
        output_dir: 输出目录路径
    """

    output_dir: str

    def __init__(self, message: str, output_dir: str = "") -> None:
        super().__init__(message)
        self.output_dir = output_dir

    def __str__(self) -> str:
        parts = [self.message]
        if self.output_dir:
            parts.append(f"output_dir={self.output_dir}")
        return " | ".join(parts)
