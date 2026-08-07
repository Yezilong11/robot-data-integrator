"""DatasetSkill 单元测试（同步）。

覆盖 spec「DATASET Skill」全部 scenario：
- Zenodo metadata JSON 解析
- HuggingFace dataset_info JSON 解析
- zip / tar 压缩包解析（文件树 + 内部 metadata）
- 空数据 / 不支持的格式 / 损坏的压缩包 降级
- validate 对缺失标题 / 描述的 WARNING
"""

import io
import tarfile
import zipfile
from pathlib import Path

from rdi.models.common import Severity, StandardResult
from rdi.skills.dataset_parse import DatasetSkill

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "dataset"


def _read(name: str) -> bytes:
    return (_SAMPLE_DIR / name).read_bytes()


# ─── Scenario: Zenodo metadata JSON 解析 ───


class TestDatasetZenodo:
    def test_zenodo_metadata_parses(self) -> None:
        result = DatasetSkill().process(
            _read("zenodo_metadata.json"),
            fmt="json",
            name="ycb_video",
        )
        assert result.success is True
        assert result.canonical_format == "DatasetSummary"
        data = result.data
        assert data["title"] == "YCB Video Dataset"
        assert "6D object pose" in data["description"]
        assert data["download_url"] == "https://zenodo.org/records/12345/files/ycb_video.zip"
        assert "ycb_video.zip" in data["file_tree"]
        assert data["license"] == "CC-BY-4.0"
        assert result.output_path == "datasets/ycb_video.json"


# ─── Scenario: HuggingFace dataset_info JSON 解析 ───


class TestDatasetHuggingFace:
    def test_hf_dataset_info_parses(self) -> None:
        result = DatasetSkill().process(
            _read("hf_dataset_info.json"),
            fmt="json",
            name="grasp",
        )
        assert result.success is True
        data = result.data
        assert data["title"] == "Yeb Havinga/grasp"
        assert "Grasp detection" in data["description"]
        assert "huggingface.co" in data["download_url"]
        assert "data/train.parquet" in data["file_tree"]
        assert data["license"] == "apache-2.0"


# ─── Scenario: 压缩包解析 ───


class TestDatasetArchive:
    def test_zip_with_internal_metadata_parses(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "dataset.zip"
        metadata = (
            b'{"title":"Tiny Dataset","description":"A small test dataset.",'
            b'"license":"MIT","files":[{"key":"data.csv"}]}'
        )
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("metadata.json", metadata)
            zf.writestr("data.csv", "x,y\n1,2\n")

        result = DatasetSkill().process(zip_path.read_bytes(), fmt="zip", name="tiny")
        assert result.success is True
        data = result.data
        assert data["title"] == "Tiny Dataset"
        assert "data.csv" in data["file_tree"]
        assert data["license"] == "MIT"

    def test_tar_without_metadata_warns(self, tmp_path: Path) -> None:
        tar_path = tmp_path / "dataset.tar.gz"
        with tarfile.open(tar_path, "w:gz") as tf:
            content = b"x,y\n1,2\n"
            for name in ("data.csv", "labels.csv"):
                info = tarfile.TarInfo(name=name)
                info.size = len(content)
                tf.addfile(info, io.BytesIO(content))

        result = DatasetSkill().process(
            tar_path.read_bytes(),
            fmt="tar.gz",
            name="tiny",
            title="Tiny Dataset",
        )
        assert result.success is True
        assert "data.csv" in result.data["file_tree"]
        assert any("metadata" in w for w in result.warnings)

    def test_broken_tar_fails(self) -> None:
        result = DatasetSkill().process(b"not a tar", fmt="tar")
        assert result.success is False


# ─── Scenario: 边界与降级 ───


class TestDatasetDegradation:
    def test_empty_data_fails(self) -> None:
        result = DatasetSkill().process(b"", fmt="json")
        assert result.success is False

    def test_unsupported_format_fails(self) -> None:
        result = DatasetSkill().process(b"x", fmt="yaml")
        assert result.success is False
        assert "不支持" in result.errors[0]

    def test_non_object_json_fails(self) -> None:
        result = DatasetSkill().process(b'["not", "an", "object"]', fmt="json")
        assert result.success is False


# ─── Scenario: validate ───


class TestDatasetValidate:
    def test_validate_success(self) -> None:
        result = DatasetSkill().process(_read("zenodo_metadata.json"), fmt="json")
        report = DatasetSkill().validate(result)
        assert report.is_valid is True

    def test_validate_missing_title_warning(self) -> None:
        result = StandardResult(
            success=True,
            canonical_format="DatasetSummary",
            data={
                "title": "",
                "description": "No title here.",
                "download_url": None,
                "file_tree": [],
                "license": None,
            },
        )
        report = DatasetSkill().validate(result)
        assert report.is_valid is True
        assert any(i.severity == Severity.WARNING and "标题" in i.message for i in report.issues)

    def test_validate_failure_path(self) -> None:
        result = StandardResult(success=False, canonical_format="DatasetSummary")
        report = DatasetSkill().validate(result)
        assert report.is_valid is False
