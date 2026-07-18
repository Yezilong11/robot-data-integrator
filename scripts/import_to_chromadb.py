"""
ChromaDB 导入脚本

功能：
- 读取 extract_metadata.py 生成的 _metadata_index.jsonl
- 计算 embedding(QWEN text-embedding-v3 / OpenAI 兼容 / 本地 hash 兜底)
- 写入 ChromaDB 集合(默认 data_sources)
- 支持断点续导入、批量重试、失败记录

依赖：
- chromadb>=0.4
- httpx(已有)
- python-dotenv(已有)

作者：挑战杯团队
创建日期：2026-07-15
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config import config  # noqa: E402


# ─── Embedding 客户端 ───

class EmbeddingClient:
    """多后端 embedding 客户端。"""

    def __init__(self) -> None:
        self.qwen_key = os.getenv("QWEN_API_KEY", "")
        self.qwen_model = os.getenv("QWEN_EMBEDDING_MODEL", "text-embedding-v3")
        self.openai_key = os.getenv("OPENAI_API_KEY", "")
        self.openai_base = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        # 兜底:无 API key 时使用本地 hash 伪 embedding(仅占位)
        self.fallback_dim = 256

    def is_available(self) -> bool:
        return bool(self.qwen_key) or bool(self.openai_key)

    def embed(self, texts: list[str]) -> list[list[float]]:
        """返回与 texts 等长的 embedding 列表。"""
        if self.qwen_key:
            return self._embed_qwen(texts)
        if self.openai_key:
            return self._embed_openai(texts)
        return [self._hash_embed(t) for t in texts]

    def _embed_qwen(self, texts: list[str]) -> list[list[float]]:
        """调用阿里云 DashScope(text-embedding-v3) embedding 接口。"""
        import httpx

        url = "https://dashscope.aliyuncs.com/api/v1/services/embeddings/text-embedding/text-embedding"
        headers = {
            "Authorization": f"Bearer {self.qwen_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.qwen_model,
            "input": {"texts": texts},
            "parameters": {"text_type": "document"},
        }
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return [item["embedding"] for item in data["output"]["embeddings"]]
        except Exception as e:
            print(f"  ⚠️  QWEN embedding 失败,回退 hash: {e}")
            return [self._hash_embed(t) for t in texts]

    def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        """调用 OpenAI 兼容 embedding 接口。"""
        import httpx

        url = f"{self.openai_base}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.openai_key}",
            "Content-Type": "application/json",
        }
        payload = {"model": "text-embedding-3-small", "input": texts}
        try:
            with httpx.Client(timeout=60.0) as client:
                r = client.post(url, json=payload, headers=headers)
                r.raise_for_status()
                data = r.json()
                return [item["embedding"] for item in data["data"]]
        except Exception as e:
            print(f"  ⚠️  OpenAI embedding 失败,回退 hash: {e}")
            return [self._hash_embed(t) for t in texts]

    def _hash_embed(self, text: str) -> list[float]:
        """本地 hash 伪 embedding(无 LLM 时的兜底,无语义)。"""
        digest = hashlib.sha512(text.encode("utf-8")).digest()
        # 重复 4 次以达 256 维
        raw = digest * 4
        return [(b - 128) / 128.0 for b in raw[: self.fallback_dim]]


# ─── 主流程 ───

def load_index(path: Path) -> list[dict]:
    """加载 JSONL 索引文件。"""
    records: list[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  ⚠️  跳过非法行: {e}")
    return records


def build_document(rec: dict) -> str:
    """从元数据记录构造 embedding 的文本。"""
    custom = rec.get("custom", {})
    parts = [
        f"Path: {rec['path']}",
        f"Type: {rec['type']}",
        f"Name: {rec['name']}",
    ]
    if isinstance(custom, dict):
        for k, v in list(custom.items())[:8]:
            if isinstance(v, (str, int, float)):
                parts.append(f"{k}: {v}")
            elif isinstance(v, list) and v:
                sample = ", ".join(str(x) for x in v[:3])
                parts.append(f"{k}: [{sample}...]")
    return "\n".join(parts)


def build_metadata(rec: dict) -> dict:
    """构造 ChromaDB metadata(仅保留可序列化类型)。"""
    return {
        "source": rec["path"],
        "type": rec["type"],
        "name": rec["name"],
        "ext": rec["ext"],
        "size_bytes": int(rec["size_bytes"]),
    }


def import_records(
    records: list[dict],
    embed_client: EmbeddingClient,
    chroma_path: Path,
    collection_name: str,
    batch_size: int = 64,
    max_retry: int = 3,
) -> tuple[int, int, int]:
    """导入记录到 ChromaDB。"""
    try:
        import chromadb
    except ImportError:
        print("❌ chromadb 未安装,请先运行: pip install chromadb")
        sys.exit(1)

    chroma_path.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(chroma_path))
    collection = client.get_or_create_collection(
        name=collection_name,
        metadata={"description": "robot-data-integrator data sources"},
    )

    # 跳过已存在 ID
    existing = set(collection.get(include=[]).get("ids", []))
    to_import = [r for r in records if r["id"] not in existing]
    skipped = len(records) - len(to_import)
    print(f"  跳过已存在: {skipped} 条")
    print(f"  待导入: {len(to_import)} 条")

    imported = 0
    failed = 0
    start = time.time()

    # 批量导入
    for i in range(0, len(to_import), batch_size):
        batch = to_import[i : i + batch_size]
        documents = [build_document(r) for r in batch]
        ids = [r["id"] for r in batch]
        metadatas = [build_metadata(r) for r in batch]

        # 计算 embedding(允许失败回退)
        embeddings = embed_client.embed(documents)

        # 写入
        success = False
        for attempt in range(1, max_retry + 1):
            try:
                collection.add(
                    ids=ids,
                    documents=documents,
                    metadatas=metadatas,
                    embeddings=embeddings,
                )
                imported += len(batch)
                success = True
                break
            except Exception as e:
                print(f"  ⚠️  Batch {i//batch_size+1} 第 {attempt} 次失败: {e}")
                if attempt < max_retry:
                    time.sleep(2 * attempt)
                    # 退化为单条重试
                    if attempt == max_retry - 1:
                        for j, (id_, doc, meta, emb) in enumerate(
                            zip(ids, documents, metadatas, embeddings)
                        ):
                            try:
                                collection.add(
                                    ids=[id_],
                                    documents=[doc],
                                    metadatas=[meta],
                                    embeddings=[emb],
                                )
                                imported += 1
                            except Exception as e2:
                                failed += 1
                                print(f"    ❌ {id_}: {e2}")
                        success = True
                else:
                    failed += len(batch)

        elapsed = time.time() - start
        rate = (i + len(batch)) / elapsed if elapsed > 0 else 0
        eta = (len(to_import) - i - len(batch)) / rate if rate > 0 else 0
        print(
            f"\r  Batch {i//batch_size+1}/{(len(to_import)+batch_size-1)//batch_size} "
            f"({imported}/{len(to_import)}) [{elapsed:.1f}s, ETA {eta:.1f}s]",
            end="",
            flush=True,
        )
    print()
    return imported, skipped, failed


def main() -> None:
    parser = argparse.ArgumentParser(description="将元数据导入 ChromaDB")
    parser.add_argument(
        "--index",
        type=str,
        default=None,
        help="JSONL 索引文件路径,默认 data/sources/_metadata_index.jsonl",
    )
    parser.add_argument(
        "--collection",
        type=str,
        default=os.getenv("CHROMA_COLLECTION", "data_sources"),
        help="ChromaDB 集合名",
    )
    parser.add_argument(
        "--chroma-path",
        type=str,
        default=None,
        help="ChromaDB 持久化目录,默认读取 .env 的 CHROMADB_PATH",
    )
    parser.add_argument("--batch-size", type=int, default=64, help="批量大小")
    args = parser.parse_args()

    print("=" * 70)
    print("  ChromaDB 导入脚本")
    print("=" * 70)

    # 路径解析
    index_path = (
        Path(args.index) if args.index else config.DATA_DIR / "_metadata_index.jsonl"
    )
    chroma_path = (
        Path(args.chroma_path)
        if args.chroma_path
        else config.PROJECT_ROOT / os.getenv("CHROMADB_PATH", "./data/experience_db").lstrip("./")
    )
    if not chroma_path.is_absolute():
        chroma_path = config.PROJECT_ROOT / chroma_path

    print(f"索引文件:   {index_path}")
    print(f"ChromaDB:   {chroma_path}")
    print(f"集合名:     {args.collection}")
    print(f"批量大小:   {args.batch_size}")
    print()

    if not index_path.exists():
        print(f"❌ 索引文件不存在: {index_path}")
        print("   请先运行: python scripts/extract_metadata.py")
        sys.exit(1)

    # 加载 embedding 客户端
    embed_client = EmbeddingClient()
    if not embed_client.is_available():
        print("⚠️  未配置 QWEN_API_KEY 或 OPENAI_API_KEY,使用本地 hash 伪 embedding")
        print("   (导入仍可成功,但查询时无语义匹配,仅支持 metadata 过滤)")
        print()

    # 加载索引
    print("[1/3] 加载索引文件...")
    records = load_index(index_path)
    print(f"  加载 {len(records)} 条记录")
    print()

    # 导入
    print("[2/3] 导入 ChromaDB...")
    imported, skipped, failed = import_records(
        records=records,
        embed_client=embed_client,
        chroma_path=chroma_path,
        collection_name=args.collection,
        batch_size=args.batch_size,
    )
    print()

    # 验证
    print("[3/3] 验证...")
    try:
        import chromadb

        verify_client = chromadb.PersistentClient(path=str(chroma_path))
        col = verify_client.get_collection(args.collection)
        total = col.count()
        print(f"  集合 {args.collection} 当前文档数: {total}")
    except Exception as e:
        print(f"  ⚠️  验证失败: {e}")
        total = imported

    print()
    print("=" * 70)
    print(f"  ✅ 导入: {imported} | ⏭️  跳过: {skipped} | ❌ 失败: {failed}")
    print("=" * 70)


if __name__ == "__main__":
    main()
