"""Repository-specific BM25 lexical retrieval over existing chunks.

The index is built from the same chunk list as the embeddings, so document
position i in the BM25 corpus always refers to chunks[i]. chunk_index is only
unique within a file and must never be used as a global identifier.
"""

import re

import numpy as np
from rank_bm25 import BM25Okapi

TOP_K = 15

_BM25_CACHE: dict[
    str, tuple[list[dict], BM25Okapi | None, list[frozenset[str]]]
] = {}

_SEARCHABLE_FIELDS = (
    "file_path",
    "symbol",
    "symbol_type",
    "parent_symbol",
    "json_path",
    "content",
)

_WORD_RE = re.compile(r"[A-Za-z0-9]+")
_CAMEL_BOUNDARY_RE = re.compile(
    r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])"
)


class LexicalIndexNotReadyError(Exception):
    pass


def tokenize(text: str) -> list[str]:
    """Split text into lowercase terms, keeping whole identifiers intact.

    Punctuation, underscores, hyphens, dots and path separators split words;
    camelCase and PascalCase words additionally yield their constituent terms
    after the full identifier, e.g. handleContactSubmit ->
    [handlecontactsubmit, handle, contact, submit].
    """
    tokens = []
    for word in _WORD_RE.findall(text):
        tokens.append(word.lower())
        parts = _CAMEL_BOUNDARY_RE.split(word)
        if len(parts) > 1:
            tokens.extend(part.lower() for part in parts)
    return tokens


def _searchable_text(chunk: dict) -> str:
    parts = []
    for field in _SEARCHABLE_FIELDS:
        value = chunk.get(field)
        if isinstance(value, str) and value:
            parts.append(value)
    return " ".join(parts)


def build_lexical_index(repository: str, chunks: list[dict]) -> None:
    # Drop any previous index first so a failed rebuild never leaves a stale
    # one behind.
    _BM25_CACHE.pop(repository, None)

    documents = [tokenize(_searchable_text(chunk)) for chunk in chunks]
    index = BM25Okapi(documents) if any(documents) else None
    token_sets = [frozenset(document) for document in documents]
    _BM25_CACHE[repository] = (chunks, index, token_sets)


def search_lexical(
    repository: str, query: str, limit: int = TOP_K
) -> tuple[int, list[dict]]:
    cached = _BM25_CACHE.get(repository)
    if cached is None:
        raise LexicalIndexNotReadyError(
            "Lexical index has not been built for this repository yet. "
            "Generate embeddings first."
        )

    chunks, index, token_sets = cached
    if index is None or limit <= 0:
        return len(chunks), []

    query_tokens = tokenize(query)
    if not query_tokens:
        return len(chunks), []

    scores = index.get_scores(query_tokens)
    order = np.argsort(-scores, kind="stable")

    # BM25Okapi idf is zero or negative for terms covering half or more of a
    # small corpus, so genuine matches can score <= 0. Gate relevance on
    # query-term overlap instead; chunks sharing no query token are never
    # returned.
    results = []
    for position in order:
        if len(results) >= limit:
            break
        position = int(position)
        if not token_sets[position].intersection(query_tokens):
            continue
        results.append({**chunks[position], "bm25_score": float(scores[position])})

    return len(chunks), results