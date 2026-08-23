from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import chromadb

from app.core.config import get_settings
from app.rag.chunker import CodeChunk

settings = get_settings()


@dataclass
class SearchResult:
    id: str
    content: str
    metadata: dict
    distance: float


class VectorStoreManager:
    """Wraps a local, persistent ChromaDB collection for semantic code search.
    Uses ChromaDB's default local embedding function (ONNX MiniLM) — no
    external API calls, consistent with the local-default-stack requirement."""

    def __init__(self, persist_dir: Optional[str] = None, collection_name: Optional[str] = None):
        self._client = chromadb.PersistentClient(path=persist_dir or settings.CHROMA_PERSIST_DIR)
        self._collection = self._client.get_or_create_collection(
            name=collection_name or settings.CHROMA_COLLECTION_NAME,
        )

    def upsert_chunks(self, chunks: list[CodeChunk]) -> None:
        if not chunks:
            return
        self._collection.upsert(
            ids=[c.id for c in chunks],
            documents=[c.content for c in chunks],
            metadatas=[
                {
                    "file_path": c.file_path,
                    "language": c.language,
                    "kind": c.kind,
                    "name": c.name or "",
                    "context_path": c.context_path,
                    "start_line": c.start_line,
                    "end_line": c.end_line,
                    "part_index": c.part_index,
                    "part_total": c.part_total,
                }
                for c in chunks
            ],
        )

    def delete_by_file(self, file_path: str) -> None:
        self._collection.delete(where={"file_path": file_path})

    def query(self, query_text: str, n_results: int = 5, where: Optional[dict] = None) -> list[SearchResult]:
        results = self._collection.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
        ids = results["ids"][0]
        documents = results["documents"][0]
        metadatas = results["metadatas"][0]
        distances = results["distances"][0]
        return [
            SearchResult(id=i, content=d, metadata=m, distance=dist)
            for i, d, m, dist in zip(ids, documents, metadatas, distances)
        ]

    def count(self) -> int:
        return self._collection.count()
