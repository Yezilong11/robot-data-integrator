# src/rdi/adapters/robotiq.py
"""Robotiq 夹爪 URDF 模型源 Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 robotiq.com 网页）
降级回退方式：GitHub raw URL（ros-industrial/robotiq 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

import asyncio
import re
from typing import Any

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterCatalogError, AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Robotiq 夹爪已知型号（C8 修复：id 对应 ros-industrial-attic/robotiq 实际路径）
# D3 修复：robotiq.com 主路径（网页抓取 + 直接 URDF 下载）在本环境不可达且可能挂起，
# 用短超时快速放弃转 fallback（GitHub/jsdelivr），避免吃掉 15s 源级预算（P2_RETRIEVE 根因）。
_PRIMARY_FAST_TIMEOUT_S = 3.0
_FALLBACK_MODELS: list[dict[str, str]] = [
    {"id": "robotiq_2f_85", "title": "Robotiq 2F-85", "description": "Robotiq 2 指夹爪 85mm 行程"},
    {
        "id": "robotiq_2f_140",
        "title": "Robotiq 2F-140",
        "description": "Robotiq 2 指夹爪 140mm 行程",
    },
    {
        "id": "robotiq_3f_gripper",
        "title": "Robotiq 3F-Gripper",
        "description": "Robotiq 3 指自适应夹爪",
    },
    {"id": "robotiq_ft_sensor", "title": "Robotiq FT Sensor", "description": "Robotiq 力矩传感器"},
]

# C8 修复：item_id → ros-industrial-attic/robotiq 仓库 kinetic-devel 分支实际文件路径
# （已 curl 验证：2f_85/2f_140 是 .xacro，3f_gripper 有 .urdf）
_FETCH_PATHS: dict[str, str] = {
    "robotiq_2f_85": "robotiq_2f_85_gripper_visualization/urdf/robotiq_arg2f_85_model.xacro",
    "robotiq_2f_140": "robotiq_2f_140_gripper_visualization/urdf/robotiq_arg2f_140_model.xacro",
    "robotiq_3f_gripper": "robotiq_3f_gripper_visualization/cfg/robotiq-3f-gripper_articulated.urdf",
    "robotiq_ft_sensor": "robotiq_ft_sensor/urdf/robotiq_ft300.urdf.xacro",
}

# ─── xacro 轻量展开器（D3 修复） ───
# robotiq 2f_85/2f_140 的 model.xacro 是纯包装（include + 宏调用），实体宏定义在
# *_model_macro.xacro / robotiq_arg2f.xacro / robotiq_arg2f_transmission.xacro 中。
# 本环境无 ROS xacro 模块，assemble 把包装 xacro 原样落盘为 .urdf 得到
# 0 links/0 joints 空壳（P4_FORMAT）。此展开器在 adapter 层完成 include 内联 +
# 宏调用展开 + ${expr} 求值，产出可直接解析的纯 URDF（format="urdf"）。
_XACRO_INCLUDE_RE = re.compile(r"<xacro:include\s+([^>]*?)/>", re.S)
_XACRO_MACRO_DEF_RE = re.compile(
    r'<xacro:macro\s+name="([^"]+)"\s+params="([^"]*)"[^>]*>(.*?)</xacro:macro>', re.S
)
_XACRO_CALL_RE = re.compile(r"<xacro:(\w+)\s+([^>]*?)/>", re.S)
_XACRO_COND_RE = re.compile(r"<xacro:(if|unless)[^>]*>.*?</xacro:\1>", re.S)
_XACRO_FIND_RE = re.compile(r"\$\(find\s+([^)\s]+)")
_XACRO_VAR_RE = re.compile(r"\$\{([^}]+)\}")
_MAX_INCLUDE_DEPTH = 8
_MAX_EXPAND_ROUNDS = 20


def _strip_xml_wrapper(snippet: str) -> str:
    """剥离被 include 子文件的 XML 声明与根标签，只保留内部内容。

    xacro include 的文件常以 ``<?xml?>`` 声明 + ``<robot>`` 根包裹，直接内联
    会产生多个 ``<?xml?>`` 与嵌套 ``<robot>``，导致最终文档非法。
    """
    snippet = re.sub(r"<\?xml[^>]*\?>", "", snippet)
    snippet = re.sub(r"<robot\b[^>]*>", "", snippet, count=1)
    snippet = re.sub(r"</robot\s*>", "", snippet, count=1)
    return snippet


def _parse_xacro_attrs(attrs_str: str) -> dict[str, str]:
    return dict(re.findall(r'([\w-]+)="([^"]*)"', attrs_str))


def _resolve_xacro_include(filename: str) -> str:
    """把 ``$(find pkg)/rest`` 解析为仓库相对路径。

    D3 修复：仓库根即多包集合（robotiq_2f_85_gripper_visualization/ 等），
    ``$(find pkg)`` 的包名必须保留为路径首段，否则 include 解析成
    ``urdf/...`` 会 404（此前 P4_FORMAT 空壳根因）。
    """
    m = _XACRO_FIND_RE.search(filename)
    if m:
        pkg = m.group(1)
        rest = filename[m.end() :].lstrip(")").lstrip("/")
        return f"{pkg}/{rest}" if rest else pkg
    return filename.lstrip("/")


def _eval_xacro_expr(expr: str, scope: dict[str, str] | None = None) -> str:
    """安全求值 xacro 表达式（数字四则/括号/pi 等常量，ast 白名单）。

    scope 提供宏参数名→实参值：求值前先把参数名按整词替换为实参值，
    使 ``${reflect * -0.0127}`` 这类「宏参数参与运算」的表达式可正确展开
    （此前 ast 白名单不含宏参数，参数代入返回空串 → <origin> xyz/rpy
    退化为 2 个数值 → yourdfpy 解析失败 P4_FORMAT）。
    """
    import ast
    import math

    allowed = {"pi": math.pi, "radians": math.radians, "sin": math.sin, "cos": math.cos}
    for name, val in (scope or {}).items():
        expr = re.sub(rf"\b{re.escape(name)}\b", str(val), expr)

    def _ev(node: Any) -> float:
        if isinstance(node, ast.Expression):
            return _ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
            return float(node.value)
        if isinstance(node, ast.Name) and node.id in allowed:
            return allowed[node.id]
        if isinstance(node, ast.UnaryOp):
            v = _ev(node.operand)
            return v if isinstance(node.op, ast.UAdd) else -v
        if isinstance(node, ast.BinOp):
            a, b = _ev(node.left), _ev(node.right)
            if isinstance(node.op, ast.Add):
                return a + b
            if isinstance(node.op, ast.Sub):
                return a - b
            if isinstance(node.op, ast.Mult):
                return a * b
            if isinstance(node.op, ast.Div):
                return a / b
        raise ValueError(f"unsupported xacro expr: {expr}")

    try:
        val = _ev(ast.parse(expr, mode="eval"))
        return f"{val:g}" if isinstance(val, float) else str(val)
    except Exception:
        return ""


def _expand_xacro(text: str, load_include: Any) -> str:
    """轻量 xacro 展开：include 内联 → 宏定义收集 → 递归宏调用展开 → 表达式求值。

    Args:
        text: xacro 文本
        load_include: ``(仓库相对路径) -> str | None`` 的同步 loader（include 内容）
    """
    # 1. include 内联（限深，失败则移除该 include 标签）
    for _ in range(_MAX_INCLUDE_DEPTH):
        m = _XACRO_INCLUDE_RE.search(text)
        if not m:
            break
        rel = _resolve_xacro_include(_parse_xacro_attrs(m.group(1)).get("filename", ""))
        content = load_include(rel) if rel else None
        text = text[: m.start()] + (_strip_xml_wrapper(content) if content else "") + text[m.end() :]
    # 2. 提取宏定义并移除定义块（宏体展开到调用位置）
    macros: dict[str, tuple[str, str]] = {}
    for name, params, body in _XACRO_MACRO_DEF_RE.findall(text):
        macros[name] = (params, body)
    text = _XACRO_MACRO_DEF_RE.sub("", text)
    # 3. 递归展开宏调用（嵌套调用在展开中产生，循环直至稳定）
    for _ in range(_MAX_EXPAND_ROUNDS):
        changed = False

        def repl(m: Any) -> str:
            nonlocal changed
            name, attrs_str = m.group(1), m.group(2)
            entry = macros.get(name)
            if entry is None:
                return m.group(0)
            params, body = entry
            args = _parse_xacro_attrs(attrs_str)
            evaled = {
                k: _XACRO_VAR_RE.sub(lambda mm: _eval_xacro_expr(mm.group(1).strip()), v)
                for k, v in args.items()
            }
            scope = {p.strip(): evaled.get(p.strip(), "") for p in params.split() if p.strip()}
            out = body
            # 参数替换可嵌套（值本身含 ${param}），多轮直至稳定
            for _ in range(5):
                nxt = _XACRO_VAR_RE.sub(lambda mm: scope.get(mm.group(1).strip(), mm.group(0)), out)
                if nxt == out:
                    break
                out = nxt
            out = _XACRO_VAR_RE.sub(lambda mm: _eval_xacro_expr(mm.group(1).strip(), scope), out)
            changed = True
            return out

        text = _XACRO_CALL_RE.sub(repl, text)
        if not changed:
            break
    # 4. 清理残留 xacro 元素/命名空间
    text = _XACRO_COND_RE.sub("", text)
    text = re.sub(r"<xacro:[^>]*/>", "", text)
    text = re.sub(r'xmlns:xacro=["\'][^"\']*["\']', "", text)
    return text


def _looks_like_urdf(content: bytes) -> bool:
    """粗略判断字节内容是否为 URDF/XML 实体（而非 HTML 营销页面）。"""
    head = content[:4096]
    stripped = head.lstrip()
    return (
        stripped.startswith(b"<?xml")
        or stripped.startswith(b"<robot")
        or b"<link" in stripped
        or b"<joint" in stripped
    )


class RobotiqAdapter(BaseAdapter):
    """Robotiq 夹爪 Adapter。

    对接方式（双路径）：
    - 路径 A（优先）：网页抓取 — BeautifulSoup 解析 robotiq.com 获取 URDF 链接
    - 路径 B（降级）：GitHub raw URL 下载
    """

    source = DataSource.ROBOTIQ

    def __init__(self) -> None:
        super().__init__(
            base_url=settings.robotiq_base_url,
            rate_limit=5,
        )
        self._web_url = settings.robotiq_web_url

    async def search(self, query: str) -> list[SearchResult]:
        """搜索 Robotiq 夹爪模型。优先网页抓取，失败降级硬编码列表。"""
        try:
            async with asyncio.timeout(_PRIMARY_FAST_TIMEOUT_S):
                return await self._search_primary(query)
        except (AdapterError, TimeoutError):
            return await self._search_fallback(query)

    async def _search_primary(self, query: str) -> list[SearchResult]:
        """路径 A：网页抓取方式（文档原始对接方式）— 解析 robotiq.com 网页。"""
        url = f"{self._web_url}/products"
        soup = await self._scrape_html(url)
        results: list[SearchResult] = []
        # 解析页面中的夹爪型号链接
        for link in soup.select("a[href*='gripper'], a[href*='2f'], a[href*='urdf']"):
            model_id = self._attr_str(link, "href").rstrip("/").split("/")[-1]
            if not model_id:
                continue
            title = link.get_text(strip=True) or model_id
            query_lower = query.lower()
            if query_lower in model_id.lower() or query_lower in title.lower():
                results.append(
                    SearchResult(
                        item_id=model_id,
                        title=title,
                        source=DataSource.ROBOTIQ,
                        url=f"{self._web_url}/products/{model_id}",
                        metadata={"description": title},
                    )
                )
        if not results:
            raise AdapterError(
                message=f"Web scraping returned no models for: {query}",
                source=self.source.value,
            )
        # D3 修复：robotiq.com 抓到的链接多为新闻/博客页（slug 不在 _FETCH_PATHS），
        # 若原样返回，fetch 会因无路径映射失败。只保留已知可下载模型；一个都不剩
        # 则按"主路径无结果"抛 AdapterError，走硬编码 fallback 列表。
        fetchable = [r for r in results if r.item_id in _FETCH_PATHS]
        if not fetchable:
            raise AdapterError(
                message=f"Web scraping returned no fetchable models for: {query}",
                source=self.source.value,
            )
        return fetchable

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时抛 AdapterCatalogError（而非返回空）。

        D3 修复：口语化 query（"Robotiq 夹爪"）整串无法命中硬编码 id/title，
        此前被判定为"未收录"直接跳过源（ss_robotiq_003 P2_RETRIEVE）。
        改为 token 级匹配：query 与已知模型任一字段的词元有交集即视为命中。
        """
        query_lower = query.lower()
        query_tokens = {t for t in re.findall(r"[a-z0-9]+", query_lower) if len(t) >= 3}
        matched = [
            m
            for m in _FALLBACK_MODELS
            if query_lower in m["id"].lower()
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
            or query_tokens & set(re.findall(r"[a-z0-9]+", f"{m['id']} {m['title']} {m['description']}".lower()))
        ]
        if not matched:
            raise AdapterCatalogError(
                message=(
                    f"该源仅收录 {len(_FALLBACK_MODELS)} 个已知目标，"
                    f"未收录 '{query}'（有源但未收录）"
                ),
                source=self.source.value,
            )
        return [
            SearchResult(
                item_id=m["id"],
                title=m["title"],
                source=DataSource.ROBOTIQ,
                url=f"{self.base_url}/robotiq_description/urdf/{m['id']}",
                metadata={"description": m["description"]},
            )
            for m in matched
        ]

    async def fetch(self, item_id: str) -> RawData:
        """下载 URDF 文件。优先 robotiq.com，失败降级 GitHub raw URL。

        D3：本地数据集挂载优先——命中本地文件直接返回（不发任何网络请求）。
        """
        # D3: 本地挂载目录即 ros-industrial-attic/robotiq 仓库根镜像，相对路径即 _FETCH_PATHS
        local = self._local_raw(item_id, self._local_candidates(item_id))
        if local is not None:
            return local
        try:
            async with asyncio.timeout(_PRIMARY_FAST_TIMEOUT_S):
                return await self._fetch_primary(item_id)
        except (AdapterError, TimeoutError):
            return await self._fetch_fallback(item_id)

    def _local_candidates(self, item_id: str) -> list[tuple[str, str]]:
        """本地挂载候选 (仓库相对路径, format)，与 _fetch_fallback 的 URL 路径同构。"""
        rel_path = _FETCH_PATHS.get(item_id)
        if not rel_path:
            return []
        fmt = "urdf" if rel_path.endswith(".urdf") else "xacro"
        return [(rel_path, fmt)]

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方页面路径模式）。

        D3 修复：robotiq.com 对 ``{id}.urdf`` 路径常返回 HTML 营销页面（200），
        下载成功但内容非 URDF，被 C4 类型错配拦截为 markdown。下载后校验内容
        是否含 URDF 实体（<robot>/<link>），否则抛 AdapterError 走 GitHub fallback。
        """
        url = f"{self._web_url}/products/{item_id}/{item_id}.urdf"
        content = await self._download_bytes(url)
        if not _looks_like_urdf(content):
            raise AdapterError(
                message=f"robotiq.com 返回内容非 URDF（可能为 HTML 页面）: {url}",
                source=self.source.value,
            )
        assets = await self._download_xml_with_assets(url, content)
        return RawData(
            source=DataSource.ROBOTIQ,
            item_id=item_id,
            format="urdf",
            data=content,
            url=url,
            size_bytes=len(content),
            assets=assets,
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：GitHub raw URL 降级回退。

        C8 修复：ros-industrial/robotiq 已迁至 ros-industrial-attic/robotiq，
        且文件路径不是 robotiq_description/urdf/{id}.urdf，而是按型号分散在
        {id}_gripper_visualization/urdf/ 下。使用 _FETCH_PATHS 映射表查实际路径。

        C2 修复：根据实际文件扩展名标记 format；xacro 文件明确返回 format="xacro"，
        便于 URDFSkill 做 xacro 兜底。

        D3 修复：xacro 包装文件在此直接内联展开为纯 URDF（下载 include 宏定义 +
        mesh 资产），不再把空壳 xacro 交给 assemble 落盘。
        """
        rel_path = _FETCH_PATHS.get(item_id)
        if not rel_path:
            raise AdapterError(
                message=f"Unknown robotiq model: {item_id} (no path mapping)",
                source=self.source.value,
            )
        urdf_url = f"{self.base_url}/{rel_path}"
        content = await self._download_bytes(urdf_url)
        fmt = "urdf" if rel_path.endswith(".urdf") else "xacro"
        if fmt == "xacro":
            try:
                expanded, assets = await self._expand_xacro_content(item_id, rel_path, content)
                fmt = "urdf"
                content = expanded
            except Exception:
                # 展开失败保持 xacro 原样，URDFSkill 字符串级清理兜底
                assets = await self._download_xml_with_assets(urdf_url, content)
        else:
            assets = await self._download_xml_with_assets(urdf_url, content)
        return RawData(
            source=DataSource.ROBOTIQ,
            item_id=item_id,
            format=fmt,
            data=content,
            url=urdf_url,
            size_bytes=len(content),
            assets=assets,
        )

    async def _expand_xacro_content(
        self, item_id: str, rel_path: str, content: bytes
    ) -> tuple[bytes, dict[str, bytes]]:
        """下载 include 链 → 内联展开宏 → 下载引用的 mesh 资产 → (纯URDF, assets)。

        mesh 引用 ``package://{pkg}/meshes/...`` 改写为相对路径（与资产键一致），
        便于 assemble 落盘后 URDF 按相对路径加载。
        """
        pkg = rel_path.split("/")[0]
        # 预收集 include 链（递归，带环保护）。D3 修复：原顺序下载在 CDN 冷启动时
        # 3~5 个 include 文件即可吃掉 15s 源级预算（P2_RETRIEVE）；改为逐层并发下载。
        includes: dict[str, str] = {}
        pending = [rel_path]
        seen: set[str] = set()
        while pending:
            batch = [rel for rel in pending if rel not in seen]
            seen.update(batch)
            results = await asyncio.gather(
                *(self._download_bytes(f"{self.base_url}/{rel}") for rel in batch),
                return_exceptions=True,
            )
            pending = []
            for rel, raw in zip(batch, results, strict=False):
                if isinstance(raw, BaseException):
                    continue
                snippet = raw.decode("utf-8", errors="replace")
                includes[rel] = snippet
                for m in _XACRO_INCLUDE_RE.finditer(snippet):
                    inc_rel = _resolve_xacro_include(
                        _parse_xacro_attrs(m.group(1)).get("filename", "")
                    )
                    if inc_rel and inc_rel not in seen:
                        pending.append(inc_rel)
        # 同步展开（loader 从预下载集合取 include 内容）
        expanded = _expand_xacro(content.decode("utf-8", errors="replace"), includes.get)
        # package://pkg/meshes/... → meshes/...（相对主 XML 所在包根，资产键同构）
        expanded = expanded.replace(f"package://{pkg}/", "")
        # 下载 mesh/texture 资产：仓库根即多包集合，资产实际位于 {pkg}/{ref} 下。
        # 并发下载（D3 修复：顺序下载在 raw github 挂起时 10 个资产可拖到 70s，
        # 超过 15s 源级预算导致 P2_RETRIEVE；单个失败只跳过该资产）。
        assets: dict[str, bytes] = {}
        refs: set[str] = set(re.findall(r'<mesh\s+filename="([^"]+)"', expanded))
        refs |= set(re.findall(r'<texture\s+filename="([^"]+)"', expanded))
        urls = {ref: f"{self.base_url}/{pkg}/{ref}" for ref in refs
                if not (ref.startswith(("http://", "https://", "package://", "/")) or "$(" in ref)}
        contents = await asyncio.gather(
            *(self._download_bytes(u) for u in urls.values()),
            return_exceptions=True,
        )
        for ref, content in zip(urls, contents, strict=False):
            if isinstance(content, BaseException):
                continue
            assets[ref] = content
        return expanded.encode("utf-8"), assets
