# tests/unit/adapters/test_paperswithcode.py
"""PapersWithCodeAdapter 的单元测试。"""

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

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
        """异常情况：_request 失败时抛出 AdapterError（集成测试）。"""
        adapter = PapersWithCodeAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "paperswithcode"

    @pytest.mark.asyncio
    async def test_search_returns_results(self) -> None:
        """C12 修复后：search 直接走 REST API（无网页抓取主源）。

        mock _request 返回 REST API 响应，验证解析 paper_id、title、code_url。
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
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("graspnet")
        assert len(results) > 0
        assert results[0].source == DataSource.PAPERSWITHCODE
        assert results[0].item_id == "graspnet"
        assert results[0].title == "GraspNet"
        assert results[0].metadata["code_url"] == "https://github.com/test"

    @pytest.mark.asyncio
    async def test_search_no_match_returns_empty(self) -> None:
        """REST API 返回空 results 时返回空列表。"""
        adapter = PapersWithCodeAdapter()
        mock_response = {"results": []}
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("zzznomatchxyz")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_returns_rawdata(self) -> None:
        """C12 修复后：fetch 直接走 REST API（无网页抓取主源）。

        mock _request 返回 paper 和 implementations 数据。
        """
        adapter = PapersWithCodeAdapter()
        paper_data = {"id": "graspnet", "title": "GraspNet"}
        implementations_data = {"results": []}
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=[paper_data, implementations_data],
        ):
            raw = await adapter.fetch("graspnet")
        assert raw.source == DataSource.PAPERSWITHCODE
        assert raw.item_id == "graspnet"
        assert raw.format == "json"
        assert raw.size_bytes > 0

    @pytest.mark.asyncio
    async def test_fetch_fail_raises(self) -> None:
        """C12 修复后：_request 失败时抛 AdapterError。

        E5 修复后：禁用 OpenAlex fallback（_openalex_base_url=""），
        只测 PwC 主源失败路径，保持 _request 只被调用一次。
        """
        adapter = PapersWithCodeAdapter()
        adapter._openalex_base_url = ""  # 禁用 fallback，隔离 PwC 主源测试
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_request:
            mock_request.side_effect = AdapterError(
                message="request failed", source=DataSource.PAPERSWITHCODE.value
            )
            with pytest.raises(AdapterError):
                await adapter.fetch("graspnet")
        mock_request.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_pwc_request_converts_timeout_to_adapter_error(self) -> None:
        """C12+E5 修复：_request 超时时 _pwc_request 转 AdapterError（快速失败）。

        mock _request 为永不返回的协程 + 缩短 _PWC_REQUEST_TIMEOUT_S 到 0.1s，
        验证 10s 独立超时生效，避免 search hang 满 25s 探活外部超时。
        """
        adapter = PapersWithCodeAdapter()

        async def hang_forever(*args: object, **kwargs: object) -> object:
            await asyncio.sleep(100)

        with (
            patch.object(
                adapter, "_request", new_callable=AsyncMock, side_effect=hang_forever
            ),
            patch(
                "rdi.adapters.paperswithcode._PWC_REQUEST_TIMEOUT_S",
                0.1,
            ),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter._pwc_request("GET", "/search/", params={"q": "x"})
        assert "timed out" in exc_info.value.message
        assert exc_info.value.source == "paperswithcode"

    @pytest.mark.asyncio
    async def test_pwc_request_passes_through_adapter_error(self) -> None:
        """C12+E5：非超时的 AdapterError（如 4xx）透传，不被 _pwc_request 吞掉。"""
        adapter = PapersWithCodeAdapter()
        original_err = AdapterError(
            message="not found", source=DataSource.PAPERSWITHCODE.value, status_code=404
        )
        with patch.object(
            adapter, "_request", new_callable=AsyncMock, side_effect=original_err
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter._pwc_request("GET", "/papers/abc")
        # 透传的是原异常，不是超时转换的
        assert exc_info.value is original_err
        assert "not found" in exc_info.value.message


class TestPapersWithCodeOpenAlexFallback:
    """E5 修复：PwC 主源失败时 fallback 到 OpenAlex 的单测。"""

    def test_extract_openalex_work_id_from_full_url(self) -> None:
        """从完整 ID URL 提取 work ID。"""
        assert (
            PapersWithCodeAdapter._extract_openalex_work_id(
                "https://openalex.org/W1820657498"
            )
            == "W1820657498"
        )

    def test_extract_openalex_work_id_empty(self) -> None:
        """空字符串返回空。"""
        assert PapersWithCodeAdapter._extract_openalex_work_id("") == ""

    def test_parse_openalex_search_results(self) -> None:
        """解析 OpenAlex search 返回，验证 item_id/code_url/source 标记。"""
        data = {
            "results": [
                {
                    "id": "https://openalex.org/W1820657498",
                    "title": "Robotic grasping and contact: a review",
                    "doi": "https://doi.org/10.1109/robot.2000.844081",
                    "cited_by_count": 1070,
                    "publication_year": 2002,
                }
            ]
        }
        results = PapersWithCodeAdapter._parse_openalex_search_results(data)
        assert len(results) == 1
        r = results[0]
        assert r.item_id == "W1820657498"
        assert r.title == "Robotic grasping and contact: a review"
        assert r.source == DataSource.PAPERSWITHCODE
        assert r.metadata["code_url"] == ""  # OpenAlex 不提供 code 关联
        assert r.metadata["source"] == "openalex"
        assert r.metadata["doi"] == "https://doi.org/10.1109/robot.2000.844081"

    @pytest.mark.asyncio
    async def test_search_fallback_to_openalex_on_pwc_failure(self) -> None:
        """E5：PwC search 失败时自动 fallback 到 OpenAlex。"""
        adapter = PapersWithCodeAdapter()
        pwc_err = AdapterError(
            message="PwC timed out (Cloudflare)",
            source=DataSource.PAPERSWITHCODE.value,
        )
        openalex_data = {
            "results": [
                {
                    "id": "https://openalex.org/W2041376653",
                    "title": "Robotic Grasping of Novel Objects using Vision",
                    "doi": "https://doi.org/10.1177/0278364907087172",
                    "cited_by_count": 951,
                    "publication_year": 2008,
                }
            ]
        }
        with (
            patch.object(
                adapter, "_pwc_request", new_callable=AsyncMock, side_effect=pwc_err
            ),
            patch.object(
                adapter,
                "_openalex_request",
                new_callable=AsyncMock,
                return_value=openalex_data,
            ),
        ):
            results = await adapter.search("robot grasping")
        assert len(results) == 1
        assert results[0].item_id == "W2041376653"
        assert results[0].metadata["source"] == "openalex"

    @pytest.mark.asyncio
    async def test_search_both_fail_raises_pwc_error(self) -> None:
        """E5：PwC 和 OpenAlex 双路径均失败时抛 PwC 原异常（符合项目约束）。"""
        adapter = PapersWithCodeAdapter()
        pwc_err = AdapterError(
            message="PwC timed out (Cloudflare)",
            source=DataSource.PAPERSWITHCODE.value,
        )
        openalex_err = AdapterError(
            message="OpenAlex also failed",
            source=DataSource.PAPERSWITHCODE.value,
        )
        with (
            patch.object(
                adapter, "_pwc_request", new_callable=AsyncMock, side_effect=pwc_err
            ),
            patch.object(
                adapter, "_openalex_request", new_callable=AsyncMock, side_effect=openalex_err
            ),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("robot grasping")
        # 抛的是 PwC 原异常，不是 OpenAlex 的
        assert exc_info.value is pwc_err

    @pytest.mark.asyncio
    async def test_fetch_fallback_to_openalex_on_pwc_failure(self) -> None:
        """E5：PwC fetch 失败时自动 fallback 到 OpenAlex（无 code 关联）。"""
        adapter = PapersWithCodeAdapter()
        pwc_err = AdapterError(
            message="PwC timed out (Cloudflare)",
            source=DataSource.PAPERSWITHCODE.value,
        )
        openalex_data = {
            "id": "https://openalex.org/W1820657498",
            "title": "Robotic grasping and contact: a review",
            "doi": "https://doi.org/10.1109/robot.2000.844081",
            "cited_by_count": 1070,
            "publication_year": 2002,
            "type": "article",
            "open_access": {"oa_url": None},
        }
        with (
            patch.object(
                adapter, "_pwc_request", new_callable=AsyncMock, side_effect=pwc_err
            ),
            patch.object(
                adapter,
                "_openalex_request",
                new_callable=AsyncMock,
                return_value=openalex_data,
            ),
        ):
            raw = await adapter.fetch("W1820657498")
        assert raw.source == DataSource.PAPERSWITHCODE
        assert raw.item_id == "W1820657498"
        assert raw.format == "json"
        assert raw.size_bytes > 0
        # 验证 fallback 数据结构
        import json as _json

        body = _json.loads(raw.data.decode("utf-8"))
        assert body["paper"]["title"] == "Robotic grasping and contact: a review"
        assert body["implementations"] == []  # OpenAlex 无 code 关联
        assert body["metadata"]["source"] == "openalex"

    @pytest.mark.asyncio
    async def test_search_no_fallback_when_openalex_disabled(self) -> None:
        """E5：openalex_base_url 为空时不禁用 fallback，直接抛 PwC 异常。"""
        adapter = PapersWithCodeAdapter()
        adapter._openalex_base_url = ""  # 禁用 fallback
        pwc_err = AdapterError(
            message="PwC timed out (Cloudflare)",
            source=DataSource.PAPERSWITHCODE.value,
        )
        with patch.object(
            adapter, "_pwc_request", new_callable=AsyncMock, side_effect=pwc_err
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("robot grasping")
        assert exc_info.value is pwc_err
