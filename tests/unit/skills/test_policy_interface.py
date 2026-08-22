# tests/unit/skills/test_policy_interface.py
"""PolicyInterfaceSkill 单元测试（同步）。

覆盖 spec「PolicyInterfaceSkill — 策略模型接口标准化」全部 scenario：
- 元数据-only 目录生成接口文档（框架从文件名推断）
- 框架检测（detect_framework 各扩展名）
- 未知格式失败降级
- safetensors 真实权重结构解析（safetensors 不可用时 skip）
- 真实 saic3d 元数据解析（model_id/tags/weight_files）
- validate 对 framework=unknown 的 WARNING
"""

import json
from pathlib import Path

import pytest

from rdi.models.common import Severity, StandardResult
from rdi.models.retrieval import RawReference
from rdi.skills.policy_interface import (
    PolicyInterfaceDoc,
    PolicyInterfaceSkill,
    detect_framework,
)

_SAMPLE_DIR = Path(__file__).parent / "sample_data" / "policy"
_MINIMAL_META = _SAMPLE_DIR / "minimal_meta"
_SAIC3D_META = _SAMPLE_DIR / "saic3d_graspnet_ckpt_meta"


# ─── Scenario: 元数据-only 目录生成接口文档 ───


def test_metadata_only_dir_generates_doc() -> None:
    """元数据目录（无真实权重）→ framework 从文件名推断，completeness<100。"""
    result = PolicyInterfaceSkill().process(b"", model_dir=str(_MINIMAL_META))
    assert result.success is True
    assert result.canonical_format == "PolicyInterfaceDoc"
    assert isinstance(result.data, PolicyInterfaceDoc)
    doc: PolicyInterfaceDoc = result.data
    # framework 从 weight_files.json 中的 model.safetensors 推断
    assert doc.framework == "safetensors"
    assert len(doc.weight_files) > 0
    assert result.completeness_pct < 100.0
    assert result.confidence_score < 1.0
    assert any("权重未本地化" in w or "推断" in w for w in result.warnings)


def test_metadata_only_marks_is_fallback() -> None:
    """仅元数据（无真实权重本地化）→ is_fallback=True（fetch 降级消费契约）。"""
    result = PolicyInterfaceSkill().process(b"", model_dir=str(_MINIMAL_META))
    assert result.success is True
    assert result.is_fallback is True
    assert result.data_source_quality == "fallback"


# ─── Scenario: 框架检测 ───


def test_framework_detection() -> None:
    """detect_framework 覆盖所有已知扩展名与未知扩展名。"""
    assert detect_framework("model.pt") == "pytorch"
    assert detect_framework("model.pth") == "pytorch"
    assert detect_framework("model.safetensors") == "safetensors"
    assert detect_framework("model.onnx") == "onnx"
    assert detect_framework("model.ckpt") == "pytorch_lightning"
    assert detect_framework("model.pkl") == "pickle"
    assert detect_framework("model.unknown") is None
    assert detect_framework("noext") is None


# ─── Scenario: 未知框架/无元数据 → 失败降级 ───


def test_unknown_framework_fails(tmp_path: Path) -> None:
    """目录仅含无关文件（无权重、无元数据）→ success=False。"""
    (tmp_path / "readme.txt").write_text("unrelated", encoding="utf-8")
    result = PolicyInterfaceSkill().process(b"", model_dir=str(tmp_path))
    assert result.success is False
    assert result.data is None
    assert any("无法识别" in e for e in result.errors)


# ─── Scenario: safetensors 真实权重结构解析 ───


def test_safetensors_inspection_when_available(tmp_path: Path) -> None:
    """有真实 .safetensors 且模块可用 → 解析 layers（name+shape）。

    safetensors 不可用时 importorskip 跳过。
    """
    pytest.importorskip("safetensors")
    numpy = pytest.importorskip("numpy")
    from safetensors.numpy import save_file

    tensors = {"w": numpy.zeros((2, 2), dtype=numpy.float32)}
    weight_path = tmp_path / "model.safetensors"
    save_file(tensors, str(weight_path))
    result = PolicyInterfaceSkill().process(b"", model_dir=str(tmp_path))
    assert result.success is True
    assert isinstance(result.data, PolicyInterfaceDoc)
    doc: PolicyInterfaceDoc = result.data
    assert doc.framework == "safetensors"
    names = [layer["name"] for layer in doc.layers]
    assert "w" in names
    w_layer = next(layer for layer in doc.layers if layer["name"] == "w")
    assert w_layer["shape"] == [2, 2]
    assert result.confidence_score == 1.0


# ─── Scenario: 真实 saic3d 元数据解析 ───


def test_real_saic3d_metadata_parses() -> None:
    """真实 saic3d_graspnet_ckpt 元数据 → model_id 含 graspnet，weight_files 非空。"""
    result = PolicyInterfaceSkill().process(b"", model_dir=str(_SAIC3D_META))
    assert result.success is True
    assert isinstance(result.data, PolicyInterfaceDoc)
    doc: PolicyInterfaceDoc = result.data
    assert "graspnet" in doc.model_id
    assert len(doc.tags) > 0
    assert len(doc.weight_files) > 0
    # 权重文件为 .ckpt（size_bytes=0，元数据模式）
    ckpt_files = [wf for wf in doc.weight_files if wf["filename"].endswith(".ckpt")]
    assert len(ckpt_files) > 0
    assert result.completeness_pct < 100.0
    assert doc.source_url.startswith("https://huggingface.co/")


# ─── Scenario: validate 对 framework=unknown 的 WARNING ───


def test_validate_unknown_framework_warning() -> None:
    """framework=unknown 的 PolicyInterfaceDoc → validate 返回 WARNING。"""
    doc = PolicyInterfaceDoc(framework="unknown")
    result = StandardResult(success=True, canonical_format="PolicyInterfaceDoc", data=doc)
    report = PolicyInterfaceSkill().validate(result)
    assert report.is_valid is True  # WARNING 不阻断 is_valid
    assert any(i.severity == Severity.WARNING for i in report.issues)
    assert any("unknown" in i.message for i in report.issues)


# ─── validate 失败路径 ───


def test_validate_failure_path() -> None:
    """success=False 的结果 → validate 返回 is_valid=False。"""
    result = StandardResult(success=False, canonical_format="PolicyInterfaceDoc")
    report = PolicyInterfaceSkill().validate(result)
    assert report.is_valid is False


# ─── 字节清单路径（无目录） ───


def test_manifest_bytes_path() -> None:
    """data 为 model_info.json 字节 + kwargs 补充 weight_files.json 字节。"""
    model_info_bytes = b'{"id":"y","modelId":"foo/bar","tags":["test"]}'
    weight_files_bytes = (
        b'[{"filename":"model.pt","size_bytes":0,'
        b'"download_url":"https://huggingface.co/foo/bar/resolve/main/model.pt"}]'
    )
    result = PolicyInterfaceSkill().process(model_info_bytes, weight_files_json=weight_files_bytes)
    assert result.success is True
    assert isinstance(result.data, PolicyInterfaceDoc)
    doc: PolicyInterfaceDoc = result.data
    assert doc.framework == "pytorch"
    assert doc.model_id == "foo/bar"
    assert len(doc.weight_files) == 1
    assert any("权重未本地化" in w for w in result.warnings)


# ─── output_path 通过 name kwarg 生成 ───


def test_output_path_from_name_kwarg() -> None:
    """kwargs['name'] → output_path = policies/{name}.json。"""
    result = PolicyInterfaceSkill().process(b"", model_dir=str(_MINIMAL_META), name="test-policy")
    assert result.success is True
    assert result.output_path == "policies/test-policy.json"


# ─── 损坏 model_info.json 字节 → 降级 ───


def test_corrupt_manifest_bytes_fails() -> None:
    """data 为非法 JSON（fetch 降级场景）→ 降级成功 is_fallback（PASS_WITH_FALLBACK）。"""
    result = PolicyInterfaceSkill().process(b"not json{")
    assert result.success is True
    assert result.is_fallback is True
    assert result.data_source_quality == "fallback"
    assert result.data is not None
    assert any("降级" in w for w in result.warnings)


class TestPolicyFallbackDownloadGuide:
    """降级产物 download_guide 结构扩展（Task 8）。"""

    def test_manifest_json_with_inline_download_guide(self) -> None:
        """data 内嵌 download_guide（hf adapter 元数据 payload）→ doc.download_guide 复用。"""
        guide = {
            "status": "not_downloaded",
            "reason": "超过 max_fetch_bytes 自动下载上限",
            "source_file_url": "https://huggingface.co/foo/model/resolve/main/model.safetensors",
            "file_size_bytes": 999,
            "method_hint": (
                "wget https://huggingface.co/foo/model/resolve/main/model.safetensors "
                "-O model.safetensors"
            ),
            "selected_by": "ext=.safetensors; signals=model",
            "alternatives": [],
        }
        payload = {
            "id": "foo",
            "modelId": "foo/model",
            "tags": ["test"],
            "downloaded": False,
            "download_guide": guide,
        }
        result = PolicyInterfaceSkill().process(json.dumps(payload).encode("utf-8"), name="p1")
        assert result.is_fallback is True
        doc = result.data
        assert doc.download_guide == guide
        assert doc.model_id == "foo/model"

    def test_metadata_only_with_reference_kwarg(self) -> None:
        """目录元数据路径 + registry 透传 reference → doc.download_guide 由引用构造。"""
        ref = RawReference(
            url="https://huggingface.co/foo/model/resolve/main/model.safetensors",
            local_path="model.safetensors",
            file_size=1234,
            reason="超过自动下载上限",
        )
        result = PolicyInterfaceSkill().process(
            b"", model_dir=str(_MINIMAL_META), reference=ref
        )
        assert result.is_fallback is True
        doc = result.data
        assert doc.download_guide is not None
        assert doc.download_guide["status"] == "not_downloaded"
        assert doc.download_guide["source_file_url"] == ref.url
        assert doc.download_guide["file_size_bytes"] == 1234
        assert doc.download_guide["method_hint"].startswith("wget ")

    def test_corrupt_json_with_reference_kwarg(self) -> None:
        """JSON 非法降级 + reference → doc.download_guide 由引用构造。"""
        ref = RawReference(
            url="https://huggingface.co/foo/model/resolve/main/model.safetensors",
            file_size=1234,
            reason="超过自动下载上限",
        )
        result = PolicyInterfaceSkill().process(b"not json{", name="p", reference=ref)
        assert result.is_fallback is True
        assert result.data.download_guide["source_file_url"] == ref.url
        assert result.data.download_guide["method_hint"].startswith("wget ")

    def test_fallback_without_reference_keeps_none(self) -> None:
        """无引用 → doc.download_guide 为 None（不附加指引，不回归）。"""
        result = PolicyInterfaceSkill().process(b"not json{", name="p")
        assert result.is_fallback is True
        assert result.data.download_guide is None
