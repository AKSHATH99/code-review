from functools import lru_cache

import numpy as np

EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 32

_EMBEDDING_CACHE: dict[tuple[str, int], tuple[list[dict], np.ndarray]] = {}


class EmbeddingGenerationError(Exception):
    pass


@lru_cache(maxsize=1)
def get_embedding_model():
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(EMBEDDING_MODEL_NAME)
    except Exception as exc:
        raise EmbeddingGenerationError(
            f"Could not load the embedding model '{EMBEDDING_MODEL_NAME}': {exc}"
        ) from exc


def _encode(texts: list[str]) -> np.ndarray:
    model = get_embedding_model()

    try:
        vectors = model.encode(
            texts,
            batch_size=EMBEDDING_BATCH_SIZE,
            show_progress_bar=False,
            convert_to_numpy=True,
        )
    except Exception as exc:
        raise EmbeddingGenerationError(
            f"Failed to generate embeddings: {exc}"
        ) from exc

    return np.asarray(vectors, dtype=np.float32)


def embed_chunks(chunks: list[dict]) -> tuple[list[dict], int]:
    if not chunks:
        return [], 0

    vectors = _encode([chunk["content"] for chunk in chunks])

    embeddings = [
        {
            "file_path": chunk["file_path"],
            "chunk_index": chunk["chunk_index"],
            "start_line": chunk["start_line"],
            "end_line": chunk["end_line"],
            "values": vector.tolist(),
        }
        for chunk, vector in zip(chunks, vectors)
    ]

    return embeddings, int(vectors.shape[1])


def embed_query(query: str) -> np.ndarray:
    return _encode([query])[0]


def cache_embeddings(
    repository: str,
    chunk_size: int,
    chunks: list[dict],
    embeddings: list[dict],
) -> None:
    matrix = np.asarray(
        [embedding["values"] for embedding in embeddings],
        dtype=np.float32,
    )
    _EMBEDDING_CACHE[(repository, chunk_size)] = (chunks, matrix)


def get_cached_embeddings(
    repository: str, chunk_size: int
) -> tuple[list[dict], np.ndarray] | None:
    return _EMBEDDING_CACHE.get((repository, chunk_size))
