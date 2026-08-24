# src/rdi/skills/paper_parse.py
"""PaperSkill — 学术论文 PDF 解析 Skill。

输入来自 arXiv / IEEE 等 Adapter 的 PDF 字节，使用 PyMuPDF 提取纯文本、
标题、作者等元数据，输出为结构化文本与元数据字典。
"""

import io
import json
from typing import Any

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# 触发警告的最大页数阈值
_MAX_PAGES_WARNING = 100


class PaperSkill(BaseSkill):
    """论文 PDF 解析 Skill：提取文本与元数据。"""

    skill_name = "paper"

    def process(self, data: bytes, fmt: str | None = None, **kwargs: Any) -> StandardResult:
        """解析 PDF 字节，返回文本与元数据。

        Args:
            data: PDF 原始字节；``fmt=="json"`` 时为 fetch 层降级的 metadata JSON
            fmt: 原始数据格式（``pdf``/``json``）。Day2 回归：arxiv fetch 下载到损坏
                PDF 时显式降级返回 metadata JSON（``format=json``），本 Skill 此前
                忽略 ``fmt`` 仍把 JSON 字节当 PDF 打开，导致 "Failed to open stream"
                跨 4 轮复现（生产者已降级、消费者未适配）。
            **kwargs: 额外参数（当前未使用）

        Returns:
            StandardResult。pdf 路径返回 ``{"text","metadata"}``；
            json 降级路径返回 ``{"text":"", "metadata":meta}`` 并标记 ``is_fallback``。
        """
        if fmt == "json":
            return self._process_metadata(data)

        try:
            import fitz  # PyMuPDF
        except ImportError as exc:  # pragma: no cover
            return StandardResult(
                success=False,
                canonical_format="text",
                errors=[f"缺少 PyMuPDF 依赖: {exc}"],
            )

        if not data or len(data) == 0:
            return StandardResult(
                success=False,
                canonical_format="text",
                errors=["PDF 数据为空"],
            )

        try:
            doc = fitz.open(stream=io.BytesIO(data), filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            return StandardResult(
                success=False,
                canonical_format="text",
                errors=[f"无法打开 PDF: {exc}"],
            )

        warnings: list[str] = []
        if len(doc) > _MAX_PAGES_WARNING:
            warnings.append(f"PDF 页数较多 ({len(doc)} 页)，提取可能耗时")

        text_parts: list[str] = []
        for page in doc:
            page_text = page.get_text()
            if page_text:
                text_parts.append(page_text)
        full_text = "\n".join(text_parts).strip()

        metadata: dict[str, Any] = {
            "page_count": len(doc),
            "char_count": len(full_text),
            "title": doc.metadata.get("title", ""),
            "author": doc.metadata.get("author", ""),
            "subject": doc.metadata.get("subject", ""),
            "creator": doc.metadata.get("creator", ""),
        }
        doc.close()

        if not full_text:
            return StandardResult(
                success=False,
                canonical_format="text",
                errors=["PDF 未提取到文本（可能是扫描版或图片 PDF）"],
            )

        return StandardResult(
            success=True,
            canonical_format="text",
            data={"text": full_text, "metadata": metadata},
            completeness_pct=100.0,
            confidence_score=1.0,
            warnings=warnings,
        )

    def _process_metadata(self, data: bytes) -> StandardResult:
        """fetch 层显式降级的 metadata JSON：无 PDF 全文，装配为可用结果。

        降级契约：arxiv ``_metadata_fallback`` 返回含 arxiv_id/title/url/size
        等字段的 JSON；此处透传并标记 ``is_fallback``，判定按 PASS_WITH_FALLBACK。
        """
        try:
            meta = json.loads(data.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            return StandardResult(
                success=False,
                canonical_format="json",
                errors=[f"metadata JSON 解析失败: {exc}"],
            )
        return StandardResult(
            success=True,
            canonical_format="json",
            data={"text": "", "metadata": meta},
            completeness_pct=60.0,
            confidence_score=0.6,
            is_fallback=True,
            warnings=["PDF 不可用，返回元数据（fetch 显式降级）"],
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验论文解析结果。"""
        issues: list[ValIssue] = []
        if not result.success or result.data is None:
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id="",
                    message="论文解析失败",
                )
            )
            return ValidationReport(is_valid=False, issues=issues)

        text = result.data.get("text", "")
        metadata = result.data.get("metadata", {})
        # 降级路径（fetch 显式降级为 metadata JSON）没有 PDF 全文文本，
        # 空 text / 缺 page_count 是预期行为，不视为错误。
        if not text and not result.is_fallback:
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id="",
                    message="论文文本为空",
                )
            )
        if metadata.get("page_count", 0) == 0 and not result.is_fallback:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="",
                    message="无法获取 PDF 页数",
                )
            )

        return ValidationReport(
            is_valid=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            issues=issues,
            summary="论文解析校验通过" if not issues else f"发现 {len(issues)} 个问题",
        )
