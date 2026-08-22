# tests/unit/adapters/test_kinova_assets.py
"""kinova 资产缺失显性化（assets_missing）测试。

覆盖 spec「kinova 资产缺失显性化」的三个场景：
- 网络资产下载部分失败 → metadata["assets_missing"] 含失败引用、成功资产仍入 assets
- 资产全部下载成功 → 无 assets_missing（行为与修复前一致）
- 本地挂载路径缺 mesh 文件 → 命中 _local_raw 同样产生 assets_missing
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.kinova import KinovaAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource

_URDF = (
    b'<?xml version="1.0"?>\n'
    b'<robot name="gen3">\n'
    b'  <link name="base_link">\n'
    b'    <visual><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/base_link.STL"/></geometry></visual>\n'
    b'    <collision><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/base_link.STL"/></geometry></collision>\n'
    b"  </link>\n"
    b'  <link name="shoulder_link">\n'
    b'    <visual><geometry><mesh filename="package://kortex_description/arms/gen3/6dof/meshes/shoulder_link.STL"/></geometry></visual>\n'
    b"  </link>\n"
    b"</robot>\n"
)

# 与 _FETCH_PATHS["gen3"] 同构的本地镜像相对路径（ros_kortex 仓库根镜像）
_URDF_REL = "kortex_description/arms/gen3/6dof/urdf/GEN3-6DOF_VISION_URDF_ARM_V01.urdf"

# package:// 剥离后（fetch 中 re.sub）的引用即仓库根相对路径
_BASE_STL = "kortex_description/arms/gen3/6dof/meshes/base_link.STL"
_SHOULDER_STL = "kortex_description/arms/gen3/6dof/meshes/shoulder_link.STL"


@pytest.mark.asyncio
async def test_network_partial_failure_records_assets_missing() -> None:
    """spec：网络资产下载部分失败 → assets_missing 含失败引用、成功资产仍入 assets。"""
    adapter = KinovaAdapter()

    async def fake_download(url: str) -> bytes:
        if url.endswith(_URDF_REL):
            return _URDF
        if url.endswith("meshes/base_link.STL"):
            return b"stl-base"
        raise AdapterError(message=f"download failed: {url}", source="kinova")

    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
        mock_dl.side_effect = fake_download
        raw = await adapter.fetch("gen3")

    assert raw.source == DataSource.KINOVA
    assert raw.assets == {_BASE_STL: b"stl-base"}
    assert raw.metadata["assets_missing"] == [_SHOULDER_STL]


@pytest.mark.asyncio
async def test_network_all_success_no_assets_missing() -> None:
    """spec：资产全部下载成功 → 无 assets_missing（行为与修复前一致）。"""
    adapter = KinovaAdapter()

    async def fake_download(url: str) -> bytes:
        if url.endswith(_URDF_REL):
            return _URDF
        if url.endswith("meshes/base_link.STL"):
            return b"stl-base"
        if url.endswith("meshes/shoulder_link.STL"):
            return b"stl-shoulder"
        raise AdapterError(message=f"unexpected url: {url}", source="kinova")

    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
        mock_dl.side_effect = fake_download
        raw = await adapter.fetch("gen3")

    assert "assets_missing" not in raw.metadata
    assert raw.assets == {_BASE_STL: b"stl-base", _SHOULDER_STL: b"stl-shoulder"}


@pytest.mark.asyncio
async def test_local_mirror_missing_mesh_records_assets_missing(tmp_path, monkeypatch) -> None:
    """spec：本地挂载路径资产缺失 → 命中 _local_raw 同样产生 assets_missing。

    镜像目录含 URDF 但不含其引用的 mesh 文件（本地无对应文件即缺失，
    与网络分支下载失败同语义）；本地命中不发任何网络请求。
    """
    local_root = tmp_path / "dataset"
    urdf_path = local_root / _URDF_REL
    urdf_path.parent.mkdir(parents=True)
    urdf_path.write_bytes(_URDF)
    monkeypatch.setattr(settings, "local_datasets", {"kinova": str(local_root)})
    adapter = KinovaAdapter()
    with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
        raw = await adapter.fetch("gen3")

    assert raw.source == DataSource.LOCAL
    assert raw.assets == {}
    missing = raw.metadata["assets_missing"]
    # 缺失清单含 URDF 引用的 mesh（路径前缀由 base._local_assets_from_xml 按
    # 相对主 XML 目录拼接，故用结尾片段匹配引用文件名）
    assert any(m.endswith(_BASE_STL) for m in missing)
    assert any(m.endswith(_SHOULDER_STL) for m in missing)
    mock_dl.assert_not_awaited()