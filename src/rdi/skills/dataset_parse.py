"""DatasetSkill — 数据集元数据与压缩包解析 Skill。

输入来自 Zenodo / GraspNet / HuggingFace 等 Adapter 的原始字节，输出结构化的
``DatasetSummary``：标题、描述、下载链接、文件树与许可证。
"""

import io
import json
import re
import tarfile
import zipfile
from typing import Any

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill, extract_download_guide

_CANONICAL_FORMAT = "DatasetSummary"


def _extract_files(metadata: dict[str, Any]) -> list[str]:
    """从 metadata 中提取文件列表（支持 Zenodo files / HF siblings 等）。"""
    files: list[str] = []
    if isinstance(metadata.get("files"), list):
        for item in metadata["files"]:
            if isinstance(item, dict):
                name = item.get("key") or item.get("filename") or item.get("name", "")
                if name:
                    files.append(name)
            elif isinstance(item, str):
                files.append(item)
    if isinstance(metadata.get("siblings"), list):
        for item in metadata["siblings"]:
            if isinstance(item, dict) and item.get("rfilename"):
                files.append(item["rfilename"])
    return files


class DatasetSkill(BaseSkill):
    """数据集元数据解析 Skill：json / zip / tar → DatasetSummary。"""

    skill_name = "dataset"

    def _parse_json(self, data: bytes, kwargs: dict[str, Any]) -> StandardResult:
        """解析数据集 metadata JSON（Zenodo / HF / GraspNet）。"""
        try:
            metadata = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=[f"JSON 解析失败: {exc}"],
            )

        if not isinstance(metadata, dict):
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=["数据集 metadata 应为 JSON object"],
            )

        # Zenodo 字段
        title = (
            metadata.get("metadata", {}).get("title")
            or metadata.get("title")
            or metadata.get("name")
            or ""
        )
        description = (
            metadata.get("metadata", {}).get("description")
            or metadata.get("description")
            or metadata.get("summary")
            or ""
        )
        license_value = (
            (
                metadata.get("metadata", {}).get("license", {}).get("id")
                if isinstance(metadata.get("metadata", {}).get("license"), dict)
                else metadata.get("metadata", {}).get("license")
            )
            or metadata.get("license")
            or ""
        )

        # HF dataset_info / model_info 字段
        if not title:
            title = metadata.get("id") or metadata.get("modelId") or ""
        if not description:
            description = metadata.get("description") or ""

        # 下载链接
        download_url: str | None = None
        links = metadata.get("links", {})
        if isinstance(links, dict):
            download_url = (
                links.get("download")
                or links.get("self")
                or links.get("html")
                or links.get("latest_html")
            )
        if not download_url:
            download_url = metadata.get("download_url") or metadata.get("url")
        if isinstance(download_url, list):
            download_url = download_url[0] if download_url else None

        file_tree = kwargs.get("file_tree") or _extract_files(metadata)
        if isinstance(file_tree, str):
            file_tree = [file_tree]

        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data={
                "title": title,
                "description": description,
                "download_url": download_url,
                "file_tree": list(file_tree),
                "license": license_value or None,
            },
            output_path=self._output_path(kwargs),
            completeness_pct=100.0 if title and description else 75.0,
            confidence_score=1.0 if title else 0.85,
            warnings=[] if title else ["数据集 metadata 缺少标题"],
        )

    def _parse_archive(self, data: bytes, fmt: str, kwargs: dict[str, Any]) -> StandardResult:
        """解析 zip / tar 压缩包，列出文件树并尝试读取内部 metadata JSON。"""
        file_tree: list[str] = []
        metadata_bytes: bytes | None = None
        try:
            if fmt == "zip":
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    for info in zf.infolist():
                        if info.file_size:
                            file_tree.append(info.filename)
                            lower = info.filename.lower()
                            if metadata_bytes is None and (
                                lower.endswith("metadata.json")
                                or lower.endswith("dataset_info.json")
                            ):
                                metadata_bytes = zf.read(info.filename)
            else:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                    for member in tf.getmembers():
                        if member.isfile():
                            file_tree.append(member.name)
                            lower = member.name.lower()
                            if metadata_bytes is None and (
                                lower.endswith("metadata.json")
                                or lower.endswith("dataset_info.json")
                            ):
                                metadata_file = tf.extractfile(member)
                                if metadata_file is not None:
                                    metadata_bytes = metadata_file.read()
        except (zipfile.BadZipFile, tarfile.TarError, OSError) as exc:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=[f"压缩包解析失败: {exc}"],
            )

        if not file_tree:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=["压缩包为空或不含文件"],
            )

        if metadata_bytes:
            inner = self._parse_json(metadata_bytes, kwargs)
            if inner.success and inner.data:
                inner.data["file_tree"] = file_tree
                inner.output_path = self._output_path(kwargs)
                return inner

        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data={
                "title": kwargs.get("title", ""),
                "description": kwargs.get("description", ""),
                "download_url": kwargs.get("download_url"),
                "file_tree": file_tree,
                "license": kwargs.get("license") or None,
            },
            output_path=self._output_path(kwargs),
            completeness_pct=70.0,
            confidence_score=0.8,
            warnings=["压缩包中未找到 metadata JSON，仅返回文件树"],
        )

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """处理数据集原始数据，返回 ``DatasetSummary``。

        Args:
            data: 原始数据字节
            **kwargs: ``fmt`` 显式格式；``name`` 输出名；``title`` / ``description`` /
                ``download_url`` / ``license`` 元数据覆盖；``file_tree`` 预计算文件树

        Returns:
            ``StandardResult``，失败时 ``success=False``、``data=None``
        """
        if not data:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=["数据为空"],
            )

        fmt = kwargs.get("fmt", "").lower()
        if fmt == "json":
            return self._parse_json(data, kwargs)

        if fmt in ("zip", "tar", "tar.gz", "tgz"):
            archive_fmt = "tar" if fmt.startswith("tar") or fmt == "tgz" else "zip"
            return self._parse_archive(data, archive_fmt, kwargs)

        if fmt in ("markdown", "md"):
            return self._parse_markdown(data, kwargs)

        if not fmt and self._is_markdown_text(data):
            return self._parse_markdown(data, kwargs)

        return StandardResult(
            success=False,
            canonical_format=_CANONICAL_FORMAT,
            errors=[f"不支持的数据集格式: {fmt}"],
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验 DatasetSkill 处理结果。"""
        if not result.success or result.data is None:
            return ValidationReport(
                is_valid=False,
                issues=[
                    ValIssue(
                        severity=Severity.ERROR,
                        req_id="dataset",
                        message="数据集解析失败",
                    )
                ],
                summary="数据集解析失败",
            )

        issues: list[ValIssue] = []
        data = result.data
        if not data.get("title"):
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="dataset",
                    message="数据集标题为空",
                )
            )
        if not data.get("description"):
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="dataset",
                    message="数据集描述为空",
                )
            )

        return ValidationReport(
            is_valid=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            issues=issues,
            summary="数据集解析校验通过" if not issues else f"发现 {len(issues)} 个问题",
        )

    @staticmethod
    def _output_path(kwargs: dict[str, Any]) -> str | None:
        name = kwargs.get("name")
        if isinstance(name, str) and name:
            return f"datasets/{name}.json"
        return None

    def _parse_markdown(self, data: bytes, kwargs: dict[str, Any]) -> StandardResult:
        """解析 markdown 格式的数据集摘要，仅提取标题与描述（占位/降级结果）。

        存在下载引用（数据内嵌 download_guide 或 registry 透传 ``reference``，见
        ``extract_download_guide``）时，产物 data 顶层附加 download_guide（含 wget
        命令）；无引用时保持原结构（不回归）。
        """
        text = data.decode("utf-8", errors="replace")
        lines = text.splitlines()

        title = ""
        for line in lines:
            if line.startswith("# ") and line[2:].strip():
                title = line[2:].strip()
                break

        description = ""
        for line in lines:
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                description = stripped
                break

        result_data: dict[str, Any] = {
            "title": title,
            "description": description,
            "download_url": None,
            "file_tree": [],
            "license": None,
        }
        guide = extract_download_guide(data, kwargs)
        if guide is not None:
            result_data["download_guide"] = guide
        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data=result_data,
            output_path=self._output_path(kwargs),
            is_fallback=True,
            data_source_quality="fallback",
            completeness_pct=55,
            confidence_score=0.6,
            warnings=["仅数据集摘要（markdown），未下载数据文件"],
        )

    @staticmethod
    def _is_markdown_text(data: bytes) -> bool:
        """粗略嗅探内容是否为 markdown 文本（以 # 标题行开头）。"""
        head = data.decode("utf-8", errors="ignore").lstrip()
        return bool(re.match(r"^#{1,6}\s", head))
