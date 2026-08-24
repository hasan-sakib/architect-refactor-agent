from app.rag.vector_store import SearchResult, VectorStoreManager


def search_codebase(store: VectorStoreManager, query: str, n_results: int = 5) -> list[SearchResult]:
    return store.query(query, n_results=n_results)


def format_search_results(results: list[SearchResult]) -> str:
    if not results:
        return "(no relevant code found)"
    blocks = []
    for r in results:
        label = r.metadata.get("context_path") or r.metadata.get("kind", "")
        blocks.append(f"### {r.metadata['file_path']} :: {label}\n{r.content}")
    return "\n\n".join(blocks)
