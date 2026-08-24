# tests/unit/adapters/test_zenodo.py
"""ZenodoAdapter 的单元测试。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.zenodo import ZenodoAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataReqType, DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试污染仓库 data/cache/。"""
    monkeypatch.setattr(ZenodoAdapter, "cache_root", lambda self: tmp_path)


class TestZenodoAdapter:
    """ZenodoAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = ZenodoAdapter()
        assert adapter.source == DataSource.ZENODO

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = ZenodoAdapter()
        assert adapter.base_url == "https://zenodo.org/api"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = ZenodoAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = ZenodoAdapter()
        adapter.max_retry = 1
        with patch.object(
            adapter,
            "_request",
            new_callable=AsyncMock,
            side_effect=AdapterError("fail", source="zenodo"),
        ):
            with pytest.raises(AdapterError) as exc_info:
                await adapter.search("robot grasp dataset")
            assert exc_info.value.source == "zenodo"

    @pytest.mark.asyncio
    async def test_zenodo_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回记录列表。"""
        adapter = ZenodoAdapter()
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "id": 12345,
                        "title": "Robot Grasp Dataset",
                        "doi": "10.1234/test",
                        "links": {"self_html": "https://zenodo.org/records/12345"},
                        "created": "2024-01-01",
                    }
                ]
            }
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("robot grasp dataset")
            assert len(results) > 0
            assert results[0].source == DataSource.ZENODO
            assert results[0].item_id == "12345"
            assert results[0].title == "Robot Grasp Dataset"

    @pytest.mark.asyncio
    async def test_zenodo_search_uses_bestmatch_sort(self) -> None:
        """2026-08-23 真实重放修复：搜索必须用 bestmatch（relevance）而非 mostrecent。

        mostrecent 对通用传感器查询返回无关记录（YOLO/选集/daily-build），
        导致 ss_zenodo_002/004/007 语义不符拦截；bestmatch 命中真实关节/力觉
        传感器记录（Zenodo API 实测验证）。
        """
        adapter = ZenodoAdapter()
        mock_response = {"hits": {"hits": []}}
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            await adapter.search("joint position sensor")
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["sort"] == "bestmatch"

    @pytest.mark.asyncio
    async def test_zenodo_search_appends_filetype_filter_by_req_type(self) -> None:
        """P1-A：按需求类型追加 filetype 过滤——sensor → csv 单格式；dataset → csv OR zip。

        bestmatch 对传感器查询首命中常为 PDF 论文记录（无 csv/json 候选 →
        占位）；filetype 过滤把真实数据文件记录浮出（Zenodo API 实测有效）。
        """
        adapter = ZenodoAdapter()
        mock_response = {"hits": {"hits": []}}
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            await adapter.search(
                "joint position sensor", req_type=DataReqType.SENSOR_DATA
            )
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["q"] == 'joint position sensor AND filetype:"csv"'
        assert kwargs["params"]["sort"] == "bestmatch"

        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req2:
            mock_req2.return_value = mock_response
            await adapter.search("grasp dataset", req_type="dataset")
        _, kwargs2 = mock_req2.call_args
        assert kwargs2["params"]["q"] == 'grasp dataset AND (filetype:"csv" OR filetype:"zip")'

    @pytest.mark.asyncio
    async def test_zenodo_search_no_filter_without_req_type(self) -> None:
        """未传 req_type（如旧调用方）：不加 filetype 过滤，query 原样透传。"""
        adapter = ZenodoAdapter()
        mock_response = {"hits": {"hits": []}}
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            await adapter.search("robot grasp dataset")
        _, kwargs = mock_req.call_args
        assert kwargs["params"]["q"] == "robot grasp dataset"

    @pytest.mark.asyncio
    async def test_zenodo_search_metadata_description_contains_title_and_keywords(self) -> None:
        """fix4：SearchResult.metadata.description 含标题+关键词+描述摘要，供检索期
        语义预筛在标题缺需求词但关键词含词时仍能打分选对候选（如 IMU 记录）。"""
        adapter = ZenodoAdapter()
        mock_response = {
            "hits": {
                "hits": [
                    {
                        "id": 16894241,
                        "title": "Inertial data of daily living tasks",
                        "links": {"self_html": "https://zenodo.org/records/16894241"},
                        "created": "2024-01-01",
                        "metadata": {
                            "title": "Inertial data of daily living tasks",
                            "keywords": ["vestibulopathy", "inertial sensor", "IMU"],
                            "description": "Steps and turns of patients",
                        },
                    }
                ]
            }
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock) as mock_req:
            mock_req.return_value = mock_response
            results = await adapter.search("imu sensor data", req_type=DataReqType.SENSOR_DATA)
        desc = results[0].metadata["description"]
        assert "IMU" in desc
        assert "inertial sensor" in desc
        assert results[0].title == "Inertial data of daily living tasks"

    @pytest.mark.asyncio
    async def test_zenodo_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = ZenodoAdapter()
        mock_response = {
            "id": 12345,
            "title": "Robot Grasp Dataset",
            "doi": "10.1234/test",
        }
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            raw = await adapter.fetch("12345")
            assert raw.source == DataSource.ZENODO
            assert raw.item_id == "12345"
            assert raw.format == "json"
            assert raw.size_bytes > 0


def _record_with_files(files: list[dict[str, object]]) -> dict[str, object]:
    """构造含 files 数组的 Zenodo record（元数据 + 文件项）。"""
    return {
        "id": 12345,
        "title": "Robot Grasp Dataset",
        "doi": "10.1234/test",
        "metadata": {"description": "grasp labels"},
        "files": files,
    }


class TestZenodoFetchFileChain:
    """Zenodo fetch 的 files[] → 定位 → 预检 → 下载/引用 链路测试。"""

    @pytest.mark.asyncio
    async def test_fetch_downloads_selected_file(self) -> None:
        """GRASP 类型：tree 定位 .npz → HEAD 未超限 → 下载落盘 RawData（downloaded=True）。"""
        adapter = ZenodoAdapter()
        record = _record_with_files(
            [
                {"key": "README.md", "size": 100, "checksum": "md5:aaa"},
                {
                    "key": "annotations/grasp_labels.npz",
                    "link": "https://zenodo.org/api/records/12345/files/"
                    "annotations/grasp_labels.npz?download=1",
                    "size": 2048,
                    "checksum": "md5:bbb",
                },
                {"key": "metadata/config.json", "size": 50, "checksum": "md5:ccc"},
            ]
        )
        fake_bytes = b"npz-content"
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=2048
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ) as mock_dl,
        ):
            raw = await adapter.fetch("12345", req_type=DataReqType.GRASP)
        assert raw.format == "npz"
        assert raw.data == fake_bytes
        # fix4/fix4b: metadata 透出来源标题与描述（供装配期语义校验）
        assert raw.metadata == {
            "downloaded": True,
            "title": "Robot Grasp Dataset",
            "description": "grasp labels",
        }
        assert raw.reference is None
        assert raw.url == (
            "https://zenodo.org/api/records/12345/files/annotations/grasp_labels.npz?download=1"
        )
        mock_dl.assert_awaited_once()
        # 二进制已通过 save_to_cache 落到隔离的 tmp 缓存目录
        assert adapter.is_cached("12345/annotations/grasp_labels.npz")

    @pytest.mark.asyncio
    async def test_fetch_reference_when_over_threshold(self) -> None:
        """HEAD 预检超 max_fetch_bytes → RawReference（link + wget），不调用下载。"""
        adapter = ZenodoAdapter()
        big = settings.max_fetch_bytes + 1
        record = _record_with_files(
            [
                {
                    "key": "data/policy_model.safetensors",
                    "link": "https://zenodo.org/api/records/12345/files/"
                    "data/policy_model.safetensors?download=1",
                    "size": big,
                    "checksum": "md5:ddd",
                }
            ]
        )
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=big
            ),
            patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl,
        ):
            raw = await adapter.fetch("12345", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "json"
        # fix4/fix4b: metadata 透出来源标题与描述（供装配期语义校验）
        assert raw.metadata == {
            "downloaded": False,
            "title": "Robot Grasp Dataset",
            "description": "grasp labels",
        }
        assert raw.reference is not None
        assert raw.reference.url == (
            "https://zenodo.org/api/records/12345/files/data/policy_model.safetensors?download=1"
        )
        assert raw.reference.file_size == big
        assert raw.reference.download_hint.startswith("wget ")
        assert "max_fetch_bytes" in raw.reference.reason
        payload = json.loads(raw.data)
        assert payload["downloaded"] is False
        assert payload["file_path"] == "data/policy_model.safetensors"
        assert payload["file_size"] == big
        assert payload["download_guide"]["status"] == "not_downloaded"
        mock_dl.assert_not_called()

    @pytest.mark.asyncio
    async def test_fetch_uses_fallback_url_when_link_missing(self) -> None:
        """files 项无 link → 兜底官方下载 URL（records/{id}/files/{key}?download=1）。"""
        adapter = ZenodoAdapter()
        record = _record_with_files(
            [{"key": "data/robot_urdf.urdf", "size": 1024, "checksum": "md5:eee"}]
        )
        fake_bytes = b"urdf-content"
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=1024
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ) as mock_dl,
        ):
            raw = await adapter.fetch("12345", req_type=DataReqType.ROBOT_URDF)
        expected = "https://zenodo.org/records/12345/files/data/robot_urdf.urdf?download=1"
        assert raw.url == expected
        assert raw.format == "urdf"
        # fix4/fix4b: metadata 透出来源标题与描述（供装配期语义校验）
        assert raw.metadata == {
            "downloaded": True,
            "title": "Robot Grasp Dataset",
            "description": "grasp labels",
        }
        mock_dl.assert_awaited_once_with(expected)

    @pytest.mark.asyncio
    async def test_fetch_accepts_string_req_type(self) -> None:
        """req_type 传小写字符串（retrieve_data 兼容形）同样定位并下载。"""
        adapter = ZenodoAdapter()
        record = _record_with_files(
            [
                {
                    "key": "data/sensor_readings.csv",
                    "link": "https://zenodo.org/api/records/12345/files/"
                    "data/sensor_readings.csv?download=1",
                    "size": 512,
                    "checksum": "md5:fff",
                }
            ]
        )
        fake_bytes = b"time,torque\n0,1.0\n"
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=512
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
            ),
        ):
            raw = await adapter.fetch("12345", req_type="sensor_data")
        assert raw.format == "csv"
        assert raw.data == fake_bytes
        # fix4: metadata 透出来源标题（供装配期语义校验）
        assert raw.metadata == {
            "downloaded": True,
            "title": "Robot Grasp Dataset",
            "description": "grasp labels",
        }

    @pytest.mark.asyncio
    async def test_fetch_metadata_when_no_files(self) -> None:
        """record 无 files：维持原行为返回 metadata JSON（不抛错）。"""
        adapter = ZenodoAdapter()
        record = {"id": 12345, "title": "Robot Grasp Dataset", "doi": "10.1234/test"}
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record):
            raw = await adapter.fetch("12345", req_type="grasp")
        assert raw.format == "json"
        assert raw.reference is None
        assert json.loads(raw.data)["id"] == 12345
        assert raw.url == "https://zenodo.org/records/12345"
        # P1-A：无文件候选显式标记 degraded，供 retrieve_data 判定本源失败
        assert raw.metadata.get("degraded") == "no_file_candidate"
        # fix4: 无候选时仍透出来源标题
        assert raw.metadata.get("title") == "Robot Grasp Dataset"

    @pytest.mark.asyncio
    async def test_fetch_metadata_when_no_candidate(self) -> None:
        """files 仅有被跳过的元数据类文件 → 无候选 → 返回 record metadata JSON。"""
        adapter = ZenodoAdapter()
        record = _record_with_files(
            [
                {"key": "README.md", "size": 100, "checksum": "md5:aaa"},
                {"key": "LICENSE.txt", "size": 200, "checksum": "md5:bbb"},
            ]
        )
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=record):
            raw = await adapter.fetch("12345", req_type="dataset")
        assert raw.format == "json"
        assert raw.reference is None
        assert json.loads(raw.data)["id"] == 12345
        # P1-A：README/LICENSE 非候选 → 同样标记 degraded（无数据文件可交付）
        assert raw.metadata.get("degraded") == "no_file_candidate"
        assert raw.metadata.get("title") == "Robot Grasp Dataset"
