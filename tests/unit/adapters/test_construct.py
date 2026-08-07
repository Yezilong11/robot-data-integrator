import pytest

from rdi.adapters import get_adapter
from rdi.models.common import DataSource


@pytest.mark.parametrize("source", DataSource)
def test_adapter_can_be_constructed(source: DataSource) -> None:
    adapter = get_adapter(source)
    assert adapter is not None
    assert adapter.source == source
