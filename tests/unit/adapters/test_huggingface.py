# tests/unit/adapters/test_huggingface.py
"""HuggingFaceAdapter 的单元测试。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.huggingface import HuggingFaceAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource


@pytest.fixture(autouse=True)
def _isolate_file_cache(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    """把本地文件缓存根目录指向临时目录，避免测试污染仓库 data/cache/。"""
    monkeypatch.setattr(HuggingFaceAdapter, "cache_root", lambda self: tmp_path)


class TestHuggingFaceAdapter:
    """HuggingFaceAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.source == DataSource.HUGGINGFACE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 与配置一致（国内环境走 hf-mirror 镜像）。"""
        adapter = HuggingFaceAdapter()
        assert adapter.base_url == settings.huggingface_api_url

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 10。"""
        adapter = HuggingFaceAdapter()
        assert adapter.semaphore._value == 10

    @pytest.mark.asyncio
    @pytest.mark.integration
    async def test_search_retries_on_failure(self) -> None:
        """异常情况：请求失败时抛出 AdapterError。"""
        adapter = HuggingFaceAdapter()
        adapter.max_retry = 1
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "huggingface"

    @pytest.mark.asyncio
    async def test_huggingface_search_with_mock(self) -> None:
        """Mock 驱动：search 通过 _request 返回模型列表。"""
        adapter = HuggingFaceAdapter()
        mock_response = [
            {
                "id": "bert-base-uncased",
                "modelId": "bert-base-uncased",
                "downloads": 1000,
                "likes": 50,
                "tags": ["transformers"],
            }
        ]
        with patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_response):
            results = await adapter.search("bert")
            assert len(results) > 0
            assert results[0].source == DataSource.HUGGINGFACE
            assert results[0].item_id == "bert-base-uncased"
            assert results[0].metadata["downloads"] == 1000

    @pytest.mark.asyncio
    async def test_huggingface_fetch_with_mock(self) -> None:
        """Mock 驱动：fetch 返回 RawData 且字段正确。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert"}'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_config
        ):
            raw = await adapter.fetch("bert-base-uncased")
            assert raw.source == DataSource.HUGGINGFACE
            assert raw.item_id == "bert-base-uncased"
            assert raw.format == "json"
            assert raw.size_bytes > 0

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_uses_model_info(self) -> None:
        """POLICY_MODEL 类型：fetch 拉取 model_info.json 而非默认 config.json。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        fake_model_info = b'{"modelId": "lerobot/act_aloha", "tags": ["policy"]}'
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return fake_model_info

        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=[]),
            patch.object(adapter, "_download_bytes", side_effect=_fake_download),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert any("model_info.json" in u for u in called_urls)
            assert not any("config.json" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_huggingface_fetch_default_uses_config(self) -> None:
        """默认类型（非 POLICY_MODEL）：仍拉取 config.json（不回归）。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert"}'
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return fake_config

        with patch.object(adapter, "_download_bytes", side_effect=_fake_download):
            raw = await adapter.fetch("bert-base-uncased")
            assert raw.format == "json"
            assert any("config.json" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_invalid_json_fallback(self) -> None:
        """POLICY_MODEL：model_info.json 404 → 降级 config.json → metadata 引用（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        responses = {
            "model_info.json": b"<html>404</html>",
            "config.json": b'{"model_type": "act"}',
        }

        async def _fake_download(url: str) -> bytes:
            for name, body in responses.items():
                if name in url:
                    return body
            raise RuntimeError(f"unexpected url: {url}")

        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=[]),
            patch.object(adapter, "_download_bytes", side_effect=_fake_download),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert b"model_type" in raw.data or b"model_id" in raw.data

    @pytest.mark.asyncio
    async def test_huggingface_fetch_policy_model_all_fail_returns_meta(self) -> None:
        """POLICY_MODEL：model_info.json 与 config.json 均不可用 → 返回 metadata 引用（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=[]),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, side_effect=RuntimeError("boom")
            ),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            assert raw.format == "json"
            assert b"model_id" in raw.data


class TestHuggingFacePolicyModelChain:
    """POLICY_MODEL 的「树 → 定位 → 预检 → 下载/引用」链路单测（mock 网络）。"""

    @staticmethod
    def _fake_meta(_url: str) -> bytes:
        """meta 下载总是返回合法 model_info.json。"""
        return json.dumps(
            {"modelId": "lerobot/act_aloha", "tags": ["policy"]}, ensure_ascii=False
        ).encode("utf-8")

    @pytest.mark.asyncio
    async def test_downloads_weight_within_limit(self, tmp_path) -> None:
        """权重 ≤ max_fetch_bytes：真实下载落盘，downloaded=True，reference=None。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        fake_weight = b"\x00SAFETENSORS fake weight data"
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "model.safetensors", "size": 1000},
        ]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=1000
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_weight
            ),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "safetensors"
        assert raw.data == fake_weight
        assert raw.reference is None
        assert raw.metadata["downloaded"] is True
        assert raw.url.endswith("/resolve/main/model.safetensors")
        # 权重已落盘缓存（cache_id = item_id/path，斜杠清洗为下划线）
        cache_file = tmp_path / "lerobot_act_aloha_model.safetensors"
        assert cache_file.is_file()
        assert cache_file.read_bytes() == fake_weight

    @pytest.mark.asyncio
    async def test_returns_reference_over_limit(self) -> None:
        """权重超 max_fetch_bytes：RawReference（resolve url + wget），data 注明未下载。"""
        from rdi.models.common import DataReqType

        big_size = settings.max_fetch_bytes + 1
        adapter = HuggingFaceAdapter()
        mock_tree = [{"type": "file", "path": "policy_weights.bin", "size": big_size}]
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return self._fake_meta(url)

        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=big_size
            ),
            patch.object(adapter, "_download_bytes", side_effect=_fake_download),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "json"
        assert raw.reference is not None
        assert (
            raw.reference.url
            == "https://huggingface.co/lerobot/act_aloha/resolve/main/policy_weights.bin"
        )
        assert raw.reference.download_hint.startswith("wget ")
        assert raw.reference.file_size == big_size
        assert raw.reference.reason == "超过 max_fetch_bytes 自动下载上限"
        payload = json.loads(raw.data)
        assert payload["downloaded"] is False
        assert payload["file_size"] == big_size
        assert payload["download_guide"]["method_hint"].startswith("wget ")
        assert payload["download_guide"]["source_file_url"] == raw.reference.url
        # 体积超限：不下载权重文件（仅 meta 下载）
        assert not any("policy_weights.bin" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_no_weight_candidate_returns_meta(self) -> None:
        """tree 无权重候选：维持 metadata JSON（reference=None）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        mock_tree = [
            {"type": "file", "path": "README.md", "size": 100},
            {"type": "file", "path": "config.json", "size": 200},
        ]
        called_urls: list[str] = []

        async def _fake_download(url: str) -> bytes:
            called_urls.append(url)
            return self._fake_meta(url)

        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(adapter, "_download_bytes", side_effect=_fake_download),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "json"
        assert raw.reference is None
        assert b"modelId" in raw.data
        assert not any("README.md" in u for u in called_urls)

    @pytest.mark.asyncio
    async def test_tree_api_failure_falls_back_to_meta(self) -> None:
        """tree API 失败：降级 metadata（不抛错）。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        with (
            patch.object(
                adapter,
                "_request",
                new_callable=AsyncMock,
                side_effect=AdapterError(message="tree down", source="huggingface"),
            ),
            patch.object(
                adapter,
                "_download_bytes",
                new_callable=AsyncMock,
                return_value=self._fake_meta(""),
            ),
        ):
            raw = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
        assert raw.format == "json"
        assert raw.reference is None
        assert b"modelId" in raw.data

    @pytest.mark.asyncio
    async def test_weight_second_fetch_hits_cache(self) -> None:
        """首次下载落盘后二次 fetch 命中缓存：权重仅下载一次。"""
        from rdi.models.common import DataReqType

        adapter = HuggingFaceAdapter()
        fake_weight = b"fake-weight-bytes"
        mock_tree = [{"type": "file", "path": "policy.pt", "size": 500}]
        with (
            patch.object(adapter, "_request", new_callable=AsyncMock, return_value=mock_tree),
            patch.object(
                adapter, "_head_content_length", new_callable=AsyncMock, return_value=500
            ),
            patch.object(
                adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_weight
            ) as mock_dl,
        ):
            raw1 = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
            raw2 = await adapter.fetch("lerobot/act_aloha", req_type=DataReqType.POLICY_MODEL)
        assert raw1.data == fake_weight
        assert raw2.data == fake_weight
        assert raw1.format == "pt"
        weight_calls = [
            c for c in mock_dl.await_args_list if "resolve/main/policy.pt" in c.args[0]
        ]
        assert len(weight_calls) == 1
