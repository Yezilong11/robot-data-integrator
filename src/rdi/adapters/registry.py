# src/rdi/adapters/registry.py
"""Adapter 注册表与多源查找调度。

根据数据需求类型自动选择 Adapter，
主源失败自动切换备选源。
"""

from rdi.adapters.base import BaseAdapter
from rdi.models.common import DataReqType  # noqa: I001 — 模块级导入，延迟导入在函数内

# ─── Adapter 注册表 ───
ADAPTER_REGISTRY: dict[DataReqType, list[str]] = {
    DataReqType.PAPER: [
        "ArxivAdapter",
        "PapersWithCodeAdapter",
        "IEEEXploreAdapter",
    ],
    DataReqType.CODE: [
        "GitHubAdapter",
        "HuggingFaceAdapter",
        "PapersWithCodeAdapter",
    ],
    DataReqType.DATASET: [
        "GitHubAdapter",
        "HuggingFaceAdapter",
        "ZenodoAdapter",
        "GraspNetAdapter",
        "DexGraspAdapter",
        "YCBAdapter",
    ],
    DataReqType.ROBOT_URDF: [
        "FrankaAdapter",
        "AllegroAdapter",
        "RobotiqAdapter",
        "GitHubAdapter",
    ],
    DataReqType.MESH: ["YCBAdapter", "GoogleScannedAdapter", "GraspNetAdapter"],
    DataReqType.GRASP: ["GraspNetAdapter", "DexGraspAdapter", "YCBAdapter"],
    DataReqType.SIM_CONFIG: ["MuJoCoAdapter", "IsaacSimAdapter"],
    DataReqType.POLICY_MODEL: ["HuggingFaceAdapter", "GitHubAdapter"],
    DataReqType.SENSOR_DATA: ["GitHubAdapter", "ZenodoAdapter"],
}


# ─── DataSource 优先级映射（供 Hermes 策略演化查询） ───
def get_sources_for_type(req_type: DataReqType) -> list[str]:
    """返回指定需求类型的候选数据源名称（按优先级排序）。

    供 Hermes 策略演化模块查询候选数据源。
    """
    from rdi.models.common import DataSource

    source_name_map: dict[str, str] = {
        "ArxivAdapter": DataSource.ARXIV,
        "IEEEXploreAdapter": DataSource.IEEE,
        "GitHubAdapter": DataSource.GITHUB,
        "PapersWithCodeAdapter": DataSource.PAPERSWITHCODE,
        "HuggingFaceAdapter": DataSource.HUGGINGFACE,
        "ZenodoAdapter": DataSource.ZENODO,
        "GraspNetAdapter": DataSource.GRASPNET,
        "DexGraspAdapter": DataSource.DEXGRASP,
        "YCBAdapter": DataSource.YCB,
        "GoogleScannedAdapter": DataSource.GOOGLE_SCANNED,
        "FrankaAdapter": DataSource.FRANKA,
        "AllegroAdapter": DataSource.ALLEGRO,
        "RobotiqAdapter": DataSource.ROBOTIQ,
        "MuJoCoAdapter": DataSource.MUJOCO,
        "IsaacSimAdapter": DataSource.ISAAC,
    }
    names = ADAPTER_REGISTRY.get(req_type, [])
    return [source_name_map[n] for n in names if n in source_name_map]


def select_adapter(req_type: DataReqType) -> list[type[BaseAdapter]]:
    """根据数据需求类型返回候选 Adapter 列表。

    列表按优先级排序：第一个是主源，后续是备选源。
    使用延迟导入避免循环依赖。
    """
    names = ADAPTER_REGISTRY.get(req_type, [])

    # 延迟导入，避免循环依赖
    from rdi.adapters.allegro import AllegroAdapter
    from rdi.adapters.arxiv import ArxivAdapter
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
    from rdi.adapters.robotiq import RobotiqAdapter
    from rdi.adapters.ycb import YCBAdapter
    from rdi.adapters.zenodo import ZenodoAdapter

    adapters_map: dict[str, type[BaseAdapter]] = {
        "ArxivAdapter": ArxivAdapter,
        "GitHubAdapter": GitHubAdapter,
        "GraspNetAdapter": GraspNetAdapter,
        "YCBAdapter": YCBAdapter,
        "FrankaAdapter": FrankaAdapter,
        "HuggingFaceAdapter": HuggingFaceAdapter,
        "ZenodoAdapter": ZenodoAdapter,
        "DexGraspAdapter": DexGraspAdapter,
        "GoogleScannedAdapter": GoogleScannedAdapter,
        "RobotiqAdapter": RobotiqAdapter,
        "AllegroAdapter": AllegroAdapter,
        "MuJoCoAdapter": MuJoCoAdapter,
        "IsaacSimAdapter": IsaacSimAdapter,
        "IEEEXploreAdapter": IEEEXploreAdapter,
        "PapersWithCodeAdapter": PapersWithCodeAdapter,
    }
    return [adapters_map[name] for name in names if name in adapters_map]
