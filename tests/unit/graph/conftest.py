"""graph 测试目录公共 fixture。

仓库 .env 配置了真实 LLM API key：任何测试只要走到 LLM 决策函数就会发起
真实请求（慢且非确定）。node_assemble 现会调用 explain_quality，本 autouse
fixture 全局兜底为 None（规则降级路径），保证测试离线可复现；
具体用例如需 LLM 成功路径，在用例内重新 monkeypatch 覆盖。
"""

import pytest


@pytest.fixture(autouse=True)
def _no_real_llm_explain_quality(monkeypatch: pytest.MonkeyPatch) -> None:
    """默认让质量解释决策走规则兜底，防止测试触发真实 LLM 请求。"""
    monkeypatch.setattr(
        "rdi.intelligence.decisions.explain_quality",
        lambda **kwargs: None,
    )
