"""DatasetSkill markdown 解析单元测试。

覆盖：
- fmt="markdown" / "md" 显式解析：标题、描述、file_tree 空、降级字段齐全
- fmt 未提供时按 markdown 特征嗅探（# / ## 开头）
- 非 markdown 内容 + fmt 未知 → 不支持格式
"""

from rdi.models.retrieval import RawReference
from rdi.skills.dataset_parse import DatasetSkill

_SAMPLE = b"""# YCB Video Dataset

This dataset contains 92 object instances captured with RGB-D sensors.

## Usage

Run the download script first.
"""


class TestDatasetMarkdown:
    def test_fields_complete(self) -> None:
        result = DatasetSkill().process(_SAMPLE, fmt="markdown", name="ycb")
        assert result.success is True
        assert result.canonical_format == "DatasetSummary"
        data = result.data
        assert data["title"] == "YCB Video Dataset"
        assert "92 object instances" in data["description"]
        assert data["file_tree"] == []
        assert result.is_fallback is True
        assert result.data_source_quality == "fallback"
        assert result.completeness_pct == 55
        assert result.confidence_score == 0.6
        assert result.warnings == ["仅数据集摘要（markdown），未下载数据文件"]
        assert result.output_path == "datasets/ycb.json"

    def test_md_alias(self) -> None:
        result = DatasetSkill().process(b"# Tiny\n\ndesc text\n", fmt="md")
        assert result.success is True
        assert result.data["title"] == "Tiny"
        assert result.data["description"] == "desc text"
        assert result.data["file_tree"] == []

    def test_sniff_header_without_title(self) -> None:
        result = DatasetSkill().process(b"## Overview\n\nBody paragraph\n")
        assert result.success is True
        assert result.data["title"] == ""
        assert result.data["description"] == "Body paragraph"
        assert result.is_fallback is True

    def test_sniff_true_h1(self) -> None:
        result = DatasetSkill().process(b"# AGX Dataset\n\nSome description\n")
        assert result.success is True
        assert result.data["title"] == "AGX Dataset"
        assert result.data["description"] == "Some description"

    def test_unknown_fmt_not_markdown_fails(self) -> None:
        result = DatasetSkill().process(b"just plain text without headers")
        assert result.success is False
        assert "不支持" in result.errors[0]


class TestDatasetFallbackDownloadGuide:
    """markdown 降级产物 download_guide 结构扩展（Task 8）。"""

    def test_fallback_with_reference_kwarg(self) -> None:
        """registry 透传 RawReference → 产物 data 顶层含 download_guide（wget 命令可见）。"""
        ref = RawReference(
            url="https://github.com/o/r/releases/download/v1/ycb.tar.gz",
            local_path="ycb.tar.gz",
            file_size=1024,
            reason="超过自动下载上限",
        )
        result = DatasetSkill().process(_SAMPLE, fmt="markdown", name="ycb", reference=ref)
        assert result.is_fallback is True
        data = result.data
        assert data["title"] == "YCB Video Dataset"  # 原字段保留
        guide = data["download_guide"]
        assert guide["status"] == "not_downloaded"
        assert guide["source_file_url"] == ref.url
        assert guide["file_size_bytes"] == 1024
        assert "超过自动下载上限" in guide["reason"]
        assert guide["method_hint"].startswith("wget ")
        assert guide["selected_by"]
        assert guide["alternatives"] == []

    def test_fallback_with_reference_dict(self) -> None:
        """reference 为等价 dict → download_guide 由引用构造。"""
        data = (
            DatasetSkill()
            .process(
                _SAMPLE,
                fmt="markdown",
                name="ycb",
                reference={
                    "url": "https://example.com/data.zip",
                    "local_path": "data.zip",
                    "file_size": 777,
                    "reason": "过大",
                },
            )
            .data
        )
        guide = data["download_guide"]
        assert guide["source_file_url"] == "https://example.com/data.zip"
        assert guide["file_size_bytes"] == 777
        assert guide["method_hint"] == "wget https://example.com/data.zip -O data.zip"

    def test_fallback_without_reference_keeps_original(self) -> None:
        """无引用 → 产物不含 download_guide（不回归）。"""
        data = DatasetSkill().process(_SAMPLE, fmt="markdown", name="ycb").data
        assert "download_guide" not in data
        assert data["file_tree"] == []
