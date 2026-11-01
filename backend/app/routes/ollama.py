from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.embeddings import EmbeddingGenerationError
from app.github import parse_github_repo_url
from app.llm import get_model_name, provider_name, send_message
from app.llm_errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMResponseError,
)
from app.qa import answer_repository_question
from app.search import EmbeddingsNotReadyError

MAX_MESSAGE_LENGTH = 60000
MAX_QUESTION_LENGTH = 4000
MAX_ATTACHMENT_LENGTH = 50000

router = APIRouter()


class ChatRequest(BaseModel):
    message: str = Field(max_length=MAX_MESSAGE_LENGTH)


class Attachment(BaseModel):
    file_path: str = Field(min_length=1, max_length=1000)
    content: str = Field(max_length=MAX_ATTACHMENT_LENGTH)


class AskRequest(BaseModel):
    repo_url: str
    question: str = Field(max_length=MAX_QUESTION_LENGTH)
    attachment: Attachment | None = None


def _response_for(message: str) -> dict[str, str]:
    try:
        response = send_message(message)
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except (LLMConnectionError, LLMResponseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))

    return {"response": response}


@router.post("/test")
def ollama_test():
    return _response_for("Hi")


@router.get("/provider")
def generation_provider():
    try:
        return {"provider": provider_name(), "model": get_model_name()}
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/chat")
def ollama_chat(payload: ChatRequest):
    message = payload.message.strip()
    if not message:
        raise HTTPException(status_code=400, detail="Enter a message to send.")

    return _response_for(message)


@router.post("/ask")
def ollama_ask(payload: AskRequest):
    question = payload.question.strip()
    if not question:
        raise HTTPException(
            status_code=400,
            detail="Enter a question about the repository.",
        )

    try:
        repository = parse_github_repo_url(payload.repo_url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    attachment = (
        payload.attachment.model_dump() if payload.attachment else None
    )

    try:
        return answer_repository_question(repository, question, attachment)
    except EmbeddingsNotReadyError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "Repository embeddings are not ready. Reload the repository "
                "and try again."
            ),
        ) from exc
    except EmbeddingGenerationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except LLMConfigurationError as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    except (LLMConnectionError, LLMResponseError) as exc:
        raise HTTPException(status_code=502, detail=str(exc))
