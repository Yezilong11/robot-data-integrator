"""CodeSkill — 代码仓库（README / 配置文件 / 压缩包）解析 Skill。

输入来自 GitHub / HuggingFace 等 Adapter 的原始字节，输出结构化的
``CodeRepoSummary``：仓库地址、README 文本、文件树、框架与安装说明。
"""

import io
import json
import re
import tarfile
import zipfile
from typing import Any

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

# 常见框架关键词 -> 框架名
_FRAMEWORK_MARKERS: dict[str, str] = {
    # 更具体的框架优先于通用深度学习框架
    "huggingface": "huggingface",
    "transformers": "huggingface",
    "ros": "ros",
    "rospy": "ros",
    "package.xml": "ros",
    "mujoco": "mujoco",
    "isaac": "isaac",
    "isaacgym": "isaac",
    "isaacsim": "isaac",
    "pinocchio": "pinocchio",
    "drake": "drake",
    "open3d": "open3d",
    "pytorch": "pytorch",
    "torch": "pytorch",
    "tensorflow": "tensorflow",
    "tf.": "tensorflow",
    "keras": "keras",
    "jax": "jax",
    "flax": "flax",
}

# 安装相关章节标题
_INSTALLATION_HEADERS = frozenset(
    {
        "installation",
        "install",
        "setup",
        "getting started",
        "quick start",
        "environment",
        "dependencies",
    }
)

_CANONICAL_FORMAT = "CodeRepoSummary"


def _detect_framework(text: str, file_tree: list[str]) -> str | None:
    """根据文本内容与文件树推断框架；无法推断时返回 None。"""
    haystack = (text or "").lower()
    for marker, framework in _FRAMEWORK_MARKERS.items():
        if marker in haystack:
            return framework
    for path in file_tree:
        lower = path.lower()
        if lower.endswith("package.xml"):
            return "ros"
        if lower.endswith("requirements.txt"):
            return "python"
        if lower.endswith("setup.py") or lower.endswith("pyproject.toml"):
            return "python"
        if "cmakelists.txt" in lower:
            return "cpp"
        if lower.endswith("cargo.toml"):
            return "rust"
    return None


def _extract_markdown_title(text: str) -> str:
    """提取第一个 # 标题。"""
    match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else ""


def _extract_installation(text: str) -> str:
    """提取 Installation / Setup 章节文本（下一个同级标题前）。"""
    pattern = re.compile(
        r"^#{1,3}\s*(?:"
        + "|".join(re.escape(h) for h in _INSTALLATION_HEADERS)
        + r")\s*\n(.*?)(?=\n^#{1,3}\s|\Z)",
        re.MULTILINE | re.IGNORECASE | re.DOTALL,
    )
    match = pattern.search(text)
    if not match:
        return ""
    section = match.group(1).strip()
    # 保留前 2000 字符，避免过长
    return section[:2000]


def _infer_repo_url(kwargs: dict[str, Any]) -> str:
    """从 kwargs 获取 repo_url；支持 url / repo_url / source_url。"""
    for key in ("repo_url", "url", "source_url"):
        value = kwargs.get(key)
        if isinstance(value, str) and value:
            return value
    return ""


class CodeSkill(BaseSkill):
    """代码仓库解析 Skill：README / HF config / zip / tar → CodeRepoSummary。"""

    skill_name = "code"

    def _parse_markdown(self, text: str, kwargs: dict[str, Any]) -> StandardResult:
        """解析 Markdown README。"""
        title = _extract_markdown_title(text)
        installation = _extract_installation(text)
        file_tree: list[str] = kwargs.get("file_tree") or []
        if isinstance(file_tree, str):
            file_tree = [file_tree]
        framework = kwargs.get("framework")
        if not isinstance(framework, str):
            framework = _detect_framework(text, file_tree)

        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data={
                "repo_url": _infer_repo_url(kwargs),
                "readme_text": text.strip(),
                "file_tree": list(file_tree),
                "framework": framework,
                "installation": installation or None,
            },
            output_path=self._output_path(kwargs),
            completeness_pct=100.0 if title else 80.0,
            confidence_score=1.0 if title else 0.9,
            warnings=[] if title else ["README 未识别到标题"],
        )

    def _parse_json(self, data: bytes, kwargs: dict[str, Any]) -> StandardResult:
        """解析 HuggingFace 等模型/代码配置 JSON。"""
        try:
            config = json.loads(data.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            return StandardResult(
                success=False,
                canonical_format=_CANONICAL_FORMAT,
                errors=[f"JSON 解析失败: {exc}"],
            )

        # HF model_info / dataset_info 常见字段
        title = config.get("id") or config.get("modelId") or config.get("name") or ""
        description = (
            config.get("description")
            or config.get("summary")
            or config.get("card_data", {}).get("text", "")
            or ""
        )
        tags = config.get("tags", [])
        pipeline_tag = config.get("pipeline_tag", "")
        library_name = config.get("library_name", "")

        framework = kwargs.get("framework")
        if not isinstance(framework, str):
            framework = _detect_framework(
                " ".join([title, description, *tags, pipeline_tag, library_name]),
                [],
            )
        task = pipeline_tag or (tags[0] if tags else None)

        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data={
                "repo_url": _infer_repo_url(kwargs) or config.get("url", ""),
                "readme_text": description or f"{title} — {task or 'unknown task'}",
                "file_tree": [],
                "framework": framework,
                "installation": None,
            },
            output_path=self._output_path(kwargs),
            completeness_pct=80.0,
            confidence_score=0.9,
            warnings=["JSON 配置仅含元数据，无文件树"],
        )

    def _parse_archive(self, data: bytes, fmt: str, kwargs: dict[str, Any]) -> StandardResult:
        """解析 zip / tar 压缩包，列出文件树并尝试提取 README。"""
        file_tree: list[str] = []
        readme_text = ""
        try:
            if fmt == "zip":
                with zipfile.ZipFile(io.BytesIO(data)) as zf:
                    file_tree = [info.filename for info in zf.infolist() if info.file_size]
                    for name in file_tree:
                        lower = name.lower()
                        if lower.endswith("readme.md") or lower.endswith("readme"):
                            readme_text = zf.read(name).decode("utf-8", errors="ignore")
                            break
            else:
                with tarfile.open(fileobj=io.BytesIO(data), mode="r:*") as tf:
                    for member in tf.getmembers():
                        if member.isfile():
                            file_tree.append(member.name)
                            lower = member.name.lower()
                            if lower.endswith("readme.md") or lower.endswith("readme"):
                                readme_file = tf.extractfile(member)
                                if readme_file is not None:
                                    readme_text = readme_file.read().decode(
                                        "utf-8", errors="ignore"
                                    )
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

        framework = kwargs.get("framework")
        if not isinstance(framework, str):
            framework = _detect_framework(readme_text, file_tree)
        installation = _extract_installation(readme_text) if readme_text else ""

        return StandardResult(
            success=True,
            canonical_format=_CANONICAL_FORMAT,
            data={
                "repo_url": _infer_repo_url(kwargs),
                "readme_text": readme_text.strip(),
                "file_tree": file_tree,
                "framework": framework,
                "installation": installation or None,
            },
            output_path=self._output_path(kwargs),
            completeness_pct=100.0 if readme_text else 85.0,
            confidence_score=1.0 if readme_text else 0.9,
            warnings=[] if readme_text else ["压缩包中未找到 README"],
        )

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """处理代码相关原始数据，返回 ``CodeRepoSummary``。

        Args:
            data: 原始数据字节
            **kwargs: ``fmt`` 显式格式；``name`` 输出名；``url`` / ``repo_url``
                仓库地址；``framework`` 强制框架；``file_tree`` 预计算文件树

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
        if fmt in ("markdown", "md", "txt"):
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError as exc:
                return StandardResult(
                    success=False,
                    canonical_format=_CANONICAL_FORMAT,
                    errors=[f"README 解码失败: {exc}"],
                )
            return self._parse_markdown(text, kwargs)

        if fmt == "json":
            return self._parse_json(data, kwargs)

        if fmt in ("zip", "tar", "tar.gz", "tgz"):
            # tar.gz / tgz 统一用 tar 路径处理
            archive_fmt = "tar" if fmt.startswith("tar") or fmt == "tgz" else "zip"
            return self._parse_archive(data, archive_fmt, kwargs)

        return StandardResult(
            success=False,
            canonical_format=_CANONICAL_FORMAT,
            errors=[f"不支持的代码格式: {fmt}"],
        )

    def validate(self, result: StandardResult) -> ValidationReport:
        """校验 CodeSkill 处理结果。"""
        if not result.success or result.data is None:
            return ValidationReport(
                is_valid=False,
                issues=[
                    ValIssue(
                        severity=Severity.ERROR,
                        req_id="code",
                        message="代码解析失败",
                    )
                ],
                summary="代码解析失败",
            )

        issues: list[ValIssue] = []
        data = result.data
        if not data.get("readme_text"):
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="code",
                    message="README 文本为空",
                )
            )
        if not data.get("framework"):
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="code",
                    message="未识别到框架",
                )
            )

        return ValidationReport(
            is_valid=len([i for i in issues if i.severity == Severity.ERROR]) == 0,
            issues=issues,
            summary="代码解析校验通过" if not issues else f"发现 {len(issues)} 个问题",
        )

    @staticmethod
    def _output_path(kwargs: dict[str, Any]) -> str | None:
        name = kwargs.get("name")
        if isinstance(name, str) and name:
            return f"scripts/{name}.json"
        return None
