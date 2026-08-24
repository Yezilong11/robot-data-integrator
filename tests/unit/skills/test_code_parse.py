"""CodeSkill 单元测试（同步）。

覆盖 spec「CODE Skill」全部 scenario：
- markdown README 解析（标题、框架、安装说明、文件树）
- JSON 配置解析（HF model_info）
- zip / tar 压缩包解析（文件树 + README 提取）
- 空数据 / 不支持的格式 / 损坏的压缩包 降级
- validate 对缺失 README / 框架的 WARNING
"""

import io
import tarfile
import zipfile
from pathlib import Path

from rdi.models.common import Severity, StandardResult
from rdi.skills.code_parse import CodeSkill

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "code"


def _read(name: str) -> bytes:
    return (_SAMPLE_DIR / name).read_bytes()


# ─── Scenario: README markdown 解析 ───


class TestCodeMarkdown:
    def test_readme_parses_to_code_repo_summary(self) -> None:
        result = CodeSkill().process(
            _read("README.md"),
            fmt="markdown",
            url="https://github.com/justagist/panda_simulator",
            name="panda_simulator",
        )
        assert result.success is True
        assert result.canonical_format == "CodeRepoSummary"
        data = result.data
        assert data["repo_url"] == "https://github.com/justagist/panda_simulator"
        assert data["readme_text"].startswith("# Panda Simulator")
        assert data["framework"] == "pytorch"
        assert "pip install" in (data["installation"] or "")
        assert result.output_path == "scripts/panda_simulator.json"
        assert result.confidence_score == 1.0

    def test_readme_without_title_degrades(self) -> None:
        result = CodeSkill().process(
            b"Some plain text without heading.\n",
            fmt="markdown",
            url="https://example.com/repo",
        )
        assert result.success is True
        assert result.completeness_pct < 100.0
        assert result.confidence_score < 1.0
        assert any("标题" in w for w in result.warnings)


# ─── Scenario: JSON 配置解析 ───


class TestCodeJson:
    def test_hf_config_parses(self) -> None:
        result = CodeSkill().process(
            _read("hf_config.json"),
            fmt="json",
            name="bert-base",
        )
        assert result.success is True
        assert result.canonical_format == "CodeRepoSummary"
        data = result.data
        assert "BERT base model" in data["readme_text"]
        assert data["framework"] == "huggingface"
        assert result.output_path == "scripts/bert-base.json"

    def test_corrupt_json_fails(self) -> None:
        result = CodeSkill().process(b"not json{", fmt="json")
        assert result.success is False
        assert result.data is None


# ─── Scenario: 压缩包解析 ───


class TestCodeArchive:
    def test_zip_with_readme_parses(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "repo.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr(
                "README.md",
                "# Demo Repo\n\nA PyTorch project.\n\n## Installation\n\n`pip install`\n",
            )
            zf.writestr("setup.py", "from setuptools import setup\n")
            zf.writestr("src/model.py", "import torch\n")

        result = CodeSkill().process(
            zip_path.read_bytes(),
            fmt="zip",
            url="https://github.com/example/demo",
            name="demo",
        )
        assert result.success is True
        data = result.data
        assert "Demo Repo" in data["readme_text"]
        assert "setup.py" in data["file_tree"]
        assert data["framework"] == "pytorch"
        assert "pip install" in (data["installation"] or "")

    def test_tar_without_readme_warns(self, tmp_path: Path) -> None:
        tar_path = tmp_path / "repo.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            code = b"import tensorflow as tf\n"
            for name in ("model.py", "train.py"):
                info = tarfile.TarInfo(name=name)
                info.size = len(code)
                tf.addfile(info, io.BytesIO(code))

        result = CodeSkill().process(tar_path.read_bytes(), fmt="tar.gz", name="demo")
        assert result.success is True
        assert "model.py" in result.data["file_tree"]
        assert any("README" in w for w in result.warnings)

    def test_broken_zip_fails(self) -> None:
        result = CodeSkill().process(b"not a zip", fmt="zip")
        assert result.success is False


# ─── Scenario: 边界与降级 ───


class TestCodeDegradation:
    def test_empty_data_fails(self) -> None:
        result = CodeSkill().process(b"", fmt="markdown")
        assert result.success is False

    def test_unsupported_format_fails(self) -> None:
        result = CodeSkill().process(b"x", fmt="unknown")
        assert result.success is False
        assert "不支持" in result.errors[0]


# ─── Scenario: validate ───


class TestCodeValidate:
    def test_validate_success(self) -> None:
        result = CodeSkill().process(_read("README.md"), fmt="markdown")
        report = CodeSkill().validate(result)
        assert report.is_valid is True

    def test_validate_missing_framework_warning(self) -> None:
        result = StandardResult(
            success=True,
            canonical_format="CodeRepoSummary",
            data={
                "repo_url": "",
                "readme_text": "No framework here.",
                "file_tree": [],
                "framework": None,
                "installation": None,
            },
        )
        report = CodeSkill().validate(result)
        assert report.is_valid is True
        assert any(i.severity == Severity.WARNING and "框架" in i.message for i in report.issues)

    def test_validate_failure_path(self) -> None:
        result = StandardResult(success=False, canonical_format="CodeRepoSummary")
        report = CodeSkill().validate(result)
        assert report.is_valid is False
