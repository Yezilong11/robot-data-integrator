import pytest

from rdi.adapters import get_adapter
from rdi.models.common import DataSource

# LOCAL 为前端本地文件注入专用源（无网络适配器），不参与适配器构造测试
_NETWORK_SOURCES = [s for s in DataSource if s is not DataSource.LOCAL]


@pytest.mark.parametrize("source", _NETWORK_SOURCES)
def test_adapter_can_be_constructed(source: DataSource) -> None:
    adapter = get_adapter(source)
    assert adapter is not None
    assert adapter.source == source
