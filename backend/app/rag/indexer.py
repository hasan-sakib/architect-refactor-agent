from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.rag.chunker import chunk_file
from app.rag.vector_store import VectorStoreManager

logger = get_logger(__name__)

EXCLUDED_DIRS = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    ".pytest_cache",
    "data",
}


@dataclass
class IndexStats:
    files_indexed: int
    files_skipped: int
    chunks_indexed: int


def _iter_source_files(repo_path: Path):
    for path in repo_path.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        yield path


def index_repository(repo_path: str, store: VectorStoreManager | None = None) -> IndexStats:
    root = Path(repo_path).resolve()
    store = store or VectorStoreManager()

    files_indexed = 0
    files_skipped = 0
    chunks_indexed = 0

    for path in _iter_source_files(root):
        relative_path = str(path.relative_to(root))
        try:
            chunks = chunk_file(str(path), root_dir=str(root))
        except (UnicodeDecodeError, OSError) as e:
            logger.warning("skipping %s: %s", relative_path, e)
            files_skipped += 1
            continue

        if not chunks:
            files_skipped += 1
            continue

        store.delete_by_file(relative_path)
        store.upsert_chunks(chunks)
        files_indexed += 1
        chunks_indexed += len(chunks)

    return IndexStats(
        files_indexed=files_indexed,
        files_skipped=files_skipped,
        chunks_indexed=chunks_indexed,
    )
