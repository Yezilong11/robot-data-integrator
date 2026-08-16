"""FrankaAdapter 的单元测试。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yourdfpy

from rdi.adapters.franka import _FALLBACK_MODELS, FrankaAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
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
            adapter.base_url
            == "https://raw.githubusercontent.com/frankarobotics/franka_ros/ddd2fffd9de44b02ad15b4bbb2bfa2cec4d60d98"
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
    async def test_search_fallback_no_match_raises_catalog_error(self) -> None:
        """路径 B 无匹配时抛 AdapterCatalogError（有源但未收录，不静默空）。"""
        adapter = FrankaAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            with pytest.raises(AdapterCatalogError) as exc_info:
                await adapter.search("zzznomatchxyz")
        assert "仅收录" in exc_info.value.message
        assert "有源但未收录" in exc_info.value.message
        assert f"仅收录 {len(_FALLBACK_MODELS)}" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_search_fallback_robot_generic_word_does_not_match(self) -> None:
        """D4 回归：泛词 "机器人" 不得经描述子串误命中 Franka。

        emika_panda 描述"协作机器人"含 "机器人"，原实现 `query_lower in
        description` 让任意带独立 "机器人" query（如 Kinova 类请求）误命中
        Franka Panda。收紧后应抛 AdapterCatalogError（未收录）。
        """
        adapter = FrankaAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.FRANKA.value
            )
            with pytest.raises(AdapterCatalogError):
                await adapter.search("机器人")
            with pytest.raises(AdapterCatalogError):
                await adapter.search("URDF")

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

    @pytest.mark.asyncio
    async def test_primary_and_fallback_cache_keys_distinct(self) -> None:
        """B3：主路径与降级路径的磁盘缓存文件互不覆盖。"""
        adapter = FrankaAdapter()
        primary_bytes = b'<robot name="panda-primary"/>'
        fallback_bytes = b'<robot name="panda-fallback"/>'
        with (
            patch.object(
                adapter,
                "_download_bytes",
                new_callable=AsyncMock,
                side_effect=[primary_bytes, fallback_bytes],
            ),
            patch.object(
                adapter,
                "_download_xml_with_assets",
                new_callable=AsyncMock,
                return_value={},
            ),
        ):
            raw_primary = await adapter._fetch_primary("panda")
            raw_fallback = await adapter._fetch_fallback("panda")
        primary_path = adapter.get_cache_path("panda", ".urdf")
        fallback_path = adapter.get_cache_path("panda", ".urdf.fallback")
        assert primary_path != fallback_path
        assert primary_path.is_file() and fallback_path.is_file()
        assert primary_path.read_bytes() == primary_bytes
        assert fallback_path.read_bytes() == fallback_bytes
        assert raw_primary.data == primary_bytes
        assert raw_fallback.data == fallback_bytes
        # 降级路径写入后主路径内容仍在（未互相覆盖）
        raw_primary2 = await adapter._fetch_primary("panda")
        assert raw_primary2.data == primary_bytes


class TestFrankaAdapterLocalDatasets:
    """D3：来源级本地数据集挂载（settings.local_datasets）测试。

    本地挂载目录即 franka_ros/pybullet_robots 仓库根镜像，相对路径与
    GitHub raw URL 同构；命中返回 source=LOCAL，不发起任何网络请求。
    """

    @pytest.mark.asyncio
    async def test_fetch_local_panda_hit_no_network(self, tmp_path, monkeypatch) -> None:
        """panda 本地命中 data/franka_panda/panda.urdf：无网络请求。"""
        local_root = tmp_path / "dataset"
        urdf_dir = local_root / "data" / "franka_panda"
        urdf_dir.mkdir(parents=True)
        fake_urdf = b'<robot name="panda"/>'
        (urdf_dir / "panda.urdf").write_bytes(fake_urdf)
        monkeypatch.setattr(settings, "local_datasets", {"franka": str(local_root)})
        adapter = FrankaAdapter()
        with (
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
            patch.object(adapter, "_fetch_fallback", new_callable=AsyncMock) as mock_fallback,
        ):
            raw = await adapter.fetch("panda")
        assert raw.source == DataSource.LOCAL
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.url == "local://franka/data/franka_panda/panda.urdf"
        mock_primary.assert_not_awaited()
        mock_fallback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_fr3_xacro_hit(self, tmp_path, monkeypatch) -> None:
        """fr3 本地命中 franka_description/robots/fr3/fr3.urdf.xacro。"""
        local_root = tmp_path / "dataset"
        xacro_dir = local_root / "franka_description" / "robots" / "fr3"
        xacro_dir.mkdir(parents=True)
        fake_xacro = b'<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="fr3"/>'
        (xacro_dir / "fr3.urdf.xacro").write_bytes(fake_xacro)
        monkeypatch.setattr(settings, "local_datasets", {"franka": str(local_root)})
        adapter = FrankaAdapter()
        with (
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
            patch.object(adapter, "_fetch_fallback", new_callable=AsyncMock) as mock_fallback,
        ):
            raw = await adapter.fetch("fr3")
        assert raw.source == DataSource.LOCAL
        assert raw.format == "xacro"
        assert raw.data == fake_xacro
        assert raw.url == "local://franka/franka_description/robots/fr3/fr3.urdf.xacro"
        mock_primary.assert_not_awaited()
        mock_fallback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_urdf_assets_from_local(self, tmp_path, monkeypatch) -> None:
        """本地命中 URDF 引用的 mesh 资产从本地读取（不发网络）。"""
        local_root = tmp_path / "dataset"
        urdf_dir = local_root / "data" / "franka_panda"
        meshes_dir = urdf_dir / "meshes"
        meshes_dir.mkdir(parents=True)
        fake_urdf = (
            b'<robot name="panda"><link name="base"><visual><geometry>'
            b'<mesh filename="meshes/base.stl"/>'
            b"</geometry></visual></link></robot>"
        )
        (urdf_dir / "panda.urdf").write_bytes(fake_urdf)
        (meshes_dir / "base.stl").write_bytes(b"stl-data")
        monkeypatch.setattr(settings, "local_datasets", {"franka": str(local_root)})
        adapter = FrankaAdapter()
        with (
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
            patch.object(adapter, "_fetch_fallback", new_callable=AsyncMock) as mock_fallback,
        ):
            raw = await adapter.fetch("panda")
        assert raw.source == DataSource.LOCAL
        assert raw.assets == {"data/franka_panda/meshes/base.stl": b"stl-data"}
        mock_primary.assert_not_awaited()
        mock_fallback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_fetch_local_miss_falls_back_to_network(self, tmp_path, monkeypatch) -> None:
        """本地挂载无目标文件时走网络（主路径失败降级，行为与未配置一致）。"""
        local_root = tmp_path / "dataset"
        local_root.mkdir()  # 挂载存在但为空
        monkeypatch.setattr(settings, "local_datasets", {"franka": str(local_root)})
        adapter = FrankaAdapter()
        fake_urdf = b'<robot name="panda"/>'
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
        assert raw.data == fake_urdf
        mock_primary.assert_awaited_once()
        mock_dl.assert_awaited_once()
