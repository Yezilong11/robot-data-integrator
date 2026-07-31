"""数据连接层：数据源 Adapter 与注册表。"""

from collections.abc import Callable

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
from rdi.adapters.registry import ADAPTER_REGISTRY, get_sources_for_type, select_adapter
from rdi.adapters.robotiq import RobotiqAdapter
from rdi.adapters.semanticscholar import SemanticScholarAdapter
from rdi.adapters.ycb import YCBAdapter
from rdi.adapters.zenodo import ZenodoAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource

# 方案 A：静态工厂字典（SOP 2.2.1 决策）
# 使用 Callable[[], BaseAdapter] 而非 type[BaseAdapter]，因为子类 __init__(self) 无参
_ADAPTER_CLASSES: dict[DataSource, Callable[[], BaseAdapter]] = {
    DataSource.ARXIV: ArxivAdapter,
    DataSource.IEEE: IEEEXploreAdapter,
    DataSource.GITHUB: GitHubAdapter,
    DataSource.PAPERSWITHCODE: PapersWithCodeAdapter,
    DataSource.HUGGINGFACE: HuggingFaceAdapter,
    DataSource.GRASPNET: GraspNetAdapter,
    DataSource.DEXGRASP: DexGraspAdapter,
    DataSource.YCB: YCBAdapter,
    DataSource.GOOGLE_SCANNED: GoogleScannedAdapter,
    DataSource.ZENODO: ZenodoAdapter,
    DataSource.FRANKA: FrankaAdapter,
    DataSource.ALLEGRO: AllegroAdapter,
    DataSource.ROBOTIQ: RobotiqAdapter,
    DataSource.MUJOCO: MuJoCoAdapter,
    DataSource.ISAAC: IsaacSimAdapter,
    DataSource.SEMANTIC_SCHOLAR: SemanticScholarAdapter,
}


def get_adapter(source: DataSource) -> BaseAdapter:
    """根据 DataSource 枚举返回对应的 Adapter 实例。

    Args:
        source: 数据源枚举值

    Returns:
        Adapter 实例

    Raises:
        AdapterError: 未知数据源
    """
    cls = _ADAPTER_CLASSES.get(source)
    if cls is None:
        raise AdapterError(f"Unknown data source: {source}", source=source.value)
    return cls()


__all__ = [
    "ADAPTER_REGISTRY",
    "get_adapter",
    "get_sources_for_type",
    "select_adapter",
]
