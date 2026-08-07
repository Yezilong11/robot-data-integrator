# src/rdi/skills/paper_parse.py
"""PaperSkill — 学术论文 PDF 解析 Skill。

输入来自 arXiv / IEEE 等 Adapter 的 PDF 字节，使用 PyMuPDF 提取纯文本、
标题、作者等元数据，输出为结构化文本与元数据字典。
"""

import io
from typing import Any

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# 触发警告的最大页数阈值
_MAX_PAGES_WARNING = 100


class PaperSkill(BaseSkill):
    """论文 PDF 解析 Skill：提取文本与元数据。"""

    skill_name = "paper"

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """解析 PDF 字节，返回文本与元数据。

        Args:
            data: PDF 原始字节
            **kwargs: 额外参数（当前未使用）

        Returns:
            StandardResult，data 字段为 dict{"text": str, "metadata": dict}
        """
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
        if not text:
            issues.append(
                ValIssue(
                    severity=Severity.ERROR,
                    req_id="",
                    message="论文文本为空",
                )
            )
        if metadata.get("page_count", 0) == 0:
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
