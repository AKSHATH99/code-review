"""Shared helpers for repository routes."""

from pathlib import Path

from fastapi import HTTPException

from app.files import (
    RepositoryFileError,
    RepositoryFileNotFoundError,
    RepositoryFileTooLargeError,
    UnsupportedFileError,
    UnsafeFilePathError,
    read_repository_file,
)
from app.github import parse_github_repo_url, repository_extract_dir


def resolve_extract_dir(repo_url: str) -> tuple[str, Path]:
    try:
        repository = parse_github_repo_url(repo_url)
        extract_dir = repository_extract_dir(repository)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not access repository storage: {exc}",
        )

    if not extract_dir.is_dir():
        raise HTTPException(
            status_code=404,
            detail="Repository has not been downloaded and extracted yet.",
        )

    return repository, extract_dir


def read_repository_text_file(extract_dir: Path, path: str) -> dict:
    try:
        return read_repository_file(extract_dir, path)
    except UnsafeFilePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RepositoryFileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except RepositoryFileTooLargeError as exc:
        raise HTTPException(status_code=413, detail=str(exc))
    except UnsupportedFileError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RepositoryFileError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
