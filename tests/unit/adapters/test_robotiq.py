"""RobotiqAdapter 的单元测试。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yourdfpy

from rdi.adapters.robotiq import RobotiqAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


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


class TestRobotiqAdapter:
    """RobotiqAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = RobotiqAdapter()
        assert adapter.source == DataSource.ROBOTIQ

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确（C8 修复后走 ros-industrial-attic）。"""
        adapter = RobotiqAdapter()
        assert (
            adapter.base_url
            == "https://raw.githubusercontent.com/ros-industrial-attic/robotiq/kinetic-devel"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = RobotiqAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = RobotiqAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ROBOTIQ.value
            )
            results = await adapter.search("2f-85")
        assert len(results) > 0
        assert results[0].source == DataSource.ROBOTIQ
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = RobotiqAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ROBOTIQ.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_primary_success(self) -> None:
        """路径 A 成功：mock _download_bytes 返回数据，format 为 urdf。"""
        adapter = RobotiqAdapter()
        fake_urdf = b'<robot name="robotiq_2f_85"/>'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ):
            raw = await adapter.fetch("robotiq_2f_85")
        assert raw.source == DataSource.ROBOTIQ
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.size_bytes == len(fake_urdf)
        assert raw.size_bytes > 0

    @pytest.mark.asyncio
    async def test_fetch_fallback_3f_plain_urdf(self) -> None:
        """C2 修复：robotiq_3f_gripper 返回已展开纯 URDF，可被 yourdfpy 解析。"""
        adapter = RobotiqAdapter()
        fake_urdf = b"""<?xml version="1.0"?>
<robot name="robotiq_3f">
  <link name="base"/>
  <joint name="j1" type="revolute">
    <parent link="base"/>
    <child link="finger"/>
    <axis xyz="0 0 1"/>
    <limit effort="10" lower="-1" upper="1" velocity="1"/>
  </joint>
  <link name="finger"/>
</robot>
"""
        with (
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
            ) as mock_dl,
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
        ):
            mock_primary.side_effect = AdapterError(
                message="primary failed", source=DataSource.ROBOTIQ.value
            )
            raw = await adapter.fetch("robotiq_3f_gripper")
        assert raw.source == DataSource.ROBOTIQ
        assert raw.format == "urdf"
        assert raw.url.endswith(".urdf")
        _assert_urdf_parseable(raw.data)
        mock_primary.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_fallback_2f_xacro_format(self) -> None:
        """C2 修复：robotiq_2f_85 实际为 xacro，format 标记为 xacro。"""
        adapter = RobotiqAdapter()
        fake_xacro = b'<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="robotiq_2f_85"/>'
        with (
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_xacro
            ) as mock_dl,
            patch.object(adapter, "_fetch_primary", new_callable=AsyncMock) as mock_primary,
        ):
            mock_primary.side_effect = AdapterError(
                message="primary failed", source=DataSource.ROBOTIQ.value
            )
            raw = await adapter.fetch("robotiq_2f_85")
        assert raw.source == DataSource.ROBOTIQ
        assert raw.format == "xacro"
        assert raw.url.endswith(".xacro")
        assert raw.data == fake_xacro
        mock_primary.assert_awaited_once()
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_both_paths_fail_raises(self) -> None:
        """路径 A 和路径 B 都失败时抛 AdapterError，确认尝试两次下载。"""
        adapter = RobotiqAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = AdapterError(
                message="download failed", source=DataSource.ROBOTIQ.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("robotiq_2f_85")
        # 路径 A + 路径 B 各一次下载尝试
        assert mock_dl.await_count == 2
