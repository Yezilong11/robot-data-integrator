# src/rdi/adapters/registry.py
"""数据源注册表：DataReqType -> 候选 DataSource 列表。

供 Hermes 策略演化模块查询候选数据源，按优先级排序，最常用的排在前面。
"""

from rdi.models import DataReqType, DataSource

# ponytail: 当前仅为静态映射，C 工程师后续在此注册真实 Adapter 类
# （如 ArxivAdapter、GitHubAdapter 等），升级路径为
# dict[DataReqType, list[type[Adapter]]]。
ADAPTER_REGISTRY: dict[str, list[DataSource]] = {
    DataReqType.PAPER: [
        DataSource.ARXIV,
        DataSource.IEEE,
        DataSource.PAPERSWITHCODE,
    ],
    DataReqType.CODE: [
        DataSource.GITHUB,
        DataSource.PAPERSWITHCODE,
    ],
    DataReqType.DATASET: [
        DataSource.GITHUB,
        DataSource.HUGGINGFACE,
        DataSource.ZENODO,
        DataSource.GRASPNET,
    ],
    DataReqType.ROBOT_URDF: [
        DataSource.FRANKA,
        DataSource.ROBOTIQ,
        DataSource.ALLEGRO,
        DataSource.GITHUB,
    ],
    DataReqType.MESH: [
        DataSource.YCB,
        DataSource.GOOGLE_SCANNED,
        DataSource.GITHUB,
    ],
    DataReqType.GRASP: [
        DataSource.GRASPNET,
        DataSource.DEXGRASP,
        DataSource.YCB,
    ],
    DataReqType.SIM_CONFIG: [
        DataSource.MUJOCO,
        DataSource.ISAAC,
    ],
    DataReqType.POLICY_MODEL: [
        DataSource.HUGGINGFACE,
        DataSource.GITHUB,
    ],
    DataReqType.SENSOR_DATA: [
        DataSource.GITHUB,
        DataSource.ZENODO,
    ],
}
