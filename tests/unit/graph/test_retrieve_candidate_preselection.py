"""_pick_semantic_candidate 检索候选语义预筛的单元测试。

纯函数直测四条路径：命中术语选对应候选、全零重叠保留首个并带诊断、
非启用类型跳过、术语为空跳过。
"""

from types import SimpleNamespace

from rdi.graph.nodes.retrieve_data import _pick_semantic_candidate
from rdi.models.common import DataSource
from rdi.models.retrieval import SearchResult


def _result(item_id: str, title: str, *, desc: str | None = None) -> SearchResult:
    return SearchResult(
        item_id=item_id,
        title=title,
        source=DataSource.GITHUB,
        metadata={"description": desc} if desc is not None else {},
    )


def _req(
    *, description: str = "", keywords: list[str] | None = None, object_name: str = ""
) -> SimpleNamespace:
    return SimpleNamespace(
        description=description, keywords=keywords or [], object_name=object_name
    )


def test_picks_candidate_matching_semantic_term() -> None:
    """第 2 个候选 title/desc 含 banana、第 1 个无关 → 选第 2 个且无诊断。"""
    results = [
        _result("unrelated", "Unrelated Dataset", desc="random robot data"),
        _result("banana-1", "Banana Grasp Annotations", desc="banana grasp labels for YCB"),
    ]
    req = _req(description="banana 的抓取标注", keywords=["banana"], object_name="banana")

    picked, diag = _pick_semantic_candidate(results, "grasp", req)

    assert picked is results[1]
    assert diag is None


def test_picks_beyond_top5_when_front_zero_overlap() -> None:
    """fix4：前 5 个候选零重叠、第 6 个命中需求词 → 不再维持首个，选命中候选。

    此前仅扫描 search_results[:5]，真实排名靠后的 IMU/关节记录（如
    ss_sensor_zenodo_001 的 "Lower-body Inertial Sensor..."）被丢弃，
    转而 fetch 首个无关候选（Boxing punch data）被装配期语义校验拦截成 FAIL。
    """
    results = [_result(f"noise-{i}", f"Unrelated {i}", desc="foo bar baz") for i in range(5)]
    results.append(_result("imu-1", "Lower-body Inertial Sensor Record", desc="imu inertial data"))
    req = _req(description="惯性测量单元数据", keywords=["inertial measurement unit"])

    picked, diag = _pick_semantic_candidate(results, "sensor_data", req)

    assert picked is results[5]
    assert diag is None


def test_zero_overlap_skips_with_diagnostic() -> None:
    """全部候选零重叠 → 返回 None（调用方跳过本源），诊断含「语义零重叠」。"""
    results = [
        _result("a-1", "Alpha", desc="foo bar"),
        _result("b-1", "Beta", desc="baz qux"),
    ]
    req = _req(description="banana 的抓取标注", keywords=["banana"])

    picked, diag = _pick_semantic_candidate(results, "grasp", req)

    assert picked is None
    assert diag is not None
    assert "语义零重叠" in diag
    assert results[0].title in diag


def test_non_semantic_type_keeps_first_without_diagnostic() -> None:
    """非启用类型（PAPER）→ 选索引 0 且无诊断，即使候选含 banana。"""
    results = [
        _result("p-1", "Banana Grasp Paper", desc="banana grasp survey"),
    ]
    req = _req(description="banana 的抓取标注", keywords=["banana"])

    picked, diag = _pick_semantic_candidate(results, "paper", req)

    assert picked is results[0]
    assert diag is None


def test_empty_terms_keeps_first_without_diagnostic() -> None:
    """术语为空（泛词被 stopwords 过滤）→ 选索引 0 且无诊断。"""
    results = [
        _result("m-1", "Model", desc="robot data"),
    ]
    req = _req(description="获取机器人模型文件", keywords=["robot"])

    picked, diag = _pick_semantic_candidate(results, "mesh", req)

    assert picked is results[0]
    assert diag is None
