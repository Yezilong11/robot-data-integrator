# src/rdi/hermes/experience_db.py
"""Hermes 经验库：基于 ChromaDB 的经验持久化。"""

# mypy: ignore-errors
# ChromaDB 类型存根与实际行为不一致（metadata 值类型为宽联合，add/upsert 对
# embeddable 字段的约束等），整文件忽略 mypy 以避免大量伪错误。

import datetime
import uuid
from collections.abc import Callable
from typing import Any

import chromadb

from rdi.config import settings
from rdi.intelligence.embedding import get_embedding

# 全局统计维度的 req_type 占位符：source_stats 中 req_type="*" 表示跨需求类型的全局统计
GLOBAL_REQ_TYPE = "*"


class ExperienceDB:
    """经验库，使用 ChromaDB 存储经验、反馈和数据源统计。"""

    def __init__(
        self,
        db_path: str | None = None,
        embed_fn: Callable[[str], list[float]] | None = None,
    ) -> None:
        """初始化经验库。

        Args:
            db_path: ChromaDB 持久化路径，默认取 settings.chromadb_path
            embed_fn: Embedding 函数，默认取 get_embedding
        """
        self._db_path = db_path or settings.chromadb_path
        self._embed_fn = embed_fn or get_embedding
        self._client = chromadb.PersistentClient(path=self._db_path)
        self._experience = self._client.get_or_create_collection("experience")
        self._feedback = self._client.get_or_create_collection("feedback")
        self._source_stats = self._client.get_or_create_collection("source_stats")

    def store_experience(
        self,
        task_desc: str,
        req_type: str,
        result_status: str,
        sources_used: list[str],
        elapsed_seconds: float,
        user_feedback: str = "",
    ) -> None:
        """存储一次任务经验，含任务描述、结果与耗时。"""
        embedding = self._embed_fn(task_desc)
        exp_id = str(uuid.uuid4())
        metadata = {
            "task_desc": task_desc,
            "req_type": req_type,
            "result_status": result_status,
            "sources_used": ",".join(sources_used),
            "elapsed_seconds": str(elapsed_seconds),
            "user_feedback": user_feedback,
            "created_at": datetime.datetime.now().isoformat(),
        }
        self._experience.add(
            ids=[exp_id],
            embeddings=[embedding],
            metadatas=[metadata],
            documents=[task_desc],
        )

    def retrieve_similar_experiences(
        self,
        task_desc: str,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """检索与 task_desc 最相似的历史经验，返回元数据列表。

        空集合或无结果时返回空列表；sources_used 从逗号分隔字符串还原为 list，
        elapsed_seconds 还原为 float，同时附带 document（原始 task_desc）。
        """
        embedding = self._embed_fn(task_desc)
        results = self._experience.query(query_embeddings=[embedding], n_results=top_k)
        metadatas = results.get("metadatas") or []
        # ChromaDB 空结果：metadatas 为 [] 或 [[]]
        if not metadatas or not metadatas[0]:
            return []
        documents = (results.get("documents") or [[]])[0]
        out: list[dict[str, Any]] = []
        for i, meta in enumerate(metadatas[0]):
            sources = meta.get("sources_used", "") if meta else ""
            out.append(
                {
                    "task_desc": meta.get("task_desc", "") if meta else "",
                    "req_type": meta.get("req_type", "") if meta else "",
                    "result_status": meta.get("result_status", "") if meta else "",
                    "sources_used": sources.split(",") if sources else [],
                    "elapsed_seconds": float(
                        (meta.get("elapsed_seconds", "0") if meta else "0") or "0"
                    ),
                    "document": documents[i] if i < len(documents) else "",
                }
            )
        return out

    def store_feedback(
        self,
        task_desc: str,
        feedback_type: str,
        feedback_content: str,
        corrected_value: str = "",
    ) -> None:
        """存储用户反馈（不带向量，feedback collection 仅按元数据查询）。"""
        fb_id = str(uuid.uuid4())
        metadata = {
            "task_desc": task_desc,
            "feedback_type": feedback_type,
            "feedback_content": feedback_content,
            "corrected_value": corrected_value,
            "created_at": datetime.datetime.now().isoformat(),
        }
        # ponytail: 用 [0.0] 占位向量满足 ChromaDB 对 embeddable 字段的强制要求，
        # feedback 仅按元数据查询，向量本身无意义。
        self._feedback.add(ids=[fb_id], embeddings=[[0.0]], metadatas=[metadata])

    def get_source_stats(
        self,
        source_name: str | None = None,
        req_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """返回数据源统计记录，可按 source_name / req_type 过滤。

        req_type="*"（即 GLOBAL_REQ_TYPE）表示全局统计维度；
        不传任何参数时返回全部（全局 + 各 req_type）记录。
        """
        where: dict[str, Any] = {}
        conditions: list[dict[str, str]] = []
        if source_name is not None:
            conditions.append({"source_name": source_name})
        if req_type is not None:
            conditions.append({"req_type": req_type})
        if conditions:
            # ChromaDB where 顶层仅允许单个条件，多条件需用 $and
            where = conditions[0] if len(conditions) == 1 else {"$and": conditions}
            results = self._source_stats.get(include=["metadatas"], where=where)
        else:
            results = self._source_stats.get(include=["metadatas"])
        metadatas = results.get("metadatas") or []
        out: list[dict[str, Any]] = []
        for meta in metadatas:
            if meta is None:
                continue
            out.append(
                {
                    "source_name": meta.get("source_name", ""),
                    # 兼容旧格式记录（无 req_type 字段）：视为全局统计
                    "req_type": meta.get("req_type", GLOBAL_REQ_TYPE),
                    "total_requests": int(meta.get("total_requests", 0)),
                    "success_count": int(meta.get("success_count", 0)),
                    "avg_elapsed": float(meta.get("avg_elapsed", 0.0)),
                    "last_updated": meta.get("last_updated", ""),
                }
            )
        return out

    def update_source_stats(
        self,
        source: str,
        req_type: str,
        success: bool,
        elapsed_seconds: float,
    ) -> None:
        """累加更新某数据源在 req_type 维度的统计，并同时累计全局（"*"）统计。

        统计键为 (source_name, req_type)：请求计数、成功计数、平均耗时各自独立累加。
        """
        now = datetime.datetime.now().isoformat()
        for dim in (req_type, GLOBAL_REQ_TYPE):
            doc_id = f"{source}::{dim}"
            existing = self._source_stats.get(ids=[doc_id], include=["metadatas"])
            metas = existing.get("metadatas") or []
            if metas and metas[0] is not None:
                meta = metas[0]
                old_total = int(meta.get("total_requests", 0))
                old_avg = float(meta.get("avg_elapsed", 0.0))
                old_success = int(meta.get("success_count", 0))
                new_total = old_total + 1
                new_success = old_success + (1 if success else 0)
                new_avg = (old_avg * old_total + elapsed_seconds) / new_total
                metadata = {
                    "source_name": source,
                    "req_type": dim,
                    "total_requests": new_total,
                    "success_count": new_success,
                    "avg_elapsed": new_avg,
                    "last_updated": now,
                }
            else:
                metadata = {
                    "source_name": source,
                    "req_type": dim,
                    "total_requests": 1,
                    "success_count": 1 if success else 0,
                    "avg_elapsed": elapsed_seconds,
                    "last_updated": now,
                }
            # ponytail: 用 [0.0] 占位向量满足 ChromaDB 对 embeddable 字段的强制要求，
            # source_stats 仅按 id + metadata 查询，向量本身无意义。
            self._source_stats.upsert(ids=[doc_id], embeddings=[[0.0]], metadatas=[metadata])
