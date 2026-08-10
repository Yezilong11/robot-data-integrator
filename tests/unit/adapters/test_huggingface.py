# tests/unit/adapters/test_huggingface.py
"""HuggingFaceAdapter 的单元测试。"""

import json
from unittest.mock import AsyncMock, patch

import pytest

from rdi.adapters.huggingface import HuggingFaceAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource, DataReqType


class TestHuggingFaceAdapter:
    """HuggingFaceAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.source == DataSource.HUGGINGFACE

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = HuggingFaceAdapter()
        assert adapter.base_url == "https://huggingface.co/api"

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
        """Mock 驱动：fetch 默认返回 RawData 且字段正确（config.json 路径）。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert"}'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_config
        ) as mock_download:
            raw = await adapter.fetch("bert-base-uncased")
            assert raw.source == DataSource.HUGGINGFACE
            assert raw.item_id == "bert-base-uncased"
            assert raw.format == "json"
            assert raw.size_bytes > 0
            # 默认路径：下载 config.json
            called_url = mock_download.call_args[0][0]
            assert called_url.endswith("/resolve/main/config.json")

    @pytest.mark.asyncio
    async def test_fetch_default_req_type_none(self) -> None:
        """默认行为：req_type=None 时拉取 config.json。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "bert", "hidden_size": 768}'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_config
        ) as mock_download:
            raw = await adapter.fetch("some/model", req_type=None)
            called_url = mock_download.call_args[0][0]
            assert called_url.endswith("/resolve/main/config.json")
            # config.json 内容正确解析
            parsed = json.loads(raw.data)
            assert "hidden_size" in parsed

    @pytest.mark.asyncio
    async def test_fetch_other_req_type_uses_config(self) -> None:
        """其他需求类型（如 ROBOT_URDF）仍拉取 config.json（向后兼容）。"""
        adapter = HuggingFaceAdapter()
        fake_config = b'{"model_type": "x"}'
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_config
        ) as mock_download:
            raw = await adapter.fetch("some/model", req_type=DataReqType.ROBOT_URDF)
            called_url = mock_download.call_args[0][0]
            assert called_url.endswith("/resolve/main/config.json")

    @pytest.mark.asyncio
    async def test_fetch_policy_model_uses_api(self) -> None:
        """POLICY_MODEL 类型：调用 HF /api/models/{id} 获取 model_info.json，
        并确保返回数据包含 modelId/tags/siblings（PolicyInterfaceSkill 所需字段）。"""
        adapter = HuggingFaceAdapter()
        # HuggingFace /api/models/{repo_id} 真实响应的核心字段子集
        fake_model_info = {
            "modelId": "aloha-ct/aloha",
            "id": "aloha-ct/aloha",
            "tags": ["robotics", "pytorch", "act"],
            "siblings": [
                {"rfilename": "config.json"},
                {"rfilename": "policy.pt", "size": "12345678"},
                {"rfilename": "README.md"},
            ],
            "library_name": "transformers",
            "downloads": 100,
            "likes": 50,
        }
        fake_bytes = json.dumps(fake_model_info).encode("utf-8")

        # POLICY_MODEL 走 _download_bytes 下载 /api/models/... URL
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=fake_bytes
        ) as mock_download:
            raw = await adapter.fetch("aloha-ct/aloha", req_type=DataReqType.POLICY_MODEL)

            # 1. URL 正确：是 /api/models/{repo_id}，不是 /resolve/main/config.json
            called_url = mock_download.call_args[0][0]
            assert "/api/models/aloha-ct/aloha" in called_url
            assert "/resolve/main/config.json" not in called_url

            # 2. 格式和元数据正确
            assert raw.format == "json"
            assert raw.item_id == "aloha-ct/aloha"
            assert raw.size_bytes == len(fake_bytes)

            # 3. 数据可解析，且包含 PolicyInterfaceSkill 期望的字段
            parsed = json.loads(raw.data)
            assert "modelId" in parsed  # model_info.json 特有字段
            assert "tags" in parsed and isinstance(parsed["tags"], list)
            assert "siblings" in parsed and isinstance(parsed["siblings"], list)
            # 证明不是 config.json（config.json 一般不会有 siblings 字段）
            assert "siblings" in parsed
