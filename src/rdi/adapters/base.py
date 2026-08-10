# src/rdi/adapters/base.py
"""统一 Adapter 抽象基类。

所有具体 Adapter 继承此类，实现 search / fetch 方法。
基类提供带重试和缓存的 HTTP 请求能力。
"""

import asyncio
import hashlib
import posixpath
import re
import ssl
import time
import xml.etree.ElementTree as ET
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import aiohttp
import certifi
from bs4 import BeautifulSoup
from bs4.exceptions import FeatureNotFound

from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 默认 User-Agent，避免商业站点拒绝无 UA 请求
_DEFAULT_USER_AGENT = "rdi-bot/1.0 (+https://github.com/robotics-data)"

# ponytail: Anaconda Python 在 Windows 上系统 CA 路径为空，aiohttp 默认 SSL 校验
# 会 CERTIFICATE_VERIFY_FAILED。统一用 certifi 的 CA bundle（已在依赖中）。
_SSL_CONTEXT = ssl.create_default_context(cafile=certifi.where())

# E4: raw.githubusercontent.com 主 URL 的快速失败超时。
# raw CDN 健康时 <2s 响应；挂起时会耗尽探活 30s 外部预算，导致 jsdelivr 镜像
# 来不及兜底（主 URL 用 self.timeout*2=60s 超时 × 3 次重试，单次挂起即占满预算）。
# 主镜像 URL 改用 8s 短超时 + 不重试，挂起时快速转镜像；镜像用正常超时+重试。
_GITHUB_RAW_FAST_TIMEOUT_S = 8.0

# 资产递归下载的 include 嵌套深度上限（主 XML 为第 0 层）。
# 超过上限即终止展开（不抛异常），避免 include 链过深/异常结构拖垮下载。
_MAX_ASSET_DEPTH = 3


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

    # 本地文件缓存目录名（data/cache/<cache_dir_name>/）；默认取 source.value，子类可覆写
    cache_dir_name: str | None = None

    def cache_root(self) -> Path:
        """本地文件缓存根目录 ``data/cache/<cache_dir_name>/``。"""
        dir_name = self.cache_dir_name or self.source.value
        return Path(__file__).resolve().parents[3] / "data" / "cache" / dir_name

    def get_cache_path(self, item_id: str, suffix: str = "") -> Path:
        """返回 item_id 对应的缓存文件路径（item_id 中的不安全字符会被清洗）。"""
        sanitized = re.sub(r'[\\/:*?"<>|\s]', "_", item_id)
        return self.cache_root() / f"{sanitized}{suffix}"

    def is_cached(self, item_id: str, suffix: str = "") -> bool:
        """缓存文件是否存在且非空。"""
        path = self.get_cache_path(item_id, suffix)
        return path.is_file() and path.stat().st_size > 0

    def save_to_cache(self, item_id: str, data: bytes, suffix: str = "") -> Path:
        """将 bytes 写入缓存文件并返回路径。"""
        path = self.get_cache_path(item_id, suffix)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def load_from_cache(self, item_id: str, suffix: str = "") -> bytes | None:
        """命中缓存返回 bytes，未命中返回 None。"""
        path = self.get_cache_path(item_id, suffix)
        if path.is_file() and path.stat().st_size > 0:
            return path.read_bytes()
        return None

    # ─── D3: 来源级本地数据集挂载 ───
    # settings.local_datasets 按「来源名 → 本地目录」挂载整个数据集，adapter fetch
    # 时优先在本地命中（source=local，不发任何网络请求），未命中走网络。与前端
    # per-req 注入（state.local_files，req_id → 路径，parse_convert 节点消费）层级
    # 不同、互不干扰：local_files 绕过 adapter 直接注入单文件，local_datasets 在
    # adapter 内按 item_id/object_name 定位。本地目录布局与远程仓库/URL 的路径同构
    # （GraspNet/YCB/DexGrasp 为 HF repo 根，Franka/Allegro/Robotiq/MuJoCo/Isaac 为
    # GitHub 仓库根），各 adapter 用与网络相同的定位逻辑（扩展名/物体名/路径映射）
    # 在本地找文件。

    def local_dataset_root(self) -> Path | None:
        """返回本数据源在 ``settings.local_datasets`` 中挂载的本地目录。

        未配置或目录不存在返回 None（调用方保持既有网络流程）。
        """
        root = settings.local_datasets.get(self.source.value)
        if not root:
            return None
        path = Path(root)
        return path if path.is_dir() else None

    @staticmethod
    def _walk_local_tree(root: Path, rel_subdir: str = "") -> list[dict[str, Any]]:
        """递归扫描本地目录，构造与远程文件树（tree API）同构的条目列表。

        ``rel_subdir`` 非空时只扫描其下文件；返回条目的 ``path`` 均为相对
        ``root`` 的正斜杠路径（与网络 tree API 的 path 字段一致，便于复用
        ``_find_file_by_ext``/``find_object_grasp_file`` 等按扩展名/物体名
        定位逻辑）。目录不存在返回空列表。
        """
        scan_root = root / rel_subdir if rel_subdir else root
        if not scan_root.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for full in sorted(scan_root.rglob("*")):
            if full.is_file():
                rel = full.relative_to(root).as_posix()
                try:
                    size = full.stat().st_size
                except OSError:
                    size = 0
                items.append({"type": "file", "path": rel, "size": size})
        return items

    def _find_local_file(self, rel_paths: Iterable[str]) -> Path | None:
        """在本地挂载目录中按相对路径列表查找第一个存在且非空的文件。

        相对路径与远程仓库中的路径同构（如 ``grasp_label/xxx.npz``、
        ``franka_description/robots/panda/...``）。未配置挂载、相对路径越出挂载根
        （路径穿越防护）或未命中均返回 None。
        """
        root = self.local_dataset_root()
        if root is None:
            return None
        root_resolved = root.resolve()
        for rel in rel_paths:
            if not rel:
                continue
            candidate = (root_resolved / rel).resolve()
            try:
                candidate.relative_to(root_resolved)
            except ValueError:
                continue  # 路径穿越防护（../ 等越出挂载根）
            if candidate.is_file() and candidate.stat().st_size > 0:
                return candidate
        return None

    def _local_raw(self, item_id: str, candidates: list[tuple[str, str]]) -> RawData | None:
        """本地数据集命中：按 ``(相对路径, format)`` 候选列表读取第一个存在的文件。

        XML 类格式（urdf/xacro/xml）自动从本地挂载目录收集引用的资产
        （mesh/texture/include，复用 ``_resolve_asset_rel`` 规范化、不发网络请求）；
        命中返回 ``source=LOCAL`` 的 RawData，未命中返回 None（调用方走网络）。
        """
        root = self.local_dataset_root()
        if root is None:
            return None
        for rel_path, fmt in candidates:
            path = self._find_local_file([rel_path])
            if path is None:
                continue
            data = path.read_bytes()
            assets: dict[str, bytes] = {}
            if fmt in ("urdf", "xacro", "xml"):
                assets = self._local_assets_from_xml(data, posixpath.dirname(rel_path))
            return RawData(
                source=DataSource.LOCAL,
                item_id=item_id,
                format=fmt,
                data=data,
                url=f"local://{self.source.value}/{rel_path}",
                size_bytes=len(data),
                assets=assets,
            )
        return None

    def _local_assets_from_xml(self, xml_bytes: bytes, xml_rel_dir: str) -> dict[str, bytes]:
        """从本地挂载目录读取 XML 引用的外部资产（mesh/texture/include），不发起网络。

        D3：本地命中主 XML 时，其引用的相对路径资产同样优先从本地读取（存在则
        读入，缺失跳过，与 ``_download_xml_with_assets`` 的降级策略一致）。include
        链递归展开（深度上限 ``_MAX_ASSET_DEPTH``、``seen`` 去重防环），assets 键为
        相对主 XML 的完整路径（与网络版一致）。
        """
        assets: dict[str, bytes] = {}

        def _collect(root: ET.Element, base_dir: str, depth: int, seen: set[str]) -> None:
            if depth > _MAX_ASSET_DEPTH:
                return
            for elem in root.iter():
                # 去掉命名空间前缀（如 {http://...}mesh → mesh）后统一小写匹配
                tag = elem.tag.split("}")[-1].lower()
                if tag not in {"mesh", "texture", "include"}:
                    continue
                rel = (elem.get("filename") or elem.get("file") or "").strip()
                norm = self._resolve_asset_rel(rel)
                if norm is None:
                    continue
                full_rel = posixpath.join(base_dir, norm) if base_dir else norm
                if full_rel in seen:
                    continue  # 同一路径已处理（去重/防环）
                path = self._find_local_file([full_rel])
                if path is None:
                    continue  # 本地缺失资产跳过（与网络版单资产失败只跳过一致）
                content = path.read_bytes()
                assets[full_rel] = content
                seen.add(full_rel)
                if tag != "include":
                    continue
                try:
                    sub_root = ET.fromstring(content)
                except Exception:  # noqa: BLE001 — 子 XML 解析失败按无资产处理
                    continue
                _collect(
                    sub_root,
                    posixpath.join(base_dir, posixpath.dirname(norm)),
                    depth + 1,
                    seen,
                )

        try:
            root = ET.fromstring(xml_bytes)
        except Exception:  # noqa: BLE001 — 解析失败按无资产处理（与网络版一致）
            return assets
        _collect(root, xml_rel_dir, 0, set())
        return assets

    def __init__(
        self,
        base_url: str,
        rate_limit: int = 10,
    ) -> None:
        self.base_url = base_url
        self.semaphore = asyncio.Semaphore(rate_limit)
        self.cache = TTLCache(maxsize=settings.cache_max_entries, ttl=settings.cache_ttl_seconds)
        self.timeout = settings.adapter_timeout
        self.max_retry = settings.adapter_max_retry
        # E4: raw.githubusercontent.com 镜像兜底基础 URL（空字符串则禁用镜像）
        self._github_mirror_base = settings.github_raw_mirror_base_url

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
                            ssl=_SSL_CONTEXT,
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
                            ssl=_SSL_CONTEXT,
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

    async def _scrape_html(self, url: str) -> BeautifulSoup:
        """获取网页 HTML 并解析为 BeautifulSoup 对象。

        用于网页抓取类 Adapter 的文档原始对接方式。

        Args:
            url: 目标网页 URL

        Returns:
            BeautifulSoup 对象

        Raises:
            AdapterError: 获取或解析失败
        """
        html_text = await self._request_text_full_url("GET", url)
        try:
            return BeautifulSoup(html_text, "lxml")
        except (FeatureNotFound, ValueError, TypeError) as e:
            raise AdapterError(
                message=f"HTML parsing failed for {url}: {e}",
                source=self.source.value,
            ) from e

    async def _request_text_full_url(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> str:
        """带重试和缓存的 HTTP 请求，使用完整 URL（非 base_url+path），返回文本响应。

        适用于网页抓取场景，URL 为完整地址而非 API 路径。
        默认注入 User-Agent，可通过 kwargs["headers"] 覆盖。

        Args:
            method: HTTP 方法
            url: 完整 URL
            **kwargs: 传递给 aiohttp 的额外参数（headers 等）

        Returns:
            响应文本字符串

        Raises:
            AdapterError: 重试耗尽
        """
        cache_key = self._make_cache_key(method, url, kwargs)
        if cache_key in self.cache:
            return cast("str", self.cache[cache_key])

        headers = dict(kwargs.pop("headers", {}))
        headers.setdefault("User-Agent", _DEFAULT_USER_AGENT)

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
                            ssl=_SSL_CONTEXT,
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
                            message=f"Failed {method} {url}: {e}",
                            source=self.source.value,
                            status_code=getattr(e, "status", None),
                        ) from e
                    await asyncio.sleep(2**attempt)
            raise AdapterError(
                message=f"Failed {method} {url}: exhausted retries",
                source=self.source.value,
            )

    @staticmethod
    def _attr_str(tag: Any, name: str, default: str = "") -> str:
        """从 bs4 标签安全提取字符串属性。

        bs4 的 ``Tag.get`` 对多值属性返回 AttributeValueList，
        此方法统一返回 str，便于类型检查与后续处理。
        """
        value = tag.get(name, default)
        return value if isinstance(value, str) else default

    async def _download_bytes(self, url: str) -> bytes:
        """下载二进制文件（如 PDF、mesh文件），含 GitHub raw 镜像兜底。

        C13 修复：4xx 永久错误（除 408 超时、429 限流）立即抛出不重试。
        E4 修复：raw.githubusercontent.com 主 URL 失败时自动改走 jsdelivr 镜像
        （Franka/Allegro/Robotiq/MuJoCo/Isaac 等 Adapter 的 URDF/XML/Python
        配置文件均走 raw.githubusercontent.com，国内 CDN 偶发 30s 超时）。
        为避免主 URL 挂起耗尽探活外部超时预算，镜像 URL 的主尝试用
        _GITHUB_RAW_FAST_TIMEOUT_S 短超时 + 不重试，挂起时快速转镜像；
        镜像本身用正常超时+重试。非 raw.githubusercontent.com URL 不镜像。
        """
        mirror_url = self._to_github_mirror_url(url)
        if mirror_url is None:
            return await self._download_bytes_single(url)
        try:
            return await self._download_bytes_single(
                url, timeout=_GITHUB_RAW_FAST_TIMEOUT_S, max_retry=1
            )
        except AdapterError as primary_err:
            try:
                return await self._download_bytes_single(mirror_url)
            except AdapterError as mirror_err:
                raise mirror_err from primary_err

    async def _download_bytes_single(
        self,
        url: str,
        *,
        timeout: float | None = None,
        max_retry: int | None = None,
    ) -> bytes:
        """单 URL 下载（带重试，C13 4xx 不重试）。

        _download_bytes 的内部实现，不含镜像兜底逻辑。

        Args:
            url: 下载 URL
            timeout: 单请求总超时秒数；None 用 self.timeout * 2
            max_retry: 最大重试次数；None 用 self.max_retry
        """
        req_timeout = timeout if timeout is not None else self.timeout * 2
        retries = max_retry if max_retry is not None else self.max_retry
        async with self.semaphore:
            for attempt in range(retries):
                try:
                    async with (
                        aiohttp.ClientSession() as session,
                        session.get(
                            url,
                            timeout=aiohttp.ClientTimeout(total=req_timeout),
                            ssl=_SSL_CONTEXT,
                        ) as resp,
                    ):
                        resp.raise_for_status()
                        return await resp.read()
                except (aiohttp.ClientError, TimeoutError) as e:
                    # C13: 4xx 永久错误（除 408 超时、429 限流）不重试，立即抛
                    status = getattr(e, "status", None)
                    if (
                        isinstance(e, aiohttp.ClientResponseError)
                        and status is not None
                        and 400 <= status < 500
                        and status not in (408, 429)
                    ):
                        raise AdapterError(
                            message=f"Download failed {url}: HTTP {status} (no retry)",
                            source=self.source.value,
                            status_code=status,
                        ) from e
                    if attempt == retries - 1:
                        raise AdapterError(
                            message=f"Download failed {url}: {e}",
                            source=self.source.value,
                            status_code=status,
                        ) from e
                    await asyncio.sleep(2**attempt)
            raise AdapterError(
                message=f"Download failed {url}: exhausted retries",
                source=self.source.value,
            )

    def _to_github_mirror_url(self, url: str) -> str | None:
        """将 raw.githubusercontent.com URL 转为 jsdelivr 镜像 URL。

        E4：raw.githubusercontent.com 国内 CDN 不稳（偶发 30s 超时），
        jsdelivr 作为兜底镜像。

        转换规则：
            raw.githubusercontent.com/{owner}/{repo}/{ref}/{path...}
            → {github_raw_mirror_base}/{owner}/{repo}@{ref}/{path...}

        Args:
            url: 原始下载 URL

        Returns:
            jsdelivr 镜像 URL；非 raw.githubusercontent.com URL、路径格式不符、
            或镜像基础 URL 配置为空时返回 None（表示不镜像）
        """
        if not self._github_mirror_base:
            return None
        prefix = "https://raw.githubusercontent.com/"
        if not url.startswith(prefix):
            return None
        rest = url[len(prefix) :]
        # owner/repo/ref/path（path 可含子目录，故最多分 4 段）
        parts = rest.split("/", 3)
        if len(parts) < 4:
            return None
        owner, repo, ref, path = parts
        return f"{self._github_mirror_base}/{owner}/{repo}@{ref}/{path}"

    async def _download_xml_with_assets(self, xml_url: str, xml_bytes: bytes) -> dict[str, bytes]:
        """解析 XML 中引用的外部资源（mesh/texture/include）并一并下载。

        数据包自包含（P0-3）：主 XML 下载后，把其引用的相对路径资产（URDF 的
        ``<mesh filename>``/``<texture filename>``、MJCF 的 ``<mesh file>``/
        ``<texture file>``、xacro 的 ``<include filename>``）逐个拉取，使数据包
        可离线完整加载。include 链递归展开：子 XML 的 mesh/texture/include 引用
        同样下载，子 XML 内的相对路径以其所在目录为基准。

        降级策略：XML 解析失败返回空 dict（不抛异常，不阻塞主下载流程）；
        model://、http(s):// 等绝对 URL、xacro 变量（$(...)）与绝对路径（/ 开头）
        不下载；package://<rest> 按相对路径解析（pybullet_robots panda 语义：
        ``package://panda_description/...`` 等价于同仓库目录下，即 rest 直接相对
        于 XML 所在目录）；include 深度超过 _MAX_ASSET_DEPTH 终止展开；
        同一规范化路径只下载一次（去重防环）；单个资产下载失败只跳过该资产。

        Returns:
            规范化相对路径 → 字节 的字典；同一路径重复出现时只下载一次。
        """
        assets: dict[str, bytes] = {}
        try:
            root = ET.fromstring(xml_bytes)
        except Exception:  # noqa: BLE001 — 解析失败按无资产处理
            return assets
        base_dir = posixpath.dirname(xml_url)
        await self._collect_assets(root, base_dir, 0, set(), assets, set())
        return assets

    async def _collect_assets(
        self,
        root: ET.Element,
        base_dir: str,
        depth: int,
        seen: set[str],
        assets: dict[str, bytes],
        skipped: set[str],
        rel_prefix: str = "",
    ) -> None:
        """递归收集 XML 子树中的 mesh/texture/include 引用并下载（内部方法）。

        include 链逐层展开：include 引用的子 XML 也解析其引用，子 XML 内相对
        路径以 ``posixpath.join(base_dir, dirname(include 路径))`` 为下载基准，
        assets 键以 ``rel_prefix`` 拼接为相对主 XML 的完整路径（避免不同目录
        下同名文件互相覆盖）。``seen`` 记录已下载的完整相对路径（去重防环）；
        ``skipped`` 记录深度超限与下载失败的路径（仅作内部记录）。
        """
        if depth > _MAX_ASSET_DEPTH:
            return
        for elem in root.iter():
            # 去掉命名空间前缀（如 {http://...}mesh → mesh）后统一小写匹配
            tag = elem.tag.split("}")[-1].lower()
            if tag not in {"mesh", "texture", "include"}:
                continue
            rel = (elem.get("filename") or elem.get("file") or "").strip()
            if not rel:
                continue
            norm_rel = self._resolve_asset_rel(rel)
            if norm_rel is None:
                continue
            if tag == "include" and depth + 1 > _MAX_ASSET_DEPTH:
                skipped.add(norm_rel)
                continue  # 深度超限：该子 XML 及其引用不再展开（不下载）
            full_rel = posixpath.join(rel_prefix, norm_rel) if rel_prefix else norm_rel
            if full_rel in seen:
                continue  # 同一路径已处理（去重/防环）
            asset_url = posixpath.join(base_dir, norm_rel)
            try:
                content = await self._download_bytes(asset_url)
            except AdapterError:
                skipped.add(norm_rel)
                continue  # 单个资产失败只跳过，不中断整体
            assets[full_rel] = content
            seen.add(full_rel)
            if tag != "include":
                continue
            try:
                sub_root = ET.fromstring(content)
            except Exception:  # noqa: BLE001 — 子 XML 解析失败按无资产处理
                continue
            sub_base = posixpath.join(base_dir, posixpath.dirname(norm_rel))
            sub_prefix = posixpath.join(rel_prefix, posixpath.dirname(norm_rel))
            await self._collect_assets(
                sub_root, sub_base, depth + 1, seen, assets, skipped, sub_prefix
            )

    @staticmethod
    def _resolve_asset_rel(rel: str) -> str | None:
        """把 XML 资源引用解析为规范化相对路径；无法解析时返回 None。

        规则：model://、http(s):// 绝对 URL、xacro 变量（$(...)）与绝对路径
        （/ 开头）不下载；``package://<rest>`` 把 rest 当作相对路径（pybullet_
        robots panda 语义：package://panda_description/... 等价于同仓库目录下的
        panda_description/...）；其余按普通相对路径处理（去前导 ./ 并 normpath）。
        """
        if rel.startswith("package://"):
            rest = rel[len("package://") :]
            if not rest or rest.startswith("/"):
                return None
            norm = posixpath.normpath(rest)
        elif (
            rel.startswith(("model://", "http://", "https://"))
            or "$(" in rel
            or rel.startswith("/")  # 绝对 URL / xacro 变量 / 绝对路径均不下载
        ):
            return None
        else:
            # 规范化相对路径：去前导 ./，normpath 处理 ../
            if rel.startswith("./"):
                rel = rel[2:]
            norm = posixpath.normpath(rel)
        if not norm or norm in (".", ".."):
            return None
        return norm

    async def _head_content_length(self, url: str) -> int | None:
        """通过 HEAD 请求预检文件大小（Content-Length）。

        用于 fetch 下载前的体积预检：若文件超过 ``max_fetch_bytes`` 阈值，
        应返回 metadata JSON 而非下载全量二进制（避免 30s 超时）。

        约定：
        - 任何错误（网络/超时/缺 header/4xx/5xx）均返回 None，
          表示"大小未知"，调用方应回退到正常下载流程。
        - 不重试，单次请求；HEAD 失败不应阻塞主流程。
        - 使用独立的短超时（adapter_timeout），避免与下载超时叠加。

        Args:
            url: 待下载文件的完整 URL

        Returns:
            Content-Length 字节数；不可得时返回 None
        """
        try:
            async with (
                aiohttp.ClientSession() as session,
                session.head(
                    url,
                    timeout=aiohttp.ClientTimeout(total=self.timeout),
                    ssl=_SSL_CONTEXT,
                    allow_redirects=True,
                ) as resp,
            ):
                if resp.status >= 400:
                    return None
                length = resp.headers.get("Content-Length")
                return int(length) if length and length.isdigit() else None
        except (aiohttp.ClientError, TimeoutError, ValueError):
            return None

    @staticmethod
    def _make_cache_key(method: str, path: str, kwargs: dict[str, Any]) -> str:
        """生成缓存键。

        B3 修复：URL query 参数乱序、空值不影响键命中——
        query 解析后按参数名排序、丢弃空值，再重建 URL 参与哈希。
        """
        parts = urlsplit(path)
        query = urlencode(sorted(parse_qsl(parts.query)))
        normalized = urlunsplit(
            (parts.scheme, parts.netloc, parts.path, query, parts.fragment)
        )
        key_str = f"{method}:{normalized}:{sorted(kwargs.items())}"
        return hashlib.md5(key_str.encode()).hexdigest()
