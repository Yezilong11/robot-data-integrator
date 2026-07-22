# src/rdi/adapters/registry.py
"""Adapter 注册表与多源查找调度。

根据数据需求类型自动选择 Adapter，
主源失败自动切换备选源。
"""

from rdi.models.common import DataReqType  # noqa: I001 — 模块级导入，延迟导入在函数内


# ─── Adapter 注册表 ───
ADAPTER_REGISTRY: dict[DataReqType, list[str]] = {
    DataReqType.PAPER: ["ArxivAdapter", "IEEEXploreAdapter"],
    DataReqType.CODE: ["GitHubAdapter", "PapersWithCodeAdapter"],
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


def select_adapter(req_type: DataReqType) -> list[type]:
    """根据数据需求类型返回候选 Adapter 列表。

    列表按优先级排序：第一个是主源，后续是备选源。
    使用延迟导入避免循环依赖。
    """
    names = ADAPTER_REGISTRY.get(req_type, [])

    # 延迟导入，避免循环依赖
    from rdi.adapters.arxiv import ArxivAdapter
    from rdi.adapters.github import GitHubAdapter

    adapters_map: dict[str, type] = {
        "ArxivAdapter": ArxivAdapter,
        "GitHubAdapter": GitHubAdapter,
        # 其他 Adapter 随着开发逐步注册：
        # "IEEEXploreAdapter": IEEEXploreAdapter,
        # "PapersWithCodeAdapter": PapersWithCodeAdapter,
        # "GraspNetAdapter": GraspNetAdapter,
        # "DexGraspAdapter": DexGraspAdapter,
        # "YCBAdapter": YCBAdapter,
        # "GoogleScannedAdapter": GoogleScannedAdapter,
        # "FrankaAdapter": FrankaAdapter,
        # "AllegroAdapter": AllegroAdapter,
        # "RobotiqAdapter": RobotiqAdapter,
        # "MuJoCoAdapter": MuJoCoAdapter,
        # "IsaacSimAdapter": IsaacSimAdapter,
        # "HuggingFaceAdapter": HuggingFaceAdapter,
        # "ZenodoAdapter": ZenodoAdapter,
    }
    return [adapters_map[name] for name in names if name in adapters_map]
