#!/usr/bin/env python3
"""联调前连通性检测脚本。"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC_PATH = ROOT / "src"
if str(SRC_PATH) not in sys.path:
    sys.path.insert(0, str(SRC_PATH))


def check_python_version() -> bool:
    ok = sys.version_info >= (3, 11)
    print(f"[{'OK' if ok else 'FAIL'}] Python {sys.version}")
    return ok


def check_dotenv() -> bool:
    env = Path(".env")
    ok = env.exists() and "LLM_API_KEY" in env.read_text()
    print(f"[{'OK' if ok else 'FAIL'}] .env with LLM_API_KEY")
    return ok


def check_adapters_construct() -> bool:
    try:
        from rdi.adapters import get_adapter
        from rdi.models.common import DataSource
    except Exception as exc:
        print(f"[FAIL] Adapter import: {exc}")
        return False

    failed = []
    for source in DataSource:
        try:
            adapter = get_adapter(source)
            assert adapter.source == source
        except Exception as exc:
            failed.append((source.value, str(exc)))

    ok = not failed
    print(f"[{'OK' if ok else 'FAIL'}] Adapter construct ({len(list(DataSource))} sources)")
    for src, err in failed:
        print(f"       {src}: {err}")
    return ok


def check_chromadb() -> bool:
    try:
        from rdi.hermes.experience_db import ExperienceDB

        db = ExperienceDB()
        db.store_experience(
            task_desc="test",
            req_type="paper",
            result_status="success",
            sources_used=["arxiv"],
            elapsed_seconds=1.0,
        )
        print("[OK] ChromaDB init")
        return True
    except Exception as exc:
        print(f"[FAIL] ChromaDB init: {exc}")
        return False


def main() -> int:
    checks = [
        check_python_version,
        check_dotenv,
        check_adapters_construct,
        check_chromadb,
    ]
    results = [c() for c in checks]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
