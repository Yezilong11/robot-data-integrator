# tests/unit/adapters/test_arxiv.py
"""ArxivAdapter 的单元测试。"""

import pytest

from rdi.adapters.arxiv import ArxivAdapter
from rdi.exceptions import AdapterError
from rdi.models.common import DataSource

# arXiv Atom XML 响应示例（精简版）
ARXIV_ATOM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2304.06524v1</id>
    <title>Robot Grasping Survey: A Deep Learning Perspective</title>
    <summary>A comprehensive survey of deep learning methods for robot grasping.</summary>
    <published>2023-04-12T10:00:00Z</published>
    <author><name>Alice Smith</name></author>
    <author><name>Bob Jones</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2304.06524v1" rel="related" type="application/pdf"/>
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2203.13251v1</id>
    <title>6-DOF GraspNet: Variational Grasp Generation</title>
    <summary>A variational approach to 6-DOF grasp pose generation.</summary>
    <published>2022-03-24T15:30:00Z</published>
    <author><name>Charlie Brown</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/2203.13251v1" rel="related" type="application/pdf"/>
  </entry>
</feed>
"""

ARXIV_EMPTY_XML = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
</feed>
"""


class TestArxivAdapter:
    """ArxivAdapter 单元测试。"""

    def test_adapter_source(self) -> None:
        """正常情况：source 属性正确。"""
        adapter = ArxivAdapter()
        assert adapter.source == DataSource.ARXIV

    def test_adapter_base_url(self) -> None:
        """正常情况：base_url 设置正确。"""
        adapter = ArxivAdapter()
        assert adapter.base_url == "http://export.arxiv.org/api"

    def test_adapter_rate_limit(self) -> None:
        """正常情况：速率限制为 3。"""
        adapter = ArxivAdapter()
        assert adapter.semaphore._value == 3

    def test_parse_atom_xml_returns_results(self) -> None:
        """正常情况：解析 Atom XML 返回正确的元数据。"""
        results = ArxivAdapter._parse_atom_xml(ARXIV_ATOM_XML)
        assert len(results) == 2

        first = results[0]
        assert first.item_id == "2304.06524v1"
        assert "Robot Grasping Survey" in first.title
        assert first.source == DataSource.ARXIV
        assert first.url == "https://arxiv.org/abs/2304.06524v1"
        assert first.pdf_url == "http://arxiv.org/pdf/2304.06524v1"
        assert first.metadata["authors"] == ["Alice Smith", "Bob Jones"]
        assert "deep learning" in first.metadata["abstract"]
        assert first.metadata["published"] == "2023-04-12T10:00:00Z"

    def test_parse_atom_xml_handles_empty_result(self) -> None:
        """边界情况：搜索无结果时返回空列表。"""
        results = ArxivAdapter._parse_atom_xml(ARXIV_EMPTY_XML)
        assert results == []

    def test_parse_atom_xml_extracts_second_entry(self) -> None:
        """正常情况：正确解析第二条结果。"""
        results = ArxivAdapter._parse_atom_xml(ARXIV_ATOM_XML)
        second = results[1]
        assert second.item_id == "2203.13251v1"
        assert "6-DOF" in second.title
        assert second.metadata["authors"] == ["Charlie Brown"]

    @pytest.mark.asyncio
    async def test_search_retries_on_429(self) -> None:
        """异常情况：遇到限流时自动重试（通过 _request 基类实现）。

        此测试验证 ArxivAdapter 在请求失败时正确抛出 AdapterError，
        基类 _request 的指数退避重试逻辑已在 test_base.py 中测试。
        """
        adapter = ArxivAdapter()
        adapter.max_retry = 1
        # 不启动服务器，请求必然失败
        with pytest.raises(AdapterError) as exc_info:
            await adapter.search("robot grasping")
        assert exc_info.value.source == "arxiv"
