# tests/unit/adapters/test_github.py
"""GitHubAdapter 的单元测试。"""

import base64
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.github import GitHubAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


class TestGitHubAdapter:
    """GitHubAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = GitHubAdapter()
        assert adapter.source == DataSource.GITHUB

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = GitHubAdapter()
        assert adapter.base_url == "https://api.github.com"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 30。"""
        adapter = GitHubAdapter()
        assert adapter.semaphore._value == 30

    def test_headers_without_token(self) -> None:
        """正常情况：无 token 时只有 Accept 头。"""
        adapter = GitHubAdapter()
        adapter.token = ""
        assert "Authorization" not in adapter.headers
        assert adapter.headers["Accept"] == "application/vnd.github.v3+json"

    def test_headers_with_token(self) -> None:
        """正常情况：有 token 时包含 Authorization 头。"""
        adapter = GitHubAdapter()
        adapter.token = "ghp-test-token"
        assert adapter.headers["Authorization"] == "token ghp-test-token"

    def test_headers_format(self) -> None:
        """正常情况：Authorization 格式为 'token <value>'。"""
        adapter = GitHubAdapter()
        adapter.token = "ghp-abc123"
        assert adapter.headers["Authorization"].startswith("token ")

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = GitHubAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("test")
        assert exc_info.value.source == "github"

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_fetch_retries_on_failure(self) -> None:
        """异常情况：fetch 失败时抛出 AdapterError。"""
        adapter = GitHubAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.fetch("nonexistent/repo")
        assert exc_info.value.source == "github"

    @pytest.mark.asyncio
    async def test_github_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回仓库结果。"""
        adapter = GitHubAdapter()
        mock_response = {
            "items": [
                {
                    "full_name": "NVlabs/6-DOF-GraspNet",
                    "name": "6-DOF-GraspNet",
                    "html_url": "https://github.com/NVlabs/6-DOF-GraspNet",
                    "stargazers_count": 500,
                    "description": "6-DOF GraspNet",
                    "language": "Python",
                    "topics": ["grasping"],
                }
            ]
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("6-DOF grasp")
            assert len(results) > 0
            assert results[0].source == DataSource.GITHUB
            assert results[0].item_id == "NVlabs/6-DOF-GraspNet"
            assert results[0].metadata["stars"] == 500

    @pytest.mark.asyncio
    async def test_github_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = GitHubAdapter()
        mock_response = {
            "content": base64.b64encode(b"# Test README").decode(),
            "html_url": "https://github.com/test",
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            raw = await adapter.fetch("test/repo")
            assert raw.source == DataSource.GITHUB
            assert raw.item_id == "test/repo"
            assert raw.format == "markdown"
            assert raw.data == b"# Test README"
            assert raw.size_bytes > 0
