# tests/unit/hermes/test_experience_db.py
"""ExperienceDB 单元测试。

使用 tmp_path 创建临时 ChromaDB，mock embed_fn 返回固定向量，覆盖经验存取、
反馈写入、数据源统计累加。
"""

from pathlib import Path

from rdi.hermes.experience_db import ExperienceDB


def make_db(tmp_path: Path) -> ExperienceDB:
    """构造测试用 ExperienceDB，使用临时路径 + 固定向量 embed_fn。"""
    return ExperienceDB(
        db_path=str(tmp_path / "test_db"),
        embed_fn=lambda text: [0.1] * 10,
    )


def test_store_and_retrieve_experience(tmp_path: Path) -> None:
    """存入一条经验后，retrieve_similar_experiences 能检索到。"""
    db = make_db(tmp_path)
    db.store_experience(
        task_desc="抓取杯子实验",
        req_type="grasping",
        result_status="success",
        sources_used=["github", "ieee"],
        elapsed_seconds=12.5,
    )
    results = db.retrieve_similar_experiences("抓取杯子", top_k=3)
    assert len(results) == 1
    item = results[0]
    assert item["task_desc"] == "抓取杯子实验"
    assert item["req_type"] == "grasping"
    assert item["result_status"] == "success"
    assert item["sources_used"] == ["github", "ieee"]
    assert item["elapsed_seconds"] == 12.5
    assert item["document"] == "抓取杯子实验"


def test_update_source_stats_accumulates(tmp_path: Path) -> None:
    """连续 update 两次：success=True 然后 success=False，验证 req_type 与全局维度各自累加。"""
    db = make_db(tmp_path)
    db.update_source_stats(source="github", req_type="code", success=True, elapsed_seconds=10.0)
    db.update_source_stats(source="github", req_type="code", success=False, elapsed_seconds=20.0)
    # 全局维度（req_type="*"）与 req_type 维度独立累加
    for dim in ("*", "code"):
        stats = db.get_source_stats(req_type=dim)
        assert len(stats) == 1
        stat = stats[0]
        assert stat["source_name"] == "github"
        assert stat["req_type"] == dim
        assert stat["total_requests"] == 2
        assert stat["success_count"] == 1
        # avg = (10*1 + 20) / 2 = 15.0
        assert stat["avg_elapsed"] == 15.0


def test_update_source_stats_separates_by_req_type(tmp_path: Path) -> None:
    """同一源在不同 req_type 下的统计互不影响，且都能过滤查询。"""
    db = make_db(tmp_path)
    db.update_source_stats(source="github", req_type="code", success=True, elapsed_seconds=1.0)
    db.update_source_stats(source="github", req_type="dataset", success=False, elapsed_seconds=2.0)
    code = db.get_source_stats(source_name="github", req_type="code")
    dataset = db.get_source_stats(source_name="github", req_type="dataset")
    assert len(code) == 1
    assert code[0]["total_requests"] == 1
    assert code[0]["success_count"] == 1
    assert len(dataset) == 1
    assert dataset[0]["total_requests"] == 1
    assert dataset[0]["success_count"] == 0


def test_store_feedback_writes_correctly(tmp_path: Path) -> None:
    """存入反馈后，db._feedback.get() 能读到对应元数据。"""
    db = make_db(tmp_path)
    db.store_feedback(
        task_desc="抓取杯子实验",
        feedback_type="correction",
        feedback_content="数据源应该用 ieee",
        corrected_value="ieee",
    )
    result = db._feedback.get(include=["metadatas"])
    metadatas = result.get("metadatas") or []
    assert len(metadatas) == 1
    meta = metadatas[0]
    assert meta["task_desc"] == "抓取杯子实验"
    assert meta["feedback_type"] == "correction"
    assert meta["feedback_content"] == "数据源应该用 ieee"
    assert meta["corrected_value"] == "ieee"
