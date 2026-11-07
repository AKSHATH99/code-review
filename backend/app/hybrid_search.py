"""Hybrid retrieval fusing semantic and BM25 rankings via Reciprocal Rank Fusion."""

from app.lexical_search import search_lexical
from app.search import search_chunks

RRF_K = 60
RETRIEVAL_LIMIT = 15
TOP_K = 15


def _chunk_identity(result: dict) -> tuple:
    # Semantic results carry no byte offsets, so both systems key chunks by
    # the line-based identity (the components of chunk_id). chunk_index alone
    # is only unique within a file.
    return (result["file_path"], result["start_line"], result["end_line"])


def reciprocal_rank_fusion(
    semantic_results: list[dict],
    lexical_results: list[dict],
    k: int = RRF_K,
) -> list[dict]:
    """Merge two ranked result lists, scoring each chunk by 1/(k + rank).

    Ranks are 1-based per list; a chunk found in both lists accumulates both
    contributions. Original similarity/bm25_score values are preserved as
    metadata but never feed the RRF score.
    """
    fused: dict[tuple, dict] = {}

    for system, results in (
        ("semantic", semantic_results),
        ("bm25", lexical_results),
    ):
        for rank, result in enumerate(results, start=1):
            identity = _chunk_identity(result)
            entry = fused.get(identity)
            if entry is None:
                entry = {**result, "rrf_score": 0.0, "retrieved_by": []}
                fused[identity] = entry
            else:
                for key, value in result.items():
                    entry.setdefault(key, value)
            entry["rrf_score"] += 1.0 / (k + rank)
            entry["retrieved_by"].append(system)

    return sorted(
        fused.values(), key=lambda entry: entry["rrf_score"], reverse=True
    )


def search_hybrid(
    repository: str, query: str, limit: int = TOP_K
) -> tuple[int, list[dict]]:
    total_chunks, semantic_results = search_chunks(
        repository, query, limit=RETRIEVAL_LIMIT
    )
    _, lexical_results = search_lexical(repository, query, limit=RETRIEVAL_LIMIT)

    fused = reciprocal_rank_fusion(semantic_results, lexical_results)
    return total_chunks, fused[: max(0, limit)]