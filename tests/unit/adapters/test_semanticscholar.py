# tests/unit/adapters/test_semanticscholar.py
"""SemanticScholarAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.semanticscholar import SemanticScholarAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestSemanticScholarAdapter:
    """SemanticScholarAdapter 单元测试。"""

    def test_source_is_semantic_scholar(self) -> None:
        """正常情况：source 属性为 SEMANTIC_SCHOLAR。"""
        adapter = SemanticScholarAdapter()
        assert adapter.source == DataSource.SEMANTIC_SCHOLAR

    def test_base_url_from_settings(self) -> None:
        """正常情况：base_url 来自 settings。"""
        adapter = SemanticScholarAdapter()
        assert "semanticscholar.org" in adapter.base_url

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """正常情况：search 返回解析后的 SearchResult 列表。"""
        adapter = SemanticScholarAdapter()
        mock_data = {
            "data": [
                {
                    "paperId": "abc123",
                    "title": "Robot Grasping Survey",
                    "url": "https://www.semanticscholar.org/paper/abc123",
                    "abstract": "A survey of robot grasping.",
                    "year": 2023,
                    "citationCount": 42,
                    "authors": [{"name": "Alice"}, {"name": "Bob"}],
                },
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_data):
            results = await adapter.search("robot grasping")
        assert len(results) == 1
        assert results[0].item_id == "abc123"
        assert results[0].title == "Robot Grasping Survey"
        assert results[0].source == DataSource.SEMANTIC_SCHOLAR
        assert results[0].metadata["citation_count"] == 42
        assert results[0].metadata["authors"] == ["Alice", "Bob"]

    @pytest.mark.asyncio
    async def test_search_empty_data_returns_empty_list(self) -> None:
        """边界情况：API 返回空 data 列表时返回空列表。"""
        adapter = SemanticScholarAdapter()
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value={"data": []}):
            results = await adapter.search("nonexistent topic")
        assert results == []

    @pytest.mark.asyncio
    async def test_search_skips_entries_without_id_or_title(self) -> None:
        """边界情况：跳过缺少 paperId 或 title 的条目。"""
        adapter = SemanticScholarAdapter()
        mock_data = {
            "data": [
                {"paperId": "", "title": "Has Title But No ID"},
                {"paperId": "xyz789", "title": ""},
                {"paperId": "valid123", "title": "Valid Paper"},
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_data):
            results = await adapter.search("test")
        assert len(results) == 1
        assert results[0].item_id == "valid123"

    @pytest.mark.asyncio
    async def test_fetch_returns_raw_data(self) -> None:
        """正常情况：fetch 返回 RawData。"""
        adapter = SemanticScholarAdapter()
        mock_paper_data = {
            "paperId": "abc123",
            "title": "Robot Grasping Survey",
            "url": "https://www.semanticscholar.org/paper/abc123",
            "abstract": "A survey.",
            "year": 2023,
            "citationCount": 42,
            "authors": [],
            "references": [],
        }
        with patch.object(
            adapter, "_request", new_callable=AsyncMock, return_value=mock_paper_data
        ):
            raw = await adapter.fetch("abc123")
        assert raw.item_id == "abc123"
        assert raw.source == DataSource.SEMANTIC_SCHOLAR
        assert raw.format == "json"
        assert len(raw.data) > 0

    @pytest.mark.asyncio
    async def test_fetch_failure_raises_adapter_error(self) -> None:
        """异常情况：fetch 失败抛 AdapterError。"""
        adapter = SemanticScholarAdapter()
        with (
            patch.object(
                adapter,
                "_request",
                new_callable=AsyncMock,
                side_effect=AdapterError("fail", source="semantic_scholar"),
            ),
            pytest.raises(AdapterError),
        ):
            await adapter.fetch("nonexistent")
