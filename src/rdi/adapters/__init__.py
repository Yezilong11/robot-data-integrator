"""数据连接层：数据源 Adapter 与注册表。"""

from .registry import ADAPTER_REGISTRY, get_sources_for_type, select_adapter

__all__ = ["ADAPTER_REGISTRY", "get_sources_for_type", "select_adapter"]
