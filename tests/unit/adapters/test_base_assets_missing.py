# tests/unit/adapters/test_base_assets_missing.py
"""P0-C：外部资源下载失败显性化（assets_missing）测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.base import BaseAdapter
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class _StubAdapter(BaseAdapter):
    """测试用 Adapter 桩：仅用于调用资产收集逻辑。"""

    source = DataSource.ARXIV

    def __init__(self) -> None:
        super().__init__(base_url="http://localhost:9999", rate_limit=5)

    async def search(self, query: str) -> list[SearchResult]:
        return []

    async def fetch(self, item_id: str) -> RawData:
        raise NotImplementedError


_XML = (
    b'<robot name="r"><link name="base"><visual><geometry>'
    b'<mesh filename="meshes/base.stl"/>'
    b"</geometry></visual></link></robot>"
)


@pytest.mark.asyncio
async def test_download_failure_records_assets_missing() -> None:
    """P0-C：资产下载失败时 missing 记录该路径，assets 不含该项。"""
    adapter = _StubAdapter()
    with patch.object(
        adapter,
        "_download_bytes",
        new_callable=AsyncMock,
        side_effect=RuntimeError("network down"),
    ):
        assets, missing = await adapter._download_xml_with_assets(
            "https://example.com/models/panda.urdf", _XML
        )
    assert assets == {}
    assert missing == ["meshes/base.stl"]


@pytest.mark.asyncio
async def test_partial_failure_records_only_failed() -> None:
    """P0-C：多个资产时仅下载失败的路径进入 missing，成功项仍进 assets。"""
    adapter = _StubAdapter()
    xml = b'<robot name="r"><mesh filename="a.stl"/><mesh filename="b.stl"/></robot>'

    def fake(url: str) -> bytes:
        if url.endswith("/models/a.stl"):
            return b"a-stl"
        raise RuntimeError("b down")

    with patch.object(
        adapter,
        "_download_bytes",
        new_callable=AsyncMock,
        side_effect=fake,
    ):
        assets, missing = await adapter._download_xml_with_assets(
            "https://example.com/models/panda.urdf", xml
        )
    assert assets == {"a.stl": b"a-stl"}
    assert missing == ["b.stl"]


@pytest.mark.asyncio
async def test_success_records_empty_missing() -> None:
    """P0-C：全部资产下载成功时不误报 missing；非法 XML 同样返回空缺失。"""
    adapter = _StubAdapter()
    with patch.object(
        adapter,
        "_download_bytes",
        new_callable=AsyncMock,
        return_value=b"stl-data",
    ):
        assets, missing = await adapter._download_xml_with_assets(
            "https://example.com/models/panda.urdf", _XML
        )
    assert assets == {"meshes/base.stl": b"stl-data"}
    assert missing == []
    # XML 解析失败：assets 与 missing 均为空，不抛异常
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
        assets2, missing2 = await adapter._download_xml_with_assets(
            "https://example.com/models/panda.urdf", b"not <xml"
        )
    assert (assets2, missing2) == ({}, [])
    mock_dl.assert_not_awaited()
