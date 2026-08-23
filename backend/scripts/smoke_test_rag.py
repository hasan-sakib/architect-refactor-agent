"""Manual smoke test for the Phase 2 RAG pipeline (Tree-sitter chunker + ChromaDB).

Usage:
    cd backend && source .venv/bin/activate
    python scripts/smoke_test_rag.py
"""

import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.indexer import index_repository
from app.rag.vector_store import VectorStoreManager

BACKEND_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    persist_dir = tempfile.mkdtemp(prefix="refactor-agent-rag-smoke-")
    store = VectorStoreManager(persist_dir=persist_dir, collection_name="smoke_test")

    try:
        print(f"[1/3] Indexing {BACKEND_DIR}/app ...")
        stats = index_repository(str(BACKEND_DIR / "app"), store=store)
        print(f"      files_indexed={stats.files_indexed} files_skipped={stats.files_skipped} "
              f"chunks_indexed={stats.chunks_indexed}")
        assert stats.chunks_indexed > 0, "expected at least one chunk to be indexed"

        print("[2/3] Querying: 'run a command inside a docker sandbox container' ...")
        results = store.query("run a command inside a docker sandbox container", n_results=3)
        for r in results:
            print(f"      {r.metadata['file_path']} :: {r.metadata['context_path'] or r.metadata['kind']} "
                  f"(distance={r.distance:.4f})")
        assert any("docker_driver" in r.metadata["file_path"] for r in results), \
            "expected docker_driver.py to be a top semantic match"

        print("[3/3] Querying: 'read application settings from environment variables' ...")
        results = store.query("read application settings from environment variables", n_results=3)
        for r in results:
            print(f"      {r.metadata['file_path']} :: {r.metadata['context_path'] or r.metadata['kind']} "
                  f"(distance={r.distance:.4f})")
        assert any("config" in r.metadata["file_path"] for r in results), \
            "expected config.py to be a top semantic match"

        print("\nAll checks passed.")
    finally:
        shutil.rmtree(persist_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
