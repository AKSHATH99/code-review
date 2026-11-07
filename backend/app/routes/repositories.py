from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from app import ingestion
from app.chunks import chunk_repository
from app.embeddings import (
    EMBEDDING_MODEL_NAME,
    EmbeddingGenerationError,
    cache_embeddings,
    embed_chunks,
)
from app.files import list_repository_files
from app.github import (
    GithubDownloadError,
    GithubLookupError,
    RepositoryNotFoundError,
    ZipExtractionError,
    download_repository_zip,
    extract_repository_zip,
    fetch_repository_details,
    parse_github_repo_url,
)
from app.hybrid_search import search_hybrid
from app.lexical_search import LexicalIndexNotReadyError, build_lexical_index
from app.routes.common import (
    read_repository_text_file,
    resolve_extract_dir as _resolve_extract_dir,
)
from app.search import EmbeddingsNotReadyError, search_chunks
from app.stats import DEFAULT_LARGEST_FILES, compute_repository_stats

router = APIRouter()


class DownloadRequest(BaseModel):
    repo_url: str


class EmbeddingsRequest(BaseModel):
    repo_url: str


class SearchRequest(BaseModel):
    repo_url: str
    query: str


@router.get("/details")
def repository_details(repo_url: str):
    try:
        return fetch_repository_details(repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RepositoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except GithubLookupError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/files")
def repository_files(repo_url: str):
    repository, extract_dir = _resolve_extract_dir(repo_url)

    files = list_repository_files(extract_dir)

    return {
        "repository": repository,
        "total_files": len(files),
        "files": files,
    }


@router.get("/stats")
def repository_stats(
    repo_url: str,
    largest: int = Query(default=DEFAULT_LARGEST_FILES, ge=1, le=50),
):
    repository, extract_dir = _resolve_extract_dir(repo_url)

    try:
        stats = compute_repository_stats(extract_dir, largest)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not read repository files: {exc}",
        ) from exc

    return {"repository": repository, **stats}


@router.get("/file")
def repository_file(repo_url: str, path: str):
    repository, extract_dir = _resolve_extract_dir(repo_url)

    file = read_repository_text_file(extract_dir, path)

    return {"repository": repository, **file}


@router.get("/chunks")
def repository_chunks(repo_url: str):
    repository, extract_dir = _resolve_extract_dir(repo_url)

    report = ingestion.new_report(repository)
    chunks = chunk_repository(extract_dir, report)
    ingestion.store_report(report)

    return {
        "repository": repository,
        "total_chunks": len(chunks),
        "chunks": chunks,
    }


@router.post("/embeddings")
def repository_embeddings(payload: EmbeddingsRequest):
    repository, extract_dir = _resolve_extract_dir(payload.repo_url)

    report = ingestion.new_report(repository)
    chunks = chunk_repository(extract_dir, report)
    ingestion.store_report(report)

    try:
        embeddings, dimensions = embed_chunks(chunks)
    except EmbeddingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    cache_embeddings(repository, chunks, embeddings)

    try:
        build_lexical_index(repository, chunks)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not build the lexical index: {exc}",
        ) from exc

    ingestion.mark_embedded(repository, len(chunks))

    return {
        "repository": repository,
        "model": EMBEDDING_MODEL_NAME,
        "total_chunks": len(chunks),
        "total_embeddings": len(embeddings),
        "dimensions": dimensions,
        "embeddings": embeddings,
    }


@router.post("/search")
def repository_search(payload: SearchRequest):
    try:
        repository = parse_github_repo_url(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        total_chunks, results = search_chunks(repository, query)
    except EmbeddingsNotReadyError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except EmbeddingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "repository": repository,
        "query": query,
        "model": EMBEDDING_MODEL_NAME,
        "total_chunks": total_chunks,
        "results": results,
    }


@router.post("/search/hybrid")
def repository_hybrid_search(payload: SearchRequest):
    try:
        repository = parse_github_repo_url(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    query = payload.query.strip()
    if not query:
        raise HTTPException(status_code=400, detail="Query must not be empty.")

    try:
        total_chunks, results = search_hybrid(repository, query)
    except (EmbeddingsNotReadyError, LexicalIndexNotReadyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except EmbeddingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "repository": repository,
        "query": query,
        "model": EMBEDDING_MODEL_NAME,
        "total_chunks": total_chunks,
        "results": results,
    }


@router.post("/download")
def download_repository(payload: DownloadRequest):
    try:
        repository, zip_path = download_repository_zip(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except GithubDownloadError as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    try:
        extract_dir = extract_repository_zip(zip_path)
    except ZipExtractionError as exc:
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "status": "ok",
        "repository": repository,
        "zip_path": str(zip_path),
        "extract_dir": str(extract_dir),
    }
