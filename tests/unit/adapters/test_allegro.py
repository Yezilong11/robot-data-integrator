"""AllegroAdapter 的单元测试。"""

import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import yourdfpy

from rdi.adapters.allegro import _FALLBACK_MODELS, AllegroAdapter
from rdi.exceptions import AdapterCatalogError, AdapterError
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


class TestAllegroAdapter:
    """AllegroAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = AllegroAdapter()
        assert adapter.source == DataSource.ALLEGRO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确（C7 修复后走 pal-robotics）。"""
        adapter = AllegroAdapter()
        assert (
            adapter.base_url
            == "https://raw.githubusercontent.com/pal-robotics/allegro_hand/93d7154068345a7e6496654b91c14db93818d9b3"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = AllegroAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            results = await adapter.search("allegro")
        assert len(results) > 0
        assert results[0].source == DataSource.ALLEGRO
        assert "allegro" in results[0].item_id
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_raises_catalog_error(self) -> None:
        """路径 B 无匹配时抛 AdapterCatalogError（有源但未收录，不静默空）。"""
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            with pytest.raises(AdapterCatalogError) as exc_info:
                await adapter.search("zzznomatchxyz")
        assert "仅收录" in exc_info.value.message
        assert "有源但未收录" in exc_info.value.message
        assert f"仅收录 {len(_FALLBACK_MODELS)}" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_search_fallback_kinova_query_does_not_match(self) -> None:
        """D4 回归：Kinova 查询不得误命中 Allegro（描述含英文 "urdf" 曾导致误命中）。

        原实现 query 词元与模型任一字段词元有交集即命中，带 "urdf" 的任意查询
        （如 "kinova gen3 urdf"）会匹配 right/left 型号 → ms_003 req_000 拿到
        Allegro 手而非 Kinova Gen3。收紧后应抛 AdapterCatalogError（未收录）。
        """
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            with pytest.raises(AdapterCatalogError):
                await adapter.search("kinova gen3 urdf")

    @pytest.mark.asyncio
    async def test_search_fallback_urdf_token_does_not_match(self) -> None:
        """D4 二次回归：独立 "URDF" 格式词不得经归一化子串误命中。

        原 D4 收紧后，归一化子串检查的匹配文本仍含 description——"URDF" 是
        描述 "Allegro 右手 URDF 模型" 的子串，绕过 token 收紧规则再次误命中
        （ms_003 复测 req_000 又拿到 Allegro 手）。子串文本收紧为 id/title
        后，"URDF" 应抛 AdapterCatalogError。
        """
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            with pytest.raises(AdapterCatalogError):
                await adapter.search("URDF")
            with pytest.raises(AdapterCatalogError):
                await adapter.search("机器人 URDF")

    @pytest.mark.asyncio
    async def test_search_fallback_allegro_hand_urdf_still_matches(self) -> None:
        """D4 回归：allegro 自身查询（含通用词 urdf）仍命中（标识性 token 交集）。"""
        adapter = AllegroAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.ALLEGRO.value
            )
            results = await adapter.search("allegro hand urdf")
        assert len(results) > 0
        assert results[0].source == DataSource.ALLEGRO

    @pytest.mark.asyncio
    async def test_fetch_v4_plain_urdf(self) -> None:
        """C2 修复：allegro_hand_v4 返回 dexsuite 已展开纯 URDF。"""
        adapter = AllegroAdapter()
        fake_urdf = b"""<?xml version="1.0"?>
<robot name="allegro_right">
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
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ) as mock_dl:
            raw = await adapter.fetch("allegro_hand_v4")
        assert raw.source == DataSource.ALLEGRO
        assert raw.format == "urdf"
        assert raw.data == fake_urdf
        assert raw.url.endswith("allegro_hand_right.urdf")
        _assert_urdf_parseable(raw.data)
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_left_plain_urdf(self) -> None:
        """C2 修复：allegro_hand_left 返回 dexsuite 已展开纯 URDF。"""
        adapter = AllegroAdapter()
        fake_urdf = b"""<?xml version="1.0"?>
<robot name="allegro_left">
  <link name="base"/>
</robot>
"""
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_urdf
        ) as mock_dl:
            raw = await adapter.fetch("allegro_hand_left")
        assert raw.source == DataSource.ALLEGRO
        assert raw.format == "urdf"
        assert raw.url.endswith("allegro_hand_left.urdf")
        _assert_urdf_parseable(raw.data)
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_v3_xacro_format(self) -> None:
        """C2 修复：allegro_hand_v3 无稳定纯 URDF，返回 xacro 并标记 format="xacro"。"""
        adapter = AllegroAdapter()
        fake_xacro = b'<robot xmlns:xacro="http://www.ros.org/wiki/xacro" name="allegro_hand"/>'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_xacro
        ) as mock_dl:
            raw = await adapter.fetch("allegro_hand_v3")
        assert raw.source == DataSource.ALLEGRO
        assert raw.format == "xacro"
        assert raw.url.endswith("allegro_hand.urdf.xacro")
        assert raw.data == fake_xacro
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_fail_raises(self) -> None:
        """C7 修复后：单路径 fetch 失败直接抛 AdapterError。"""
        adapter = AllegroAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            mock_dl.side_effect = AdapterError(
                message="download failed", source=DataSource.ALLEGRO.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("allegro_hand_v4")
        # C7: 单路径，只尝试一次
        mock_dl.assert_awaited_once()
