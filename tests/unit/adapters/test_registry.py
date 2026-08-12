# tests/unit/adapters/test_registry.py
"""Adapter 注册表单元测试。"""

import pytest

from rdi.adapters.allegro import AllegroAdapter
from rdi.adapters.arxiv import ArxivAdapter
from rdi.adapters.base import BaseAdapter
from rdi.adapters.dexgrasp import DexGraspAdapter
from rdi.adapters.franka import FrankaAdapter
from rdi.adapters.github import GitHubAdapter
from rdi.adapters.google_scanned import GoogleScannedAdapter
from rdi.adapters.graspnet import GraspNetAdapter
from rdi.adapters.huggingface import HuggingFaceAdapter
from rdi.adapters.ieee import IEEEXploreAdapter
from rdi.adapters.isaac import IsaacSimAdapter
from rdi.adapters.mujoco import MuJoCoAdapter
from rdi.adapters.paperswithcode import PapersWithCodeAdapter
from rdi.adapters.registry import ADAPTER_REGISTRY, select_adapter
from rdi.adapters.robotiq import RobotiqAdapter
from rdi.adapters.ycb import YCBAdapter
from rdi.adapters.zenodo import ZenodoAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource

# 所有 15 个 Adapter 类及其对应的 DataSource
ALL_ADAPTERS: list[tuple[type[BaseAdapter], DataSource]] = [
    (ArxivAdapter, DataSource.ARXIV),
    (GitHubAdapter, DataSource.GITHUB),
    (GraspNetAdapter, DataSource.GRASPNET),
    (YCBAdapter, DataSource.YCB),
    (FrankaAdapter, DataSource.FRANKA),
    (HuggingFaceAdapter, DataSource.HUGGINGFACE),
    (ZenodoAdapter, DataSource.ZENODO),
    (DexGraspAdapter, DataSource.DEXGRASP),
    (GoogleScannedAdapter, DataSource.GOOGLE_SCANNED),
    (RobotiqAdapter, DataSource.ROBOTIQ),
    (AllegroAdapter, DataSource.ALLEGRO),
    (MuJoCoAdapter, DataSource.MUJOCO),
    (IsaacSimAdapter, DataSource.ISAAC),
    (IEEEXploreAdapter, DataSource.IEEE),
    (PapersWithCodeAdapter, DataSource.PAPERSWITHCODE),
]


class TestAdapterRegistry:
    """ADAPTER_REGISTRY 单元测试。"""

    # D2: 新增四类暂无内置数据源的 DataReqType（诚实失败为 missing，
    # 不注册 Adapter 是预期语义，见 spec Task 13）。
    _NO_BUILTIN_SOURCE_TYPES = {
        DataReqType.CAMERA_CALIB,
        DataReqType.TEACHING_TRAJECTORY,
        DataReqType.ROBOT_CONFIG,
        DataReqType.BENCHMARK_TASK,
    }

    def test_registry_has_all_req_types(self) -> None:
        """正常情况：注册表覆盖所有真实 DataReqType（UNKNOWN 为哨兵值，无需 adapter）。

        D2：CAMERA_CALIB / TEACHING_TRAJECTORY / ROBOT_CONFIG / BENCHMARK_TASK
        暂不注册 adapter（无内置数据源），从预期中排除。
        """
        expected_types = [
            t
            for t in DataReqType
            if t is not DataReqType.UNKNOWN and t not in self._NO_BUILTIN_SOURCE_TYPES
        ]
        for req_type in expected_types:
            assert req_type in ADAPTER_REGISTRY, f"Missing {req_type} in ADAPTER_REGISTRY"

    def test_registry_no_builtin_for_new_types(self) -> None:
        """D2：四类新类型在注册表中无内置 Adapter（select_adapter 返回空列表）。"""
        for req_type in self._NO_BUILTIN_SOURCE_TYPES:
            assert req_type not in ADAPTER_REGISTRY, (
                f"{req_type} 不应注册内置 Adapter（无内置数据源）"
            )
            assert select_adapter(req_type) == [], f"select_adapter({req_type}) 应返回空列表"

    def test_paper_primary_is_arxiv(self) -> None:
        """正常情况：PAPER 主源是 ArxivAdapter，且包含 PapersWithCodeAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.PAPER]
        assert names[0] == "ArxivAdapter"
        assert "PapersWithCodeAdapter" in names

    def test_code_primary_is_github(self) -> None:
        """正常情况：CODE 主源是 GitHubAdapter，且包含 HuggingFaceAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.CODE]
        assert names[0] == "GitHubAdapter"
        assert "HuggingFaceAdapter" in names

    def test_robot_urdf_does_not_contain_sim_adapters(self) -> None:
        """C2 修复：ROBOT_URDF 不再包含 MuJoCoAdapter 和 IsaacSimAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.ROBOT_URDF]
        assert "MuJoCoAdapter" not in names
        assert "IsaacSimAdapter" not in names

    def test_sim_config_contains_sim_adapters(self) -> None:
        """正常情况：SIM_CONFIG 包含 MuJoCoAdapter 和 IsaacSimAdapter。"""
        names = ADAPTER_REGISTRY[DataReqType.SIM_CONFIG]
        assert "MuJoCoAdapter" in names
        assert "IsaacSimAdapter" in names

    def test_paper_contains_all_b_expected(self) -> None:
        """B 系统预期：PAPER 包含 Arxiv + PapersWithCode。"""
        names = ADAPTER_REGISTRY[DataReqType.PAPER]
        assert "ArxivAdapter" in names
        assert "PapersWithCodeAdapter" in names

    def test_code_contains_all_b_expected(self) -> None:
        """B 系统预期：CODE 至少包含 GitHub + HuggingFace。"""
        names = ADAPTER_REGISTRY[DataReqType.CODE]
        assert "GitHubAdapter" in names
        assert "HuggingFaceAdapter" in names

    def test_robot_urdf_contains_all_b_expected(self) -> None:
        """B 系统预期：ROBOT_URDF 仅包含真实机器人 URDF 源。"""
        names = ADAPTER_REGISTRY[DataReqType.ROBOT_URDF]
        for expected in [
            "FrankaAdapter",
            "AllegroAdapter",
            "RobotiqAdapter",
        ]:
            assert expected in names, f"{expected} missing from ROBOT_URDF"

    def test_sim_config_contains_all_b_expected(self) -> None:
        """B 系统预期：SIM_CONFIG 包含仿真配置源。"""
        names = ADAPTER_REGISTRY[DataReqType.SIM_CONFIG]
        for expected in ["MuJoCoAdapter", "IsaacSimAdapter"]:
            assert expected in names, f"{expected} missing from SIM_CONFIG"


class TestSelectAdapter:
    """select_adapter 单元测试。"""

    def test_select_paper_returns_arxiv(self) -> None:
        """正常情况：PAPER 返回包含 ArxivAdapter 和 PapersWithCodeAdapter。"""
        adapters = select_adapter(DataReqType.PAPER)
        assert ArxivAdapter in adapters
        assert PapersWithCodeAdapter in adapters

    def test_select_code_returns_github(self) -> None:
        """正常情况：CODE 返回包含 GitHubAdapter 和 HuggingFaceAdapter。"""
        adapters = select_adapter(DataReqType.CODE)
        assert GitHubAdapter in adapters
        assert HuggingFaceAdapter in adapters

    def test_select_returns_adapter_subclasses(self) -> None:
        """正常情况：返回的都是 BaseAdapter 子类。"""
        for req_type in DataReqType:
            adapters = select_adapter(req_type)
            for adapter_cls in adapters:
                assert issubclass(adapter_cls, BaseAdapter)

    def test_select_sensor_data_returns_github(self) -> None:
        """正常情况：SENSOR_DATA 返回 GitHubAdapter。"""
        adapters = select_adapter(DataReqType.SENSOR_DATA)
        assert GitHubAdapter in adapters

    def test_all_adapters_available_via_select(self) -> None:
        """正常情况：所有 15 个 Adapter 都能通过 select_adapter 返回。"""
        all_returned: set[type[BaseAdapter]] = set()
        for req_type in DataReqType:
            all_returned.update(select_adapter(req_type))
        adapter_classes = {cls for cls, _ in ALL_ADAPTERS}
        assert adapter_classes.issubset(all_returned), (
            f"Missing adapters: {adapter_classes - all_returned}"
        )

    @pytest.mark.parametrize(
        "adapter_cls,expected_source",
        ALL_ADAPTERS,
        ids=[cls.__name__ for cls, _ in ALL_ADAPTERS],
    )
    def test_each_adapter_source_matches(
        self, adapter_cls: type[BaseAdapter], expected_source: DataSource
    ) -> None:
        """正常情况：每个 Adapter 实例化后 source 属性与 DataSource 枚举对应。"""
        adapter = adapter_cls()
        assert adapter.source == expected_source


class TestGetAdapter:
    """get_adapter 工厂函数单元测试。"""

    def test_get_adapter_all_sources(self) -> None:
        """正常情况：每个网络 DataSource 都能通过 get_adapter 返回 BaseAdapter 实例且 source 正确。"""
        from rdi.adapters import get_adapter

        # LOCAL 为前端本地文件注入专用源（无网络适配器），跳过
        for source in DataSource:
            if source is DataSource.LOCAL:
                continue
            adapter = get_adapter(source)
            assert isinstance(adapter, BaseAdapter), f"{source} 返回的不是 BaseAdapter 实例"
            assert adapter.source == source, f"{source} 返回的 adapter.source 不匹配"

    def test_get_adapter_covers_all_sources(self) -> None:
        """正常情况：_ADAPTER_CLASSES 覆盖除 LOCAL 外的所有 DataSource 枚举值。"""
        from rdi.adapters import _ADAPTER_CLASSES

        # LOCAL 为本地注入专用源，不注册网络适配器
        assert len(_ADAPTER_CLASSES) == len(DataSource) - 1, (
            f"_ADAPTER_CLASSES 有 {len(_ADAPTER_CLASSES)} 项，"
            f"DataSource 枚举（除 LOCAL）应有 {len(DataSource) - 1} 项"
        )

    def test_get_adapter_unknown_raises(self) -> None:
        """异常情况：不在 _ADAPTER_CLASSES 中的 DataSource 会抛出 AdapterError。"""
        from rdi.adapters import _ADAPTER_CLASSES, get_adapter

        # 临时从 _ADAPTER_CLASSES 删除一个键，验证 get_adapter 抛出 AdapterError
        test_source = DataSource.ARXIV
        original = _ADAPTER_CLASSES.pop(test_source)
        try:
            with pytest.raises(AdapterError) as exc_info:
                get_adapter(test_source)
            assert (
                test_source.value in exc_info.value.source
                or exc_info.value.source == test_source.value
            )
        finally:
            _ADAPTER_CLASSES[test_source] = original
