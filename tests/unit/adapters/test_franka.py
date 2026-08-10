"""FrankaAdapter 的单元测试。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yourdfpy

from rdi.adapters.franka import FrankaAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试互相污染仓库 data/cache/。"""
    monkeypatch.setattr(FrankaAdapter, "cache_root", lambda self: tmp_path)


def _assert_urdf_parseable(data: bytes) -> None:
    """使用 yourdfpy 解析 URDF 字节并断言至少含一个 link。"""
    with tempfile.NamedTemporaryFile(suffix=".urdf", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        robot = yourdfpy.URDF.load(tmp_path, load_meshes=False)
        assert robot.link_map
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class TestFrankaAdapter:
    """FrankaAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = FrankaAdapter()
        assert adapter.source == DataSource.FRANKA

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = FrankaAdapter()
        assert (
            adapter.base_url == "https://raw.githubusercontent.com/frankaemika/franka_ros/develop"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = FrankaAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = FrankaAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            results = await adapter.search("panda")
        assert len(results) > 0
        assert results[0].source == DataSource.FRANKA
        assert "panda" in results[0].item_id
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = FrankaAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_primary_success(self) -> None:
        """路径 A 成功：mock _download_bytes 返回数据，format 为 urdf。"""
        adapter = FrankaAdapter()
        fake_urdf = b'<robot name="panda"/>'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ):
            raw = await adapter.fetch("panda")
        assert raw.source == DataSource.FRANKA
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.size_bytes == len(fake_urdf)
        assert raw.size_bytes > 0

    @pytest.mark.asyncio
    async def test_fetch_fills_assets_for_mesh_references(self) -> None:
        """P0-3：URDF 引用相对 mesh 时，fetch 返回的 raw.assets 携带资产字节。"""
        adapter = FrankaAdapter()
        fake_urdf = (
            b'<robot name="panda"><link name="base"><visual><geometry>'
            b'<mesh filename="meshes/base.stl"/>'
            b"</geometry></visual></link></robot>"
        )
        with patch.object(
            adapter,
            "_download_bytes",
            new_callable=AsyncMock,
            side_effect=[fake_urdf, b"stl-data"],
        ) as mock_dl:
            raw = await adapter.fetch("panda")
        assert raw.assets == {"meshes/base.stl": b"stl-data"}
        # 主 URDF 一次 + mesh 资产一次
        assert mock_dl.await_count == 2
        assert mock_dl.call_args_list[1].args[0].endswith("meshes/base.stl")

    @pytest.mark.asyncio
    async def test_fetch_fallback_panda_plain_urdf(self) -> None:
        """路径 B：panda 返回已展开纯 URDF，可被 yourdfpy 解析。"""
        adapter = FrankaAdapter()
        fake_urdf = b"""<?xml version="1.0"?>
<robot name="panda">
  <link name="base"/>
  <joint name="j1" type="revolute">
    <parent link="base"/>
    <child link="link1"/>
    <axis xyz="0 0 1"/>
    <limit effort="10" lower="-1" upper="1" velocity="1"/>
  </joint>
  <link name="link1"/>
</robot>
"""
        with (
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
            ) as mock_dl,
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
        ):
            mock_primary.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            raw = await adapter.fetch("panda")
        assert raw.source == DataSource.FRANKA
        assert raw.format == "urdf"
        assert raw.url.endswith("panda.urdf")
        _assert_urdf_parseable(raw.data)
        mock_primary.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_fallback_fr3_xacro_format(self) -> None:
        """路径 B：fr3 无稳定纯 URDF，返回 xacro 并标记 format="xacro"。"""
        adapter = FrankaAdapter()
        fake_xacro = b'<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="fr3"/>'
        with (
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_xacro
            ) as mock_dl,
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
        ):
            mock_primary.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            raw = await adapter.fetch("fr3")
        assert raw.source == DataSource.FRANKA
        assert raw.format == "xacro"
        assert raw.url.endswith(".urdf.xacro")
        assert raw.data == fake_xacro
        mock_primary.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_both_paths_fail_raises(self) -> None:
        """路径 A 和路径 B 都失败时抛 AdapterError，确认尝试两次下载。"""
        adapter = FrankaAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = AdapterError(
                message="download failed", source=DataSource.FRANKA.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("panda")
        # 路径 A + 路径 B 各一次下载尝试
        assert mock_dl.await_count == 2

    @pytest.mark.asyncio
    async def test_fetch_prefers_local_cache(self, tmp_path, monkeypatch) -> None:
        """首次 fetch 触发下载并落盘；二次 fetch 命中缓存不再触发网络。"""
        adapter = FrankaAdapter()
        monkeypatch.setattr(adapter, "cache_root", lambda: tmp_path)
        fake_urdf = b'<robot name="panda"/>'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ) as mock_dl:
            raw1 = await adapter.fetch("panda")
            raw2 = await adapter.fetch("panda")
        assert raw1.data == fake_urdf
        assert raw2.data == fake_urdf
        assert raw1.format == "urdf"
        # 仅首次触发下载；二次命中本地缓存
        mock_dl.assert_awaited_once()
        cache_file = tmp_path / "panda.urdf"
        assert cache_file.is_file()
        assert cache_file.read_bytes() == fake_urdf
