from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.analysis.budget import ContextBudgetError
from app.analysis.collector import AnalysisCollectionError
from app.analysis.pipeline import (
    NoAnalysableFilesError,
    RepositoryAnalysisError,
    analyze_repository,
)
from app.llm_errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMResponseError,
)
from app.routes.common import resolve_extract_dir as _resolve_extract_dir

router = APIRouter()


class AnalysisRequest(BaseModel):
    repo_url: str


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
