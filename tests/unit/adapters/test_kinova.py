"""KinovaAdapter 单元测试（D4 新增）。

覆盖：search token 匹配与 AdapterCatalogError；fetch 剥离 package:// 并以
仓库根 URL（self.base_url）收集 mesh 资产（D4 修复：不能用 URDF 文件 URL 拼接）。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.kinova import _FALLBACK_MODELS, KinovaAdapter
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource

_URDF = (
    b'<?xml version="1.0"?>\n'
    b'<robot name="gen3">\n'
    b'  <link name="base_link">\n'
    b'    <visual><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/base_link.STL"/></geometry></visual>\n'
    b'    <collision><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/base_link.STL"/></geometry></collision>\n'
    b'  </link>\n'
    b'  <link name="shoulder_link">\n'
    b'    <visual><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/shoulder_link.STL"/></geometry></visual>\n'
    b'  </link>\n'
    b'</robot>\n'
)


class TestKinovaAdapter:
    def test_adapter_source(self) -> None:
        adapter = KinovaAdapter()
        assert adapter.source == DataSource.KINOVA

    @pytest.mark.asyncio
    async def test_search_matches_gen3(self) -> None:
        adapter = KinovaAdapter()
        results = await adapter.search("Kinova Gen3")
        assert len(results) > 0
        assert results[0].source == DataSource.KINOVA
        assert results[0].item_id == "gen3"

    @pytest.mark.asyncio
    async def test_search_unknown_raises_catalog_error(self) -> None:
        adapter = KinovaAdapter()
        with pytest.raises(AdapterCatalogError) as exc_info:
            await adapter.search("zzznomatchxyz")
        assert "有源但未收录" in exc_info.value.message
        assert f"仅收录 {len(_FALLBACK_MODELS)}" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_fetch_collects_assets_from_repo_root(self) -> None:
        """D4 修复：资产下载 URL 必须以仓库根（self.base_url）拼接，而非 URDF 文件 URL。"""
        adapter = KinovaAdapter()

        async def fake_download(url: str) -> bytes:
            if url.endswith("GEN3-6DOF_VISION_URDF_ARM_V01.urdf"):
                return _URDF
            if url.endswith("meshes/base_link.STL"):
                return b"stl-base"
            if url.endswith("meshes/shoulder_link.STL"):
                return b"stl-shoulder"
            raise AdapterError(message=f"unexpected url: {url}", source="kinova")

        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = fake_download
            raw = await adapter.fetch("gen3")

        assert raw.format == "urdf"
        assert raw.source == DataSource.KINOVA
        # 仅剥离 package://，保留包名 kortex_description/...（仓库根相对路径）
        assert b"package://" not in raw.data
        assert b'filename="kortex_description/arms/gen3/6dof/meshes/base_link.STL"' in raw.data
        # 资产键与 URDF 引用一致（包内 robots/{ref} 落盘可自洽加载）
        assert raw.assets == {
            "kortex_description/arms/gen3/6dof/meshes/base_link.STL": b"stl-base",
            "kortex_description/arms/gen3/6dof/meshes/shoulder_link.STL": b"stl-shoulder",
        }
        # 所有下载 URL 都以仓库根 base_url 为前缀，且不含 URDF 文件 URL 拼接
        for call in mock_dl.await_args_list:
            url = call.args[0]
            assert url.startswith(adapter.base_url + "/")
            assert "GEN3-6DOF_VISION_URDF_ARM_V01.urdf/" not in url
        # 资产 URL 命中真实仓库路径（含 kortex_description 前缀）
        assert (
            "https://raw.githubusercontent.com/Kinovarobotics/ros_kortex/noetic-devel/"
            "kortex_description/arms/gen3/6dof/meshes/base_link.STL"
            in [c.args[0] for c in mock_dl.await_args_list]
        )
