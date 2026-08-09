# src/rdi/adapters/robotiq.py
"""Robotiq 夹爪 URDF 模型源 Adapter。

文档原始对接方式：网页抓取（BeautifulSoup 解析 robotiq.com 网页）
降级回退方式：GitHub raw URL（ros-industrial/robotiq 仓库）直接下载
无需 API Key，直接 HTTP 下载。
"""

from rdi.adapters.base import BaseAdapter
from rdi.config.settings import settings
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource
from rdi.models.retrieval import RawData, SearchResult

# 降级回退：Robotiq 夹爪已知型号（C8 修复：id 对应 ros-industrial-attic/robotiq 实际路径）
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
            return await self._search_primary(query)
        except AdapterError:
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
        return results

    async def _search_fallback(self, query: str) -> list[SearchResult]:
        """路径 B：硬编码列表降级回退。无匹配时返回空列表。"""
        query_lower = query.lower()
        matched = [
            m
            for m in _FALLBACK_MODELS
            if query_lower in m["id"].lower()
            or query_lower in m["title"].lower()
            or query_lower in m["description"].lower()
        ]
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
        """下载 URDF 文件。优先 robotiq.com，失败降级 GitHub raw URL。"""
        try:
            return await self._fetch_primary(item_id)
        except AdapterError:
            return await self._fetch_fallback(item_id)

    async def _fetch_primary(self, item_id: str) -> RawData:
        """路径 A：直接 URL 构造（官方页面路径模式）。"""
        url = f"{self._web_url}/products/{item_id}/{item_id}.urdf"
        content = await self._download_bytes(url)
        return RawData(
            source=DataSource.ROBOTIQ,
            item_id=item_id,
            format="urdf",
            data=content,
            url=url,
            size_bytes=len(content),
        )

    async def _fetch_fallback(self, item_id: str) -> RawData:
        """路径 B：GitHub raw URL 降级回退。

        C8 修复：ros-industrial/robotiq 已迁至 ros-industrial-attic/robotiq，
        且文件路径不是 robotiq_description/urdf/{id}.urdf，而是按型号分散在
        {id}_gripper_visualization/urdf/ 下。使用 _FETCH_PATHS 映射表查实际路径。
        """
        rel_path = _FETCH_PATHS.get(item_id)
        if not rel_path:
            raise AdapterError(
                message=f"Unknown robotiq model: {item_id} (no path mapping)",
                source=self.source.value,
            )
        urdf_url = f"{self.base_url}/{rel_path}"
        content = await self._download_bytes(urdf_url)
        return RawData(
            source=DataSource.ROBOTIQ,
            item_id=item_id,
            format="urdf",
            data=content,
            url=urdf_url,
            size_bytes=len(content),
        )
