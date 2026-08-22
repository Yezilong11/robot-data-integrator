# tests/unit/adapters/test_github.py
"""GitHubAdapter 的单元测试。"""

import base64
import json
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.github import GitHubAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试污染仓库 data/cache/。"""
    monkeypatch.setattr(GitHubAdapter, "cache_root", lambda self: tmp_path)


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
                return_value=({"meshes/base.stl": b"stl-bytes"}, []),
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
            raw = await adapter.fetch("Kinovarobotics/ros_kortex", req_type=DataReqType.ROBOT_URDF)
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


class TestGitHubDataChain:
    """数据类需求的「contents 树 → 定位 → HEAD 预检 → 下载/引用」链路单测（mock 网络）。"""

    @staticmethod
    def _contents_entry(
        name: str,
        path: str,
        size: int,
        *,
        type_: str = "file",
        download_url: str | None = None,
    ) -> dict[str, Any]:
        """构造一条 GitHub contents API 条目。"""
        entry: dict[str, Any] = {"type": type_, "name": name, "path": path, "size": size}
        if download_url:
            entry["download_url"] = download_url
        return entry

    @pytest.mark.asyncio
    async def test_data_fetch_downloads_selected_file_within_limit(self, tmp_path) -> None:
        """候选 ≤ max_fetch_bytes：真实下载落盘，downloaded=True，reference=None。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        dl_url = (
            "https://raw.githubusercontent.com/acme/robot_control/main/"
            "checkpoints/policy.pt"
        )
        contents = [
            self._contents_entry("README.md", "README.md", 100),
            self._contents_entry(
                "policy.pt", "checkpoints/policy.pt", 512, download_url=dl_url
            ),
        ]
        fake_bytes = b"\x00\x00FakePolicy"
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=contents),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=512
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ),
        ):
            raw = await adapter.fetch("acme/robot_control", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "pt"
        assert raw.data == fake_bytes
        assert raw.reference is None
        assert raw.metadata["downloaded"] is True
        assert raw.url == dl_url
        # 权重已落盘缓存（cache_id 斜杠清洗为下划线）
        cache_file = tmp_path / "acme_robot_control_checkpoints_policy.pt"
        assert cache_file.is_file()
        assert cache_file.read_bytes() == fake_bytes

    @pytest.mark.asyncio
    async def test_data_fetch_returns_reference_over_limit(self) -> None:
        """候选超 max_fetch_bytes：RawReference（download_url + wget），data 注明未下载。"""
        from rdi.models.common import DataReqType

        big = settings.max_fetch_bytes + 1
        adapter = GitHubAdapter()
        dl_url = (
            "https://raw.githubusercontent.com/acme/robot_control/main/"
            "data/train_data.csv"
        )
        contents = [
            self._contents_entry("README.md", "README.md", 100),
            self._contents_entry(
                "train_data.csv", "data/train_data.csv", big, download_url=dl_url
            ),
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=contents),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=big
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
        ):
            raw = await adapter.fetch("acme/robot_control", req_type=DataReqType.SENSOR_DATA)
        assert raw.reference is not None
        assert raw.reference.url == dl_url
        assert raw.reference.file_size == big
        assert raw.reference.reason == "超过 max_fetch_bytes 自动下载上限"
        assert raw.reference.download_hint.startswith("wget ")
        assert raw.metadata["downloaded"] is False
        payload = json.loads(raw.data)
        assert payload["downloaded"] is False
        assert payload["file_path"] == "data/train_data.csv"
        assert payload["file_size"] == big
        assert payload["download_guide"]["method_hint"].startswith("wget ")
        assert payload["download_guide"]["source_file_url"] == dl_url
        # 体积超限：不下载候选文件
        assert not mock_dl.await_args_list

    @pytest.mark.asyncio
    async def test_data_fetch_no_candidate_falls_back_to_readme(self) -> None:
        """树无目标候选（仅元数据文件）：回退 README markdown（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        contents = [self._contents_entry("README.md", "README.md", 100)]
        readme_response = {
            "content": base64.b64encode(b"# repo readme").decode(),
            "html_url": "https://github.com/acme/robot_control",
        }

        async def _fake_request(method: str, path: str, **kwargs: Any) -> Any:
            if "contents" in path:
                return contents
            return readme_response

        with patch.object(adapter, "_request", side_effect=_fake_request):
            raw = await adapter.fetch("acme/robot_control", req_type=DataReqType.DATASET)
        assert raw.format == "markdown"
        assert raw.data == b"# repo readme"

    @pytest.mark.asyncio
    async def test_data_fetch_tree_api_failure_falls_back_to_readme(self) -> None:
        """contents 树 API 失败：回退 README（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        readme_response = {
            "content": base64.b64encode(b"# ok").decode(),
            "html_url": "https://github.com/acme/robot_control",
        }

        async def _fake_request(method: str, path: str, **kwargs: Any) -> Any:
            if "contents" in path:
                raise AdapterError(message="403 rate limited", source="github", status_code=403)
            return readme_response

        with patch.object(adapter, "_request", side_effect=_fake_request):
            raw = await adapter.fetch("acme/robot_control", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "markdown"

    @pytest.mark.asyncio
    async def test_data_fetch_recurses_subdirs(self) -> None:
        """contents API 递归进入子目录；候选取子目录内命中信号的权重文件。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        dl_url = (
            "https://raw.githubusercontent.com/acme/robot_control/main/"
            "checkpoints/actuator_model.bin"
        )

        async def _fake_request(method: str, path: str, **kwargs: Any) -> Any:
            if path == "/repos/acme/robot_control/contents":
                return [
                    self._contents_entry("checkpoints", "checkpoints", 0, type_="dir"),
                    self._contents_entry("README.md", "README.md", 100),
                ]
            if path == "/repos/acme/robot_control/contents/checkpoints":
                return [
                    self._contents_entry(
                        "actuator_model.bin",
                        "checkpoints/actuator_model.bin",
                        2048,
                        download_url=dl_url,
                    ),
                ]
            raise AssertionError(f"unexpected path: {path}")

        fake_bytes = b"bin-bytes"
        with (
            patch.object(adapter, "_request", side_effect=_fake_request),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=2048
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ),
        ):
            raw = await adapter.fetch("acme/robot_control", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "bin"
        assert raw.data == fake_bytes
        assert raw.url == dl_url
        assert raw.metadata["downloaded"] is True

    @pytest.mark.asyncio
    async def test_data_fetch_downloads_when_head_unknown(self) -> None:
        """HEAD 预检失败（None）：视为大小未知，真实下载（不误判超限）。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        contents = [
            self._contents_entry(
                "grasp_label_test.npz", "grasp/grasp_label_test.npz", 300,
                download_url="https://raw.githubusercontent.com/acme/grasp/main/grasp/grasp_label_test.npz",
            ),
        ]
        fake_bytes = b"npz-bytes"
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=contents),
            patch.object(adapter, "_head_content_length", new_callable=AsyncMock, return_value=None),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ),
        ):
            raw = await adapter.fetch("acme/grasp", req_type=DataReqType.GRASP)
        assert raw.format == "npz"
        assert raw.data == fake_bytes
        assert raw.reference is None
        assert raw.metadata["downloaded"] is True

    @pytest.mark.asyncio
    async def test_code_type_keeps_readme(self) -> None:
        """CODE 需求仍返回 README（不进入文件树下载链路，防回归）。"""
        from rdi.models.common import DataReqType

        adapter = GitHubAdapter()
        readme_response = {
            "content": base64.b64encode(b"# code readme").decode(),
            "html_url": "https://github.com/acme/foo",
        }
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=readme_response),
            patch.object(adapter, "_list_contents_tree", new_callable=AsyncMock) as mock_tree,
        ):
            raw = await adapter.fetch("acme/foo", req_type=DataReqType.CODE)
        assert raw.format == "markdown"
        mock_tree.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_default_req_type_keeps_readme(self) -> None:
        """无 req_type：保持 README 行为（防回归）。"""
        adapter = GitHubAdapter()
        readme_response = {
            "content": base64.b64encode(b"# readme").decode(),
            "html_url": "https://github.com/acme/foo",
        }
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=readme_response),
            patch.object(adapter, "_list_contents_tree", new_callable=AsyncMock) as mock_tree,
        ):
            raw = await adapter.fetch("acme/foo")
        assert raw.format == "markdown"
        mock_tree.assert_not_awaited()
