# tests/unit/adapters/test_base.py
"""BaseAdapter 和 TTLCache 的单元测试。"""

import time
from unittest.mock import AsyncMock, patch

import pytest
from bs4 import BeautifulSoup

from rdi.adapters.base import _GITHUB_RAW_FAST_TIMEOUT_S, BaseAdapter, TTLCache
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# ─── TTLCache 测试 ───


class TestTTLCache:
    """TTLCache 单元测试。"""

    def test_cache_set_and_get(self) -> None:
        """正常情况：缓存写入后可读取。"""
        cache = TTLCache(maxsize=5, ttl=60)
        cache["key1"] = "value1"
        assert "key1" in cache
        assert cache["key1"] == "value1"

    def test_cache_miss(self) -> None:
        """边界情况：未写入的键不存在。"""
        cache = TTLCache(maxsize=5, ttl=60)
        assert "nonexistent" not in cache

    def test_cache_ttl_expiration(self) -> None:
        """过期淘汰：TTL 过期后键不可访问。"""
        cache = TTLCache(maxsize=5, ttl=1)  # 1秒过期
        cache["key1"] = "value1"
        assert "key1" in cache
        time.sleep(1.1)
        assert "key1" not in cache

    def test_cache_maxsize_eviction(self) -> None:
        """容量上限：超过 maxsize 时淘汰最旧条目。"""
        cache = TTLCache(maxsize=3, ttl=60)
        cache["a"] = 1
        time.sleep(0.01)  # 确保时间戳不同
        cache["b"] = 2
        time.sleep(0.01)
        cache["c"] = 3
        # 此时 a 最旧
        cache["d"] = 4  # 超过 maxsize，淘汰最旧的 a
        assert "a" not in cache
        assert "b" in cache
        assert "c" in cache
        assert "d" in cache

    def test_cache_overwrite(self) -> None:
        """覆盖写入：对已存在的键写入新值。"""
        cache = TTLCache(maxsize=5, ttl=60)
        cache["key1"] = "old"
        cache["key1"] = "new"
        assert cache["key1"] == "new"


# ─── BaseAdapter 测试 ───


class _StubAdapter(BaseAdapter):
    """测试用 Adapter 桩实现。"""

    source = DataSource.ARXIV

    def __init__(self) -> None:
        super().__init__(base_url="http://localhost:9999", rate_limit=5)

    async def search(self, query: str) -> list[SearchResult]:
        return []

    async def fetch(self, item_id: str) -> RawData:
        return RawData(
            source=DataSource.ARXIV,
            item_id=item_id,
            format="pdf",
            data=b"fake",
            url="http://localhost/fake.pdf",
        )


class TestBaseAdapter:
    """BaseAdapter 单元测试。"""

    def test_adapter_initialization(self) -> None:
        """正常情况：Adapter 初始化正确。"""
        from rdi.config.settings import settings

        adapter = _StubAdapter()
        assert adapter.base_url == "http://localhost:9999"
        assert adapter.source == DataSource.ARXIV
        assert adapter.timeout == settings.adapter_timeout
        assert adapter.max_retry == settings.adapter_max_retry

    def test_make_cache_key_deterministic(self) -> None:
        """缓存键生成：相同输入产生相同键。"""
        key1 = BaseAdapter._make_cache_key("GET", "/path", {"q": "test"})
        key2 = BaseAdapter._make_cache_key("GET", "/path", {"q": "test"})
        assert key1 == key2

    def test_make_cache_key_different_inputs(self) -> None:
        """缓存键生成：不同输入产生不同键。"""
        key1 = BaseAdapter._make_cache_key("GET", "/path1", {})
        key2 = BaseAdapter._make_cache_key("GET", "/path2", {})
        assert key1 != key2

    @pytest.mark.asyncio
    async def test_request_retries_on_failure(self) -> None:
        """异常情况：_request 重试后抛出 AdapterError。"""
        adapter = _StubAdapter()
        adapter.max_retry = 2
        # 不启动服务器，请求必然失败
        with pytest.raises(AdapterError) as exc_info:
            await adapter._request("GET", "/nonexistent")
        assert "Failed" in exc_info.value.message
        assert exc_info.value.source == "arxiv"

    @pytest.mark.asyncio
    async def test_download_bytes_retries_on_failure(self) -> None:
        """异常情况：_download_bytes 重试后抛出 AdapterError。"""
        adapter = _StubAdapter()
        adapter.max_retry = 2
        with pytest.raises(AdapterError) as exc_info:
            await adapter._download_bytes("http://localhost:9999/nonexistent.pdf")
        assert "Download failed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_search_returns_empty_list(self) -> None:
        """正常情况：StubAdapter search 返回空列表。"""
        adapter = _StubAdapter()
        results = await adapter.search("test")
        assert results == []

    @pytest.mark.asyncio
    async def test_fetch_returns_raw_data(self) -> None:
        """正常情况：StubAdapter fetch 返回 RawData。"""
        adapter = _StubAdapter()
        raw = await adapter.fetch("test-id")
        assert raw.item_id == "test-id"
        assert raw.format == "pdf"
        assert raw.data == b"fake"
        assert raw.source == DataSource.ARXIV


# ─── BaseAdapter 新增辅助方法测试 ───


class TestBaseAdapterHelpers:
    """BaseAdapter 新增辅助方法（_attr_str / _scrape_html / _request_text_full_url）的单元测试。"""

    def test_attr_str_returns_string_value(self) -> None:
        """_attr_str 对字符串属性返回原值。"""
        soup = BeautifulSoup('<a href="/paper/abc">link</a>', "lxml")
        tag = soup.find("a")
        assert BaseAdapter._attr_str(tag, "href") == "/paper/abc"

    def test_attr_str_missing_attr_returns_default(self) -> None:
        """_attr_str 对缺失属性返回默认值。"""
        soup = BeautifulSoup("<a>link</a>", "lxml")
        tag = soup.find("a")
        assert BaseAdapter._attr_str(tag, "href") == ""
        assert BaseAdapter._attr_str(tag, "href", "fallback") == "fallback"

    def test_attr_str_multivalue_returns_default(self) -> None:
        """_attr_str 对多值属性（AttributeValueList）返回默认值。"""
        soup = BeautifulSoup('<p class="a b c">text</p>', "lxml")
        tag = soup.find("p")
        # class 是多值属性，bs4 返回列表而非 str，应返回默认值
        result = BaseAdapter._attr_str(tag, "class", "")
        assert isinstance(result, str)
        assert result == ""

    @pytest.mark.asyncio
    async def test_scrape_html_returns_beautifulsoup(self) -> None:
        """_scrape_html 成功返回 BeautifulSoup 对象。"""
        adapter = _StubAdapter()
        with patch.object(
            adapter,
            "_request_text_full_url",
            new_callable=AsyncMock,
            return_value="<html><body><a href='/x'>X</a></body></html>",
        ):
            soup = await adapter._scrape_html("http://example.com")
        assert soup.find("a") is not None
        assert soup.find("a").get_text() == "X"

    @pytest.mark.asyncio
    async def test_scrape_html_raises_on_parse_error(self) -> None:
        """_scrape_html 解析失败抛 AdapterError（异常收窄生效）。"""
        adapter = _StubAdapter()
        with (
            patch.object(
                adapter,
                "_request_text_full_url",
                new_callable=AsyncMock,
                return_value="dummy-html",
            ),
            patch("rdi.adapters.base.BeautifulSoup", side_effect=ValueError("parse error")),
            pytest.raises(AdapterError) as exc_info,
        ):
            await adapter._scrape_html("http://example.com")
        assert "HTML parsing failed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_request_text_full_url_retries_on_failure(self) -> None:
        """_request_text_full_url 重试耗尽后抛 AdapterError。"""
        adapter = _StubAdapter()
        adapter.max_retry = 2
        with pytest.raises(AdapterError) as exc_info:
            await adapter._request_text_full_url("GET", "http://localhost:9999/nonexistent")
        assert "Failed" in exc_info.value.message

    @pytest.mark.asyncio
    async def test_head_content_length_returns_none_on_connection_error(self) -> None:
        """_head_content_length 连接失败时返回 None（不抛异常，不阻塞主流程）。

        localhost:9999 未启动，HEAD 必然连接失败 → 返回 None。
        """
        adapter = _StubAdapter()
        result = await adapter._head_content_length("http://localhost:9999/file.pdf")
        assert result is None


# ─── GitHub raw 镜像兜底测试（E4）───


class TestBaseAdapterMirrorFallback:
    """_download_bytes 的 GitHub raw 镜像兜底逻辑测试（E4）。"""

    def test_to_github_mirror_url_transforms_raw_url(self) -> None:
        """raw.githubusercontent.com URL 正确转为 jsdelivr 镜像 URL。"""
        adapter = _StubAdapter()
        raw = (
            "https://raw.githubusercontent.com/frankaemika/franka_ros/develop/"
            "franka_description/robots/panda/panda.urdf.xacro"
        )
        mirror = adapter._to_github_mirror_url(raw)
        assert mirror == (
            "https://cdn.jsdelivr.net/gh/frankaemika/franka_ros@develop/"
            "franka_description/robots/panda/panda.urdf.xacro"
        )

    def test_to_github_mirror_url_returns_none_for_non_github_url(self) -> None:
        """非 raw.githubusercontent.com URL 返回 None（不镜像）。"""
        adapter = _StubAdapter()
        assert adapter._to_github_mirror_url("https://example.com/file.urdf") is None
        assert adapter._to_github_mirror_url("https://huggingface.co/x") is None

    def test_to_github_mirror_url_returns_none_when_mirror_disabled(self) -> None:
        """镜像基础 URL 配置为空时返回 None（禁用镜像）。"""
        adapter = _StubAdapter()
        adapter._github_mirror_base = ""
        raw = "https://raw.githubusercontent.com/owner/repo/main/file.xml"
        assert adapter._to_github_mirror_url(raw) is None

    def test_to_github_mirror_url_returns_none_for_malformed_url(self) -> None:
        """路径缺少 owner/repo/ref/path 之一时返回 None。"""
        adapter = _StubAdapter()
        # 只有 owner/repo，缺 ref 和 path
        assert adapter._to_github_mirror_url("https://raw.githubusercontent.com/owner/repo") is None

    @pytest.mark.asyncio
    async def test_download_bytes_falls_back_to_mirror_on_github_raw_failure(
        self,
    ) -> None:
        """GitHub raw 主 URL 失败时自动走 jsdelivr 镜像。

        mock _download_bytes_single：主 URL 抛 AdapterError，镜像 URL 返回数据，
        验证 _download_bytes 返回镜像数据且两次调用 URL 符合预期。
        """
        adapter = _StubAdapter()
        primary_url = "https://raw.githubusercontent.com/o/r/main/file.xml"
        fake = b"<xml/>"

        async def fake_single(url: str, **kwargs: object) -> bytes:
            if url == primary_url:
                raise AdapterError(message="primary fail", source="arxiv")
            return fake

        with patch.object(
            adapter,
            "_download_bytes_single",
            new_callable=AsyncMock,
            side_effect=fake_single,
        ) as mock_single:
            result = await adapter._download_bytes(primary_url)
        assert result == fake
        # 两次调用：主 URL + 镜像 URL
        assert mock_single.await_count == 2
        called_urls = [call.args[0] for call in mock_single.call_args_list]
        assert called_urls[0] == primary_url
        assert called_urls[1].startswith("https://cdn.jsdelivr.net/gh/o/r@main/")

    @pytest.mark.asyncio
    async def test_download_bytes_skips_mirror_for_non_github_url(self) -> None:
        """非 GitHub raw URL 失败时不走镜像，直接抛主错误。"""
        adapter = _StubAdapter()
        primary_url = "https://example.com/file.urdf"
        primary_err = AdapterError(message="primary fail", source="arxiv")

        async def fake_single(url: str, **kwargs: object) -> bytes:
            raise primary_err

        with (
            patch.object(
                adapter,
                "_download_bytes_single",
                new_callable=AsyncMock,
                side_effect=fake_single,
            ) as mock_single,
            pytest.raises(AdapterError) as exc_info,
        ):
            await adapter._download_bytes(primary_url)
        assert exc_info.value is primary_err
        # 仅主 URL 调用一次，镜像未触发
        assert mock_single.await_count == 1

    @pytest.mark.asyncio
    async def test_download_bytes_raises_mirror_error_when_both_fail(self) -> None:
        """主 URL 与镜像均失败时抛镜像错误（链式保留主错误）。"""
        adapter = _StubAdapter()
        primary_url = "https://raw.githubusercontent.com/o/r/main/file.xml"

        async def fake_single(url: str, **kwargs: object) -> bytes:
            raise AdapterError(message=f"fail {url}", source="arxiv")

        with (
            patch.object(
                adapter,
                "_download_bytes_single",
                new_callable=AsyncMock,
                side_effect=fake_single,
            ),
            pytest.raises(AdapterError) as exc_info,
        ):
            await adapter._download_bytes(primary_url)
        # 镜像错误为最终抛出的异常
        assert "cdn.jsdelivr.net" in exc_info.value.message
        # 主错误作为 __cause__ 链式保留
        assert isinstance(exc_info.value.__cause__, AdapterError)
        assert "raw.githubusercontent.com" in exc_info.value.__cause__.message

    @pytest.mark.asyncio
    async def test_download_bytes_primary_uses_fast_timeout_for_github_raw(
        self,
    ) -> None:
        """镜像 URL 的主尝试用短超时 + 不重试（避免挂起耗尽探活预算）。

        mock _download_bytes_single 直接返回数据（主 URL 成功），
        验证主调用传入 timeout=_GITHUB_RAW_FAST_TIMEOUT_S、max_retry=1。
        """
        adapter = _StubAdapter()
        primary_url = "https://raw.githubusercontent.com/o/r/main/file.xml"
        fake = b"<xml/>"
        with patch.object(
            adapter,
            "_download_bytes_single",
            new_callable=AsyncMock,
            return_value=fake,
        ) as mock_single:
            await adapter._download_bytes(primary_url)
        mock_single.assert_awaited_once()
        call = mock_single.call_args_list[0]
        assert call.args == (primary_url,)
        assert call.kwargs["timeout"] == _GITHUB_RAW_FAST_TIMEOUT_S
        assert call.kwargs["max_retry"] == 1


# ─── 数据包自包含：XML 外部资产下载（P0-3）───


class TestBaseAdapterXmlAssets:
    """_download_xml_with_assets 的单元测试（P0-3 数据包自包含）。"""

    @pytest.mark.asyncio
    async def test_downloads_relative_mesh_against_xml_dir(self) -> None:
        """正常情况：URDF 中的相对 mesh 路径以 XML URL 目录为基准下载。"""
        adapter = _StubAdapter()
        xml = (
            b'<robot name="r"><link name="base"><visual><geometry>'
            b'<mesh filename="meshes/base.stl"/>'
            b"</geometry></visual></link></robot>"
        )
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=b"mesh-data"
        ) as mock_dl:
            assets = await adapter._download_xml_with_assets(
                "https://example.com/models/panda.urdf", xml
            )
        assert assets == {"meshes/base.stl": b"mesh-data"}
        mock_dl.assert_awaited_once()
        # 下载 URL 以 xml_url 所在目录为基准
        assert mock_dl.call_args.args[0] == "https://example.com/models/meshes/base.stl"

    @pytest.mark.asyncio
    async def test_invalid_xml_returns_empty(self) -> None:
        """异常情况：XML 解析失败返回空 dict（降级策略，不抛异常）。"""
        adapter = _StubAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            assets = await adapter._download_xml_with_assets(
                "https://example.com/models/panda.urdf", b"not <xml"
            )
        assert assets == {}
        mock_dl.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_skips_absolute_urls_and_normalizes_relative(self) -> None:
        """package:// 与 https:// 绝对引用被跳过；相对路径规范化（去 ./）。"""
        adapter = _StubAdapter()
        xml = (
            b'<robot name="r">'
            b'<link name="a"><visual><geometry><mesh filename="package://pkg/meshes/a.stl"/>'
            b"</geometry></visual></link>"
            b'<link name="b"><visual><geometry><mesh filename="https://example.com/meshes/b.stl"/>'
            b"</geometry></visual></link>"
            b'<link name="c"><visual><geometry><mesh filename="./meshes/c.stl"/>'
            b"</geometry></visual></link>"
            b"</robot>"
        )
        with patch.object(
            adapter, "_download_bytes", new_callable=AsyncMock, return_value=b"x"
        ) as mock_dl:
            assets = await adapter._download_xml_with_assets(
                "https://example.com/models/panda.urdf", xml
            )
        # 仅相对路径 c 被下载，且前导 ./ 已规范化
        assert assets == {"meshes/c.stl": b"x"}
        assert mock_dl.await_count == 1
        assert mock_dl.call_args.args[0] == "https://example.com/models/meshes/c.stl"

    @pytest.mark.asyncio
    async def test_no_references_does_not_download(self) -> None:
        """无 mesh/texture 引用时不额外调用 _download_bytes。"""
        adapter = _StubAdapter()
        with patch.object(adapter, "_download_bytes", new_callable=AsyncMock) as mock_dl:
            assets = await adapter._download_xml_with_assets(
                "https://example.com/models/panda.urdf", b'<robot name="panda"/>'
            )
        assert assets == {}
        mock_dl.assert_not_awaited()


# ─── 本地文件缓存测试 ───


class TestBaseAdapterFileCache:
    """BaseAdapter 本地文件缓存（data/cache/<source>/）方法测试。"""

    @staticmethod
    def _adapter_with_root(tmp_path) -> BaseAdapter:
        """构造 stub Adapter 并把缓存根目录指向临时目录。"""
        adapter = _StubAdapter()
        adapter.cache_root = lambda: tmp_path  # type: ignore[method-assign]
        return adapter

    def test_cache_root_dir_name_from_source(self) -> None:
        """cache_root 目录名默认取 source.value，父级目录为 cache。"""
        adapter = _StubAdapter()  # source = DataSource.ARXIV
        root = adapter.cache_root()
        assert root.name == "arxiv"
        assert root.parent.name == "cache"

    def test_cache_root_uses_custom_cache_dir_name(self, tmp_path) -> None:
        """cache_dir_name 覆写后生效。"""
        adapter = _StubAdapter()
        adapter.cache_dir_name = "my-source"
        root = adapter.cache_root()
        assert root.name == "my-source"

    def test_get_cache_path_sanitizes_item_id(self, tmp_path) -> None:
        """item_id 中的不安全字符被清洗为下划线，不产生子目录。"""
        adapter = self._adapter_with_root(tmp_path)
        path = adapter.get_cache_path("a/b\\c:d e", suffix=".obj")
        assert path == tmp_path / "a_b_c_d_e.obj"
        assert path.parent == tmp_path

    def test_get_cache_path_without_suffix(self, tmp_path) -> None:
        """无 suffix 时直接以 item_id 命名。"""
        adapter = self._adapter_with_root(tmp_path)
        assert adapter.get_cache_path("item") == tmp_path / "item"

    def test_save_and_load_roundtrip(self, tmp_path) -> None:
        """save_to_cache 落盘后 is_cached / load_from_cache 均可命中。"""
        adapter = self._adapter_with_root(tmp_path)
        saved = adapter.save_to_cache("item1", b"payload")
        assert saved == tmp_path / "item1"
        assert adapter.is_cached("item1")
        assert adapter.load_from_cache("item1") == b"payload"

    def test_save_creates_nested_dirs(self, tmp_path) -> None:
        """缓存根目录不存在时自动创建（mkdir parents=True）。"""
        adapter = _StubAdapter()
        root = tmp_path / "nested" / "dir"
        adapter.cache_root = lambda: root  # type: ignore[method-assign]
        adapter.save_to_cache("x", b"d")
        assert (root / "x").is_file()

    def test_load_miss_returns_none(self, tmp_path) -> None:
        """未命中时 load_from_cache 返回 None、is_cached 返回 False。"""
        adapter = self._adapter_with_root(tmp_path)
        assert adapter.load_from_cache("missing") is None
        assert not adapter.is_cached("missing")

    def test_is_cached_false_for_empty_file(self, tmp_path) -> None:
        """空文件不算有效缓存（非空才命中）。"""
        adapter = self._adapter_with_root(tmp_path)
        (tmp_path / "empty").write_bytes(b"")
        assert not adapter.is_cached("empty")
        assert adapter.load_from_cache("empty") is None

    def test_suffix_distinguishes_files(self, tmp_path) -> None:
        """同一 item_id 不同 suffix 互不干扰。"""
        adapter = self._adapter_with_root(tmp_path)
        adapter.save_to_cache("item", b"a", suffix=".urdf")
        adapter.save_to_cache("item", b"b", suffix=".xacro")
        assert adapter.load_from_cache("item", suffix=".urdf") == b"a"
        assert adapter.load_from_cache("item", suffix=".xacro") == b"b"
