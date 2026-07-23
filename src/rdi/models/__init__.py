# src/rdi/models/__init__.py
"""全局 Pydantic 数据模型。

所有模块通过此包导入模型，禁止从子模块直接导入。
"""

from .common import (
    DataReqType,
    DataSource,
    Priority,
    ProvenanceEntry,
    Severity,
    StandardResult,
    ValidationReport,
    ValIssue,
)
from .goal import DataReq, GoalSpec, PaperInfo
from .manifest import ManifestFile, ManifestMissingItem, PackageManifest, QualityReport
from .parsed import MissingItem, ParsedItem
from .retrieval import RawData, RetrievalError, RetrievalResult, SearchResult

__all__ = [
    # common
    "DataSource",
    "DataReqType",
    "Priority",
    "ProvenanceEntry",
    "Severity",
    "ValIssue",
    "ValidationReport",
    "StandardResult",
    # goal
    "GoalSpec",
    "DataReq",
    "PaperInfo",
    # retrieval
    "SearchResult",
    "RawData",
    "RetrievalResult",
    "RetrievalError",
    # parsed
    "ParsedItem",
    "MissingItem",
    # manifest
    "PackageManifest",
    "ManifestFile",
    "ManifestMissingItem",
    "QualityReport",
]
