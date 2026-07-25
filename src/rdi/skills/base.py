# src/rdi/skills/base.py
"""Skill 能力执行层抽象基类。

所有具体 Skill（URDFSkill / MeshSkill / GraspSkill / SimConfigSkill /
PolicyInterfaceSkill / SensorDataSkill）继承此类，实现 process / validate 方法。

输入仅为 `bytes`（来自 `RawData.data`），Skill 不直接调用外部 API，
符合开发规范「节点内部不直接调用外部 API，必须通过 Adapter 或 Skill」。
"""

from abc import ABC, abstractmethod
from typing import Any

from rdi.models.common import StandardResult, ValidationReport


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
