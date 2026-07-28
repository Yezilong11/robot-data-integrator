# src/rdi/adapters/base.py
"""统一 Adapter 抽象基类。

所有具体 Adapter 继承此类，实现 search / fetch 方法。
基类提供带重试和缓存的 HTTP 请求能力。
"""

import asyncio
import hashlib
import time
from abc import ABC, abstractmethod
from typing import Any, cast

import aiohttp

from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult


class TTLCache:
    """简单的 TTL 缓存实现。"""

    def __init__(self, maxsize: int = 500, ttl: int = 3600) -> None:
        self._cache: dict[str, tuple[float, Any]] = {}
        self.maxsize = maxsize
        self.ttl = ttl

    def __contains__(self, key: str) -> bool:
        if key not in self._cache:
            return False
        ts, _ = self._cache[key]
        if time.time() - ts > self.ttl:
            del self._cache[key]
            return False
        return True

    def __getitem__(self, key: str) -> Any:
        _, value = self._cache[key]
        return value

    def __setitem__(self, key: str, value: Any) -> None:
        if len(self._cache) >= self.maxsize:
            # 淘汰最旧的
            oldest = min(self._cache, key=lambda k: self._cache[k][0])
            del self._cache[oldest]
        self._cache[key] = (time.time(), value)


class BaseAdapter(ABC):
    """数据源 Adapter 基类。

    约定：
    - 每个 Adapter 文件不超过 300 行，超过则拆分
    - 必须实现 search / fetch 方法，签名与基类一致
    - 所有返回值使用 Pydantic model
    - 在 tests/unit/adapters/fixtures/ 下放录制的 API 响应 JSON
    """

    source: DataSource  # 子类必须定义自己的源标识

    def __init__(
        self,
        base_url: str,
        rate_limit: int = 10,
    ) -> None:
        self.base_url = base_url
        self.semaphore = asyncio.Semaphore(rate_limit)
        self.cache = TTLCache(maxsize=500, ttl=settings.adapter_cache_ttl)
        self.timeout = settings.adapter_timeout
        self.max_retry = settings.adapter_max_retry

    @abstractmethod
    async def search(self, query: str) -> list[SearchResult]:
        """搜索并返回结果列表。

        Args:
            query: 搜索查询词

        Returns:
            SearchResult 列表，空列表表示无结果
        """
        ...

    @abstractmethod
    async def fetch(self, item_id: str) -> RawData:
        """根据 ID 获取具体数据。

        Args:
            item_id: 数据项唯一标识

        Returns:
            RawData 包含原始数据

        Raises:
            AdapterError: 获取失败
        """
        ...

    async def _request(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> Any:
        """带重试和缓存的 HTTP 请求。

        Args:
            method: HTTP 方法（GET/POST/...）
            path: API 路径（拼接到 base_url 后）
            **kwargs: 传递给 aiohttp 的额外参数

        Returns:
            JSON 响应体

        Raises:
            AdapterError: 重试耗尽
        """
        cache_key = self._make_cache_key(method, path, kwargs)
        if cache_key in self.cache:
            return self.cache[cache_key]

        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})

        async with self.semaphore:
            for attempt in range(self.max_retry):
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.request(
                            method,
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=self.timeout),
                            **kwargs,
                        ) as resp,
                    ):
                        resp.raise_for_status()
                        data = await resp.json()
                        self.cache[cache_key] = data
                        return data
                except (aiohttp.ClientError, TimeoutError) as e:
                    if attempt == self.max_retry - 1:
                        raise AdapterError(
                            message=f"Failed {method} {path}: {e}",
                            source=self.source.value,
                            status_code=getattr(e, "status", None),
                        ) from e
                    await asyncio.sleep(2**attempt)  # 指数退避
            raise AdapterError(
                message=f"Failed {method} {path}: exhausted retries",
                source=self.source.value,
            )

    async def _request_text(
        self,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> str:
        """带重试的 HTTP 请求，返回文本响应（用于 XML 等）。

        Args:
            method: HTTP 方法
            path: API 路径
            **kwargs: 传递给 aiohttp 的额外参数

        Returns:
            响应文本字符串

        Raises:
            AdapterError: 重试耗尽
        """
        cache_key = self._make_cache_key(method, path, kwargs)
        if cache_key in self.cache:
            return cast("str", self.cache[cache_key])

        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})

        async with self.semaphore:
            for attempt in range(self.max_retry):
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.request(
                            method,
                            url,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(total=self.timeout),
                            **kwargs,
                        ) as resp,
                    ):
                        resp.raise_for_status()
                        text = await resp.text()
                        self.cache[cache_key] = text
                        return text
                except (aiohttp.ClientError, TimeoutError) as e:
                    if attempt == self.max_retry - 1:
                        raise AdapterError(
                            message=f"Failed {method} {path}: {e}",
                            source=self.source.value,
                            status_code=getattr(e, "status", None),
                        ) from e
                    await asyncio.sleep(2**attempt)
            raise AdapterError(
                message=f"Failed {method} {path}: exhausted retries",
                source=self.source.value,
            )

    async def _download_bytes(self, url: str) -> bytes:
        """下载二进制文件（如 PDF、mesh文件）。"""
        async with self.semaphore:
            for attempt in range(self.max_retry):
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=self.timeout * 2),
                        ) as resp,
                    ):
                        resp.raise_for_status()
                        return await resp.read()
                except (aiohttp.ClientError, TimeoutError) as e:
                    if attempt == self.max_retry - 1:
                        raise AdapterError(
                            message=f"Download failed {url}: {e}",
                            source=self.source.value,
                        ) from e
                    await asyncio.sleep(2**attempt)
            raise AdapterError(
                message=f"Download failed {url}: exhausted retries",
                source=self.source.value,
            )

    @staticmethod
    def _make_cache_key(method: str, path: str, kwargs: dict[str, Any]) -> str:
        """生成缓存键。"""
        key_str = f"{method}:{path}:{sorted(kwargs.items())}"
        return hashlib.md5(key_str.encode()).hexdigest()
