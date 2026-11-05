"""Developer-facing endpoints that expose the Tree-sitter ingestion pipeline."""

from fastapi import APIRouter, HTTPException

from app import ingestion
from app.routes.common import read_repository_text_file, resolve_extract_dir
from app.structural_chunks import inspect_source

router = APIRouter()


@router.get("/parse")
def parse_repository_file(repo_url: str, path: str):
    repository, extract_dir = resolve_extract_dir(repo_url)
    file = read_repository_text_file(extract_dir, path)

    try:
        inspected = inspect_source(file["file_path"], file["content"])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Could not parse {file['file_path']}: {exc}",
        )

    return {"repository": repository, "size": file["size"], **inspected}


@router.get("/ingestion")
def repository_ingestion(repo_url: str):
    repository, extract_dir = resolve_extract_dir(repo_url)

    report = ingestion.get_report(repository)
    if report is None:
        report = ingestion.build_report(extract_dir, repository)

    return report
