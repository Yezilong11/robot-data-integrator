# tests/unit/adapters/test_paperswithcode.py
"""PapersWithCodeAdapter 的单元测试。"""

from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from rdi.adapters.paperswithcode import PapersWithCodeAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestPapersWithCodeAdapter:
    """PapersWithCodeAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.source == DataSource.PAPERSWITHCODE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.base_url == "https://paperswithcode.com/api/v1"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 5。"""
        adapter = PapersWithCodeAdapter()
        assert adapter.semaphore._value == 5

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：两条路径都失败时抛出 AdapterError（集成测试）。"""
        adapter = PapersWithCodeAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "paperswithcode"

    @pytest.mark.asyncio
    async def test_search_primary_success(self) -> None:
        """路径 A 成功：_scrape_html 返回构造的论文页面，验证 CSS 选择器解析。

        mock _scrape_html 返回带 paper-card 结构的 BeautifulSoup，验证
        _search_primary 正确解析 paper_id、title、code_url，且不调用路径 B。
        """
        adapter = PapersWithCodeAdapter()
        html = """
        <html><body>
          <div class="paper-card">
            <h2><a href="/paper/graspnet-1billion">GraspNet-1Billion</a></h2>
            <a href="https://github.com/example/graspnet">code</a>
          </div>
          <div class="paper-card">
            <h2><a href="/paper/other-paper">Other Paper</a></h2>
          </div>
        </body></html>
        """
        soup = BeautifulSoup(html, "lxml")
        with (
            patch.object(adapter, "_scrape_html", new_callable=AsyncMock, return_value=soup),
            patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request,
        ):
            results = await adapter.search("graspnet")
        # 路径 A 解析出全部 2 个 paper-card 条目（_search_primary 不按 query 过滤）
        assert len(results) == 2
        assert results[0].item_id == "graspnet-1billion"
        assert results[0].title == "GraspNet-1Billion"
        assert results[0].metadata["code_url"] == "https://github.com/example/graspnet"
        assert results[0].url == f"{adapter._web_url}/paper/graspnet-1billion"
        # 第二个条目无 github 链接，code_url 应为空字符串
        assert results[1].item_id == "other-paper"
        assert results[1].metadata["code_url"] == ""
        # 路径 A 成功，路径 B（_request）不应被调用
        mock_request.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_search_fallback_returns_results(self) -> None:
        """路径 A 失败时降级到路径 B（REST API），返回论文列表。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，
        mock _request 返回 REST API 响应，验证降级到 fallback。
        """
        adapter = PapersWithCodeAdapter()
        mock_response = {
            "results": [
                {
                    "paper": {
                        "id": "graspnet",
                        "title": "GraspNet",
                        "url": "https://paperswithcode.com/paper/graspnet",
                        "repository": {
                            "url": "https://github.com/test",
                            "framework": "pytorch",
                        },
                    }
                }
            ]
        }
        with (
            patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape,
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.PAPERSWITHCODE.value
            )
            results = await adapter.search("graspnet")
        assert len(results) > 0
        assert results[0].source == DataSource.PAPERSWITHCODE
        assert results[0].item_id == "graspnet"
        assert results[0].title == "GraspNet"
        assert results[0].metadata["code_url"] == "https://github.com/test"
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_search_fallback_no_match_returns_empty(self) -> None:
        """路径 B REST API 返回空 results 时返回空列表。"""
        adapter = PapersWithCodeAdapter()
        mock_response = {"results": []}
        with (
            patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape,
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response),
        ):
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.PAPERSWITHCODE.value
            )
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_fallback_returns_rawdata(self) -> None:
        """路径 A 失败时降级到路径 B（REST API），返回 RawData。

        mock _scrape_html 抛 AdapterError 模拟路径 A 失败，
        mock _request 返回 paper 和 implementations 数据。
        """
        adapter = PapersWithCodeAdapter()
        paper_data = {"id": "graspnet", "title": "GraspNet"}
        implementations_data = {"results": []}
        with (
            patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape,
            patch.object(
                adapter,
                "_request",
                new_callable=AsyncMock,
                side_effect=[paper_data, implementations_data],
            ),
        ):
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.PAPERSWITHCODE.value
            )
            raw = await adapter.fetch("graspnet")
        assert raw.source == DataSource.PAPERSWITHCODE
        assert raw.item_id == "graspnet"
        assert raw.format == "json"
        assert raw.size_bytes > 0
        mock_scrape.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_fetch_both_paths_fail_raises(self) -> None:
        """路径 A 和路径 B 都失败时抛 AdapterError。

        mock _scrape_html 抛 AdapterError（路径 A 失败），
        mock _request 抛 AdapterError（路径 B 也失败）。
        """
        adapter = PapersWithCodeAdapter()
        with (
            patch.object(adapter, "_scrape_html", new_callable=AsyncMock) as mock_scrape,
            patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request,
        ):
            mock_scrape.side_effect = AdapterError(
                message="primary failed", source=DataSource.PAPERSWITHCODE.value
            )
            mock_request.side_effect = AdapterError(
                message="fallback failed", source=DataSource.PAPERSWITHCODE.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("graspnet")
        # 路径 A（_scrape_html）+ 路径 B（_request 第一次）各一次尝试
        mock_scrape.assert_awaited_once()
        mock_request.assert_awaited_once()
