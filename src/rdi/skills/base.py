# src/rdi/skills/base.py
"""Skill 能力执行层抽象基类。

所有具体 Skill（URDFSkill / MeshSkill / GraspSkill / SimConfigSkill /
PolicyInterfaceSkill / SensorDataSkill）继承此类，实现 process / validate 方法。

输入仅为 `bytes`（来自 `RawData.data`），Skill 不直接调用外部 API，
符合开发规范「节点内部不直接调用外部 API，必须通过 Adapter 或 Skill」。
"""

import json
from abc import ABC, abstractmethod
from typing import Any

from rdi.adapters.selectors import build_download_guide
from rdi.models.common import StandardResult, ValidationReport


def extract_download_guide(raw_data: bytes, kwargs: dict[str, Any]) -> dict[str, Any] | None:
    """从降级输入中提取下载指引（download_guide）；无引用信息时返回 None。

    两条来源（均对应 adapter 超限/降级场景）：
    1. ``raw_data``（JSON）内已嵌入的 ``download_guide`` 键（结构同
       ``build_download_guide`` 输出，zenodo/huggingface/github adapter 均如此产出）；
    2. registry 透传的 ``reference``（RawReference 或等价 dict，含 url/file_size/
       reason/download_hint），由 ``build_download_guide`` 构造同构指引。

    两者皆无时返回 None，调用方保持原降级产物结构（不回归）。
    """
    guide = _guide_from_data(raw_data)
    if guide is not None:
        return guide
    return _guide_from_reference(kwargs.get("reference"))


def _guide_from_data(raw_data: bytes) -> dict[str, Any] | None:
    """raw_data 为 JSON dict 且含 download_guide 键时直接复用；否则返回 None。"""
    try:
        obj = json.loads(raw_data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    guide = obj.get("download_guide") if isinstance(obj, dict) else None
    return guide if isinstance(guide, dict) else None


def _guide_from_reference(reference: Any) -> dict[str, Any] | None:
    """由 RawReference（或等价 dict）构造 download_guide；无 url 时返回 None。"""
    if reference is None:
        return None
    ref = reference.model_dump() if hasattr(reference, "model_dump") else reference
    if not isinstance(ref, dict):
        return None
    url = str(ref.get("url") or "")
    if not url:
        return None
    local = str(ref.get("local_path") or "") or url.rstrip("/").rsplit("/", 1)[-1]
    guide = build_download_guide(
        {"url": url, "path": local, "size": ref.get("file_size") or 0, "name": local},
        str(ref.get("reason") or "") or "引用数据源未自动下载",
    )
    hint = ref.get("download_hint")
    if isinstance(hint, str) and hint:
        guide["method_hint"] = hint
    return guide


class BaseSkill(ABC):
    """Skill 基类，约定每个 Skill 的处理与校验契约。

    约定：
    - 每个 Skill 实现 process 和 validate 方法，签名与基类一致
    - 处理失败时返回降级结果（``StandardResult(success=False, errors=[...])``）
      而非抛异常中断流程
    - 处理大文件时使用流式读取 / 懒加载（如 ``np.load`` 懒加载 + 切片读取），
      不一次性把全部内容载入内存
    - 每个 Skill 附带 ``sample_data/`` 目录，存放测试用样本
    - 返回值使用 Pydantic model（StandardResult / ValidationReport）
    """

    skill_name: str  # 子类必须定义自己的 Skill 标识

    @abstractmethod
    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        """处理原始数据，返回标准化结果。

        Args:
            data: 原始数据字节（来自 ``RawData.data``）
            **kwargs: 额外参数（如格式提示、数据集约定、配置选项）

        Returns:
            StandardResult 包含标准化后的数据；处理失败时返回降级结果
            （``success=False``、``errors=[...]``、``data=None``），不抛异常
        """
        ...

    @abstractmethod
    def validate(self, result: StandardResult) -> ValidationReport:
        """校验处理结果的正确性。

        Args:
            result: ``process`` 方法的返回值

        Returns:
            ValidationReport 包含校验结论和问题列表
        """
        ...
