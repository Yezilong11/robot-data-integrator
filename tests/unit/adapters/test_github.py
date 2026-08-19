# tests/unit/adapters/test_github.py
"""GitHubAdapter 的单元测试。"""

import base64
from typing import Any
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

    @pytest.mark.asyncio
    async def test_github_fetch_robot_urdf_downloads_urdf(self) -> None:
        """ROBOT_URDF 需求：从仓库文件树中定位并下载 .urdf，而非 README。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        tree_response = {
            "tree": [
                {"path": "robots/franka_panda.urdf", "type": "blob"},
                {"path": "README.md", "type": "blob"},
            ]
        }
        fake_urdf = b'<robot name="franka"><link name="base"/></robot>'
        with (
            patch.object(
                adapter,
                "_request",
                new_callable=AsyncMock,
                return_value=tree_response,
            ),
            patch.object(
                adapter,
                "fetch_file",
                new_callable=AsyncMock,
                return_value=fake_urdf,
            ),
        ):
            raw = await adapter.fetch("franka/franka_ros", req_type=DataReqType.ROBOT_URDF)
            assert raw.format == "urdf"
            assert raw.data == fake_urdf
            assert "robots/franka_panda.urdf" in raw.url
            assert raw.assets == {}  # 无 mesh 引用的简单 URDF 不产生资产

    @pytest.mark.asyncio
    async def test_github_fetch_robot_urdf_collects_assets_and_strips_package(self) -> None:
        """D4 修复：URDF 命中后随包抓取 package:// 引用的网格资产并剥离前缀。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        tree_response = {
            "tree": [
                {"path": "robots/panda.urdf", "type": "blob"},
                {"path": "README.md", "type": "blob"},
            ]
        }
        fake_urdf = (
            b'<robot name="panda"><link name="base"><visual><geometry>'
            b'<mesh filename="package://meshes/base.stl"/></geometry></visual></link></robot>'
        )
        raw_url = "https://raw.githubusercontent.com/deoxys/deoxys_control/main/robots/panda.urdf"
        with (
            patch.object(
                adapter,
                "_request",
                new_callable=AsyncMock,
                return_value=tree_response,
            ),
            patch.object(
                adapter,
                "fetch_file",
                new_callable=AsyncMock,
                return_value=fake_urdf,
            ),
            patch.object(
                adapter,
                "_download_xml_with_assets",
                new_callable=AsyncMock,
                return_value={"meshes/base.stl": b"stl-bytes"},
            ) as mock_assets,
        ):
            raw = await adapter.fetch("deoxys/deoxys_control", req_type=DataReqType.ROBOT_URDF)
            assert raw.format == "urdf"
            assert raw.assets == {"meshes/base.stl": b"stl-bytes"}
            # 资产下载以 raw.githubusercontent.com 的 raw_url 为基准
            mock_assets.assert_awaited_once()
            assert raw_url == mock_assets.await_args.args[0]
            # package:// 前缀已剥离，引用与资产键一致（离线可加载）
            assert b"package://" not in raw.data
            assert b'filename="meshes/base.stl"' in raw.data

    @pytest.mark.asyncio
    async def test_github_fetch_robot_urdf_branch_fallback_to_default(self) -> None:
        """D4 修复：main/master 分支不存在时回退到仓库 default_branch 查找 URDF。"""
        from rdi.exceptions import AdapterError
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()

        async def _fake_request(method: str, path: str, **kwargs: Any) -> Any:
            if path.startswith("/repos/Kinovarobotics/ros_kortex/git/trees/main"):
                raise AdapterError(message="404 main", source="github", status_code=404)
            if path.startswith("/repos/Kinovarobotics/ros_kortex/git/trees/master"):
                raise AdapterError(message="404 master", source="github", status_code=404)
            if path == "/repos/Kinovarobotics/ros_kortex":
                return {"default_branch": "noetic-devel"}
            if path.startswith("/repos/Kinovarobotics/ros_kortex/git/trees/noetic-devel"):
                return {
                    "tree": [
                        {"path": "kortex_description/robots/gen3.urdf", "type": "blob"},
                    ]
                }
            raise AssertionError(f"unexpected request: {path}")

        fake_urdf = b'<robot name="gen3"><link name="base"/></robot>'
        with (
            patch.object(adapter, "_request", side_effect=_fake_request),
            patch.object(
                adapter,
                "fetch_file",
                new_callable=AsyncMock,
                return_value=fake_urdf,
            ) as mock_fetch_file,
        ):
            raw = await adapter.fetch(
                "Kinovarobotics/ros_kortex", req_type=DataReqType.ROBOT_URDF
            )
            assert raw.format == "urdf"
            # fetch_file 以探测到的 default_branch 下载（此前固定 main 会 404 回退 README）
            assert mock_fetch_file.await_args.args == (
                "Kinovarobotics/ros_kortex",
                "kortex_description/robots/gen3.urdf",
            )
            assert mock_fetch_file.await_args.kwargs == {"ref": "noetic-devel"}
            assert "noetic-devel" in raw.url

    @pytest.mark.asyncio
    async def test_github_fetch_robot_urdf_falls_back_to_readme(self) -> None:
        """ROBOT_URDF 需求但仓库无 .urdf 文件 → 回退 README（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        tree_response = {"tree": [{"path": "README.md", "type": "blob"}]}
        readme_response = {
            "content": base64.b64encode(b"# README only").decode(),
            "html_url": "https://github.com/test",
        }

        def _fake_request(method: str, path: str, **kwargs: Any) -> Any:
            if "git/trees" in path:
                return tree_response
            return readme_response

        with patch.object(adapter, "_request", side_effect=_fake_request):
            raw = await adapter.fetch("test/repo", req_type=DataReqType.ROBOT_URDF)
            assert raw.format == "markdown"
