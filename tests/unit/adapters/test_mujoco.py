# tests/unit/adapters/test_mujoco.py
"""MuJoCoAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.mujoco import _FALLBACK_SCENES, _FETCH_XML, MuJoCoAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestMuJoCoAdapter:
    """MuJoCoAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = MuJoCoAdapter()
        assert adapter.source == DataSource.MUJOCO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = MuJoCoAdapter()
        assert (
            adapter.base_url
            == "https://raw.githubusercontent.com/google-deepmind/mujoco_menagerie/main"
        )

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = MuJoCoAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B，返回硬编码匹配结果。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，验证降级到 fallback。
        """
        adapter = MuJoCoAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.MUJOCO.value
            )
            results = await adapter.search("aloha")
        assert len(results) > 0
        assert results[0].source == DataSource.MUJOCO
        assert "aloha" in results[0].item_id
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B 无匹配时返回空列表（不返回全量）。"""
        adapter = MuJoCoAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.MUJOCO.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_fallback_multi_token_match(self) -> None:
        """路径 B 支持多 token 查询：任一 token 命中即返回结果。"""
        adapter = MuJoCoAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.MUJOCO.value
            )
            results = await adapter.search("MuJoCo panda")
        assert len(results) > 0
        assert results[0].item_id == "franka_emika_panda"
        mock_scrape.assert_awaited_once()

    # ─── C13: 场景列表 / scene.xml 映射 / 关键词匹配 ───

    def test_fallback_scenes_include_unitree_go2(self) -> None:
        """C13：unitree_go2 加入降级场景列表，且每条记录均带 keywords。"""
        ids = {s["id"] for s in _FALLBACK_SCENES}
        assert "unitree_go2" in ids
        assert all("keywords" in s and s["keywords"] for s in _FALLBACK_SCENES)
        go2 = next(s for s in _FALLBACK_SCENES if s["id"] == "unitree_go2")
        assert go2["keywords"] == ["unitree", "go2", "quadruped"]

    def test_fetch_xml_uses_scene_xml_for_scene_scenes(self) -> None:
        """C13：franka_emika_panda 与 unitree_go2 均映射到规范的 scene.xml 场景文件。"""
        assert _FETCH_XML["unitree_go2"] == "unitree_go2/scene.xml"
        assert _FETCH_XML["franka_emika_panda"].endswith("franka_emika_panda/scene.xml")

    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        ("query", "expected_id"),
        [
            ("go2", "unitree_go2"),
            ("unitree robot", "unitree_go2"),
            ("spot", "boston_dynamics_spot"),
            ("boston dynamics", "boston_dynamics_spot"),
            ("panda", "franka_emika_panda"),
            ("viperx", "aloha"),
        ],
    )
    async def test_search_fallback_keyword_match(self, query: str, expected_id: str) -> None:
        """C13：keywords 参与 token 匹配，提升真实场景命中率。"""
        adapter = MuJoCoAdapter()
        with patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape:
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.MUJOCO.value
            )
            results = await adapter.search(query)
        assert any(r.item_id == expected_id for r in results)

    @pytest.mark.asyncio
    async def test_fetch_success(self) -> None:
        """C10 修复后：单路径 fetch 走 mujoco_menagerie，mock _download_bytes 返回数据。"""
        adapter = MuJoCoAdapter()
        fake_xml = b"<mujoco><worldbody/></mujoco>"
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_xml
        ) as mock_dl:
            raw = await adapter.fetch("aloha")
        assert raw.source == DataSource.MUJOCO
        assert raw.format == "xml"
        assert raw.data == fake_xml
        assert raw.size_bytes == len(fake_xml)
        assert "aloha/aloha.xml" in raw.url
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_unknown_scene_raises(self) -> None:
        """C10 修复后：未知 scene（无路径映射）直接抛 AdapterError。"""
        adapter = MuJoCoAdapter()
        with pytest.raises(AdapterError) as exc_info:
            await adapter.fetch("ant")
        assert "Unknown mujoco scene" in exc_info.value.message
