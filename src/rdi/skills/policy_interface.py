# src/rdi/skills/policy_interface.py
"""PolicyInterfaceSkill — 策略模型接口标准化。

自动检测框架（.pt/.pth/.safetensors/.onnx/.ckpt/.pkl），有权重时解析结构，
仅元数据时从 model_info.json / weight_files.json 生成 ``PolicyInterfaceDoc``。
safetensors/onnx/torch 为可选依赖，importlib 动态加载，ImportError 时降级。
"""

import importlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from rdi.models.common import Severity, StandardResult, ValidationReport, ValIssue
from rdi.skills.base import BaseSkill

_FRAMEWORK_BY_EXT: dict[str, str] = {
    ".pt": "pytorch",
    ".pth": "pytorch",
    ".safetensors": "safetensors",
    ".onnx": "onnx",
    ".ckpt": "pytorch_lightning",
    ".pkl": "pickle",
}
_WEIGHT_EXTS = frozenset({".pt", ".pth", ".safetensors", ".onnx", ".ckpt"})
_META_ONLY_COMPLETENESS = 60.0
_INSPECT_FAILED_COMPLETENESS = 80.0
_FULL_COMPLETENESS = 100.0
# 权重结构解析结果：(layers, input_spec, output_spec)
_InspectResult = tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]


def detect_framework(filename: str) -> str | None:
    """根据文件扩展名推断框架名；未知扩展名返回 None。"""
    return _FRAMEWORK_BY_EXT.get(Path(filename).suffix.lower())


class PolicyInterfaceDoc(BaseModel):
    """策略模型标准化接口文档（可 JSON 序列化）。"""

    model_config = ConfigDict(extra="forbid")

    framework: str = Field(description="框架名: pytorch/safetensors/onnx/...")
    layers: list[dict[str, Any]] = Field(default_factory=list, description="每项 {name, shape}")
    input_spec: dict[str, Any] = Field(default_factory=dict, description="{name: [dims]}")
    output_spec: dict[str, Any] = Field(default_factory=dict, description="{name: [dims]}")
    weight_files: list[dict[str, Any]] = Field(
        default_factory=list, description="每项 {filename, download_url, size_bytes}"
    )
    source_url: str = ""
    model_id: str = ""
    tags: list[str] = Field(default_factory=list)


class PolicyInterfaceSkill(BaseSkill):
    """策略模型接口标准化 Skill（model_dir 目录路径 或 model_info.json 字节）。"""

    skill_name = "policy_interface"

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        model_dir = kwargs.get("model_dir")
        if isinstance(model_dir, str) and Path(model_dir).is_dir():
            return self._process_directory(Path(model_dir), kwargs)
        return self._process_manifest_bytes(data, kwargs)

    def validate(self, result: StandardResult) -> ValidationReport:
        if not result.success or result.data is None:
            return ValidationReport(is_valid=False, summary="策略模型接口解析失败")
        doc = result.data
        if not isinstance(doc, PolicyInterfaceDoc):
            return ValidationReport(is_valid=False, summary="中间表示类型错误")
        issues: list[ValIssue] = []
        if doc.framework == "unknown":
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="policy",
                    message="无法识别策略框架: framework=unknown",
                    suggestion="提供 .pt/.pth/.safetensors/.onnx/.ckpt 权重文件",
                )
            )
        if not doc.weight_files:
            issues.append(
                ValIssue(
                    severity=Severity.WARNING,
                    req_id="policy",
                    message="weight_files 为空，未找到任何权重文件",
                    suggestion="检查 weight_files.json 或目录内权重文件",
                )
            )
        return ValidationReport(
            is_valid=True, issues=issues, summary=f"策略接口校验完成: {len(issues)} 个问题"
        )

    def _process_directory(self, model_dir: Path, kwargs: dict[str, Any]) -> StandardResult:
        model_info = self._load_json(model_dir / "model_info.json")
        weight_files_meta = self._load_json(model_dir / "weight_files.json")
        config = self._load_json(model_dir / "config.json")
        real_weights = self._find_real_weights(model_dir)
        if not real_weights and model_info is None and weight_files_meta is None:
            return self._fail()
        if real_weights:
            return self._build_with_weights(
                real_weights, model_info, weight_files_meta, config, kwargs
            )
        return self._build_metadata_only(model_info, weight_files_meta, config, kwargs)

    def _build_with_weights(
        self,
        real_weights: list[Path],
        model_info: Any,
        weight_files_meta: Any,
        config: Any,
        kwargs: dict[str, Any],
    ) -> StandardResult:
        weight_path = real_weights[0]
        framework = detect_framework(weight_path.name) or "unknown"
        layers, input_spec, output_spec = self._inspect_weight(weight_path, framework)
        inspected = bool(layers or input_spec or output_spec)
        if inspected:
            completeness = _FULL_COMPLETENESS
            warnings: list[str] = []
        else:
            completeness = _INSPECT_FAILED_COMPLETENESS
            warnings = [
                f"权重文件 {weight_path.name} 存在但无法解析结构"
                f"（{framework} 模块不可用或格式不支持）"
            ]
        model_id, tags, source_url = self._extract_meta(model_info)
        weight_files = self._build_weight_files(real_weights, weight_files_meta)
        cfg_in, cfg_out = self._specs_from_config(config)
        if not input_spec:
            input_spec = cfg_in
        if not output_spec:
            output_spec = cfg_out
        doc = PolicyInterfaceDoc(
            framework=framework,
            layers=layers,
            input_spec=input_spec,
            output_spec=output_spec,
            weight_files=weight_files,
            source_url=source_url,
            model_id=model_id,
            tags=tags,
        )
        return self._ok(doc, completeness, warnings, kwargs)

    def _build_metadata_only(
        self,
        model_info: Any,
        weight_files_meta: Any,
        config: Any,
        kwargs: dict[str, Any],
    ) -> StandardResult:
        framework = self._infer_framework_from_meta(weight_files_meta)
        model_id, tags, source_url = self._extract_meta(model_info)
        weight_files = self._normalize_weight_meta(weight_files_meta)
        input_spec, output_spec = self._specs_from_config(config)
        doc = PolicyInterfaceDoc(
            framework=framework,
            input_spec=input_spec,
            output_spec=output_spec,
            weight_files=weight_files,
            source_url=source_url,
            model_id=model_id,
            tags=tags,
        )
        # 仅元数据（权重未本地化）→ 标记 is_fallback（fetch 降级消费契约）
        return self._ok(
            doc,
            _META_ONLY_COMPLETENESS,
            ["权重未本地化，接口为推断"],
            kwargs,
            confidence=0.8,
            is_fallback=True,
        )

    def _process_manifest_bytes(self, data: bytes, kwargs: dict[str, Any]) -> StandardResult:
        if not data:
            return self._fail()
        try:
            model_info = json.loads(data)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            # fetch 显式降级（源返回 README/HTML 等非 JSON，如 GitHub 兜底）：
            # 按 Day2 fmt=json 降级消费契约标记 is_fallback，不伪造权重结构
            return StandardResult(
                success=True,
                canonical_format="PolicyInterfaceDoc",
                data=PolicyInterfaceDoc(framework="unknown", model_id=""),
                completeness_pct=60.0,
                confidence_score=0.6,
                data_source_quality="fallback",
                is_fallback=True,
                warnings=[f"策略模型元数据非合法 JSON（{str(exc)[:80]}），返回降级引用"],
            )
        weight_files_meta = self._parse_kwarg_json(kwargs, "weight_files_json")
        config = self._parse_kwarg_json(kwargs, "config_json")
        return self._build_metadata_only(model_info, weight_files_meta, config, kwargs)

    def _inspect_weight(self, path: Path, framework: str) -> _InspectResult:
        if framework == "safetensors":
            return self._inspect_safetensors(path)
        if framework == "onnx":
            return self._inspect_onnx(path)
        if framework in ("pytorch", "pytorch_lightning"):
            return self._inspect_pytorch(path)
        return [], {}, {}

    def _inspect_safetensors(self, path: Path) -> _InspectResult:
        try:
            safetensors = importlib.import_module("safetensors")
        except ImportError:
            return [], {}, {}
        try:
            layers: list[dict[str, Any]] = []
            with safetensors.safe_open(str(path), framework="numpy") as f:
                for key in f.keys():  # noqa: SIM118 — safe_open 非字典，keys() 不可省略
                    layers.append({"name": key, "shape": list(f.get_slice(key).get_shape())})
            return layers, {}, {}
        except (OSError, ValueError, RuntimeError):
            return [], {}, {}

    def _inspect_onnx(self, path: Path) -> _InspectResult:
        try:
            onnx = importlib.import_module("onnx")
        except ImportError:
            return [], {}, {}
        try:
            model = onnx.load(str(path))
            input_spec = {
                inp.name: [d.dim_value for d in inp.type.tensor_type.shape.dim]
                for inp in model.graph.input
            }
            output_spec = {
                out.name: [d.dim_value for d in out.type.tensor_type.shape.dim]
                for out in model.graph.output
            }
            return [], input_spec, output_spec
        except (OSError, ValueError, RuntimeError):
            return [], {}, {}

    def _inspect_pytorch(self, path: Path) -> _InspectResult:
        try:
            torch = importlib.import_module("torch")
        except ImportError:
            return [], {}, {}
        try:
            state = torch.load(str(path), weights_only=True)
        except (OSError, ValueError, RuntimeError, TypeError):
            return [], {}, {}
        layers: list[dict[str, Any]] = []
        if isinstance(state, dict):
            for key, tensor in state.items():
                shape = list(tensor.shape) if hasattr(tensor, "shape") else []
                layers.append({"name": key, "shape": shape})
        return layers, {}, {}

    @staticmethod
    def _fail() -> StandardResult:
        return StandardResult(
            success=False,
            canonical_format="PolicyInterfaceDoc",
            errors=["无法识别的策略模型格式"],
        )

    @staticmethod
    def _ok(
        doc: PolicyInterfaceDoc,
        completeness: float,
        warnings: list[str],
        kwargs: dict[str, Any],
        confidence: float = 1.0,
        is_fallback: bool = False,
    ) -> StandardResult:
        name = kwargs.get("name")
        output_path = f"policies/{name}.json" if isinstance(name, str) and name else None
        return StandardResult(
            success=True,
            canonical_format="PolicyInterfaceDoc",
            output_path=output_path,
            completeness_pct=completeness,
            confidence_score=confidence,
            warnings=warnings,
            data=doc,
            is_fallback=is_fallback,
            data_source_quality="fallback" if is_fallback else "real",
        )

    @staticmethod
    def _load_json(path: Path) -> Any:
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError, OSError):
            return None

    @staticmethod
    def _parse_kwarg_json(kwargs: dict[str, Any], key: str) -> Any:
        raw = kwargs.get(key)
        if not isinstance(raw, bytes | bytearray):
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None

    @staticmethod
    def _find_real_weights(model_dir: Path) -> list[Path]:
        return [p for p in model_dir.rglob("*") if p.is_file() and p.suffix.lower() in _WEIGHT_EXTS]

    @staticmethod
    def _extract_meta(model_info: Any) -> tuple[str, list[str], str]:
        if not isinstance(model_info, dict):
            return "", [], ""
        model_id = str(model_info.get("modelId") or model_info.get("id") or "")
        tags_raw = model_info.get("tags") or []
        tags = [str(t) for t in tags_raw] if isinstance(tags_raw, list) else []
        source_url = f"https://huggingface.co/{model_id}" if model_id else ""
        return model_id, tags, source_url

    @staticmethod
    def _infer_framework_from_meta(weight_files_meta: Any) -> str:
        if not isinstance(weight_files_meta, list):
            return "unknown"
        for wf in weight_files_meta:
            if isinstance(wf, dict):
                fw = detect_framework(str(wf.get("filename", "")))
                if fw:
                    return fw
        return "unknown"

    @staticmethod
    def _normalize_weight_meta(weight_files_meta: Any) -> list[dict[str, Any]]:
        if not isinstance(weight_files_meta, list):
            return []
        return [
            {
                "filename": str(wf.get("filename", "")),
                "download_url": str(wf.get("download_url", "")),
                "size_bytes": wf.get("size_bytes", 0),
            }
            for wf in weight_files_meta
            if isinstance(wf, dict)
        ]

    @staticmethod
    def _build_weight_files(
        real_weights: list[Path], weight_files_meta: Any
    ) -> list[dict[str, Any]]:
        if isinstance(weight_files_meta, list) and weight_files_meta:
            return PolicyInterfaceSkill._normalize_weight_meta(weight_files_meta)
        result: list[dict[str, Any]] = []
        for w in real_weights:
            try:
                size = w.stat().st_size
            except OSError:
                size = 0
            result.append({"filename": w.name, "download_url": "", "size_bytes": size})
        return result

    @staticmethod
    def _specs_from_config(config: Any) -> tuple[dict[str, Any], dict[str, Any]]:
        if not isinstance(config, dict):
            return {}, {}
        in_spec = config.get("input_spec") or config.get("inputs") or {}
        out_spec = config.get("output_spec") or config.get("outputs") or {}
        if isinstance(in_spec, dict) and isinstance(out_spec, dict):
            return in_spec, out_spec
        return {}, {}
