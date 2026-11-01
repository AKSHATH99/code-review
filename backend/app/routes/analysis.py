from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analysis.budget import ContextBudgetError
from app.analysis.collector import AnalysisCollectionError
from app.analysis.pipeline import (
    NoAnalysableFilesError,
    RepositoryAnalysisError,
    analyze_repository,
)
from app.github import parse_github_repo_url, repository_extract_dir
from app.llm_errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMResponseError,
)

router = APIRouter()


class AnalysisRequest(BaseModel):
    repo_url: str


def _resolve_extract_dir(repo_url: str) -> tuple[str, Path]:
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


@router.post("/analysis")
def repository_analysis(payload: AnalysisRequest):
    repository, extract_dir = _resolve_extract_dir(payload.repo_url)

    try:
        result = analyze_repository(extract_dir)
    except NoAnalysableFilesError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ContextBudgetError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except AnalysisCollectionError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except RepositoryAnalysisError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except (LLMConnectionError, LLMResponseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"repository": repository, **result}
