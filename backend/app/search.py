import numpy as np

from app.embeddings import embed_query, get_cached_embeddings

TOP_K = 5


class EmbeddingsNotReadyError(Exception):
    pass


def search_chunks(
    repository: str, query: str, limit: int = TOP_K
) -> tuple[int, list[dict]]:
    cached = get_cached_embeddings(repository)
    if cached is None:
        raise EmbeddingsNotReadyError(
            "Embeddings have not been generated for this repository yet. "
            "Generate embeddings first."
        )

    chunks, matrix = cached
    if matrix.size == 0:
        raise EmbeddingsNotReadyError(
            "No chunk embeddings are available for this repository."
        )

    query_vector = embed_query(query)
    norms = np.linalg.norm(matrix, axis=1) * np.linalg.norm(query_vector)
    similarities = matrix @ query_vector / np.maximum(norms, 1e-12)

    top_indices = np.argsort(similarities)[::-1][:limit]

    results = []
    for index in top_indices:
        chunk = chunks[int(index)]
        results.append(
            {
                "file_path": chunk["file_path"],
                "chunk_index": chunk["chunk_index"],
                "start_line": chunk["start_line"],
                "end_line": chunk["end_line"],
                "content": chunk["content"],
                "similarity": float(similarities[index]),
            }
        )

    return len(chunks), results
