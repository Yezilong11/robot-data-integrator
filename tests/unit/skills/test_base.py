# tests/unit/skills/test_base.py
"""BaseSkill 抽象基类与 StandardResult.data 字段的单元测试。"""

from typing import Any

import pytest

from rdi.models.common import StandardResult, ValidationReport
from rdi.skills.base import BaseSkill

# ─── StandardResult.data 字段测试 ───


class TestStandardResultDataField:
    """StandardResult 新增 data 字段的契约测试。"""

    def test_standard_result_data_defaults_none(self) -> None:
        """向后兼容：未传 data 时默认为 None。"""
        result = StandardResult(success=True, canonical_format="x")
        assert result.data is None

    def test_standard_result_data_can_hold_object(self) -> None:
        """正常情况：data 字段可承载任意中间表示对象。"""
        result = StandardResult(success=True, canonical_format="x", data={"a": 1})
        assert result.data == {"a": 1}


# ─── BaseSkill 抽象基类测试 ───


class _FullSkill(BaseSkill):
    """完整实现的 Skill 桩，用于验证可实例化。"""

    skill_name = "full"

    def process(self, data: bytes, **kwargs: Any) -> StandardResult:
        return StandardResult(success=True, canonical_format="stub")

    def validate(self, result: StandardResult) -> ValidationReport:
        return ValidationReport(is_valid=True)


class _IncompleteSkill(BaseSkill):
    """缺少 process 实现的 Skill 桩，用于验证抽象契约。"""

    skill_name = "incomplete"

    # 故意不实现 process / validate


class TestBaseSkillAbc:
    """BaseSkill 抽象基类行为测试。"""

    def test_base_skill_cannot_instantiate(self) -> None:
        """异常情况：BaseSkill 自身不可实例化。"""
        with pytest.raises(TypeError):
            BaseSkill()  # type: ignore[abstract]

    def test_base_skill_subclass_must_implement(self) -> None:
        """异常情况：子类未实现全部抽象方法时不可实例化。"""
        with pytest.raises(TypeError):
            _IncompleteSkill()  # type: ignore[abstract]

    def test_base_skill_full_subclass_instantiates(self) -> None:
        """正常情况：完整实现的子类可实例化并工作。"""
        skill = _FullSkill()
        result = skill.process(b"")
        assert result.success is True
        assert result.canonical_format == "stub"
        report = skill.validate(result)
        assert report.is_valid is True
