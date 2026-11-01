import os

import httpx

from app.llm_errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMError,
    LLMResponseError,
)

DEFAULT_BASE_URL = "http://localhost:11434"
REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
LONG_REQUEST_TIMEOUT = httpx.Timeout(240.0, connect=5.0)
ANALYSIS_REQUEST_TIMEOUT = httpx.Timeout(600.0, connect=5.0)
MODEL_INFO_TIMEOUT = httpx.Timeout(15.0, connect=5.0)
WARMUP_TIMEOUT = httpx.Timeout(180.0, connect=5.0)


class OllamaError(LLMError):
    pass


class OllamaConfigurationError(LLMConfigurationError, OllamaError):
    pass


class OllamaConnectionError(LLMConnectionError, OllamaError):
    pass


class OllamaResponseError(LLMResponseError, OllamaError):
    pass


def _base_url() -> str:
    return os.getenv("OLLAMA_BASE_URL", DEFAULT_BASE_URL).strip().rstrip("/")


def _chat_url() -> str:
    return f"{_base_url()}/api/chat"


def _model_name() -> str:
    model = os.getenv("OLLAMA_MODEL", "").strip()
    if not model:
        raise OllamaConfigurationError(
            "OLLAMA_MODEL is not set. Add it to backend/.env."
        )
    return model


def get_model_name() -> str:
    return _model_name()


def _raise_for_ollama_error(exc: httpx.HTTPError, action: str) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise OllamaConnectionError(f"{action} timed out.") from exc
    if isinstance(exc, httpx.ConnectError):
        raise OllamaConnectionError(
            "Could not connect to Ollama. Make sure it is running."
        ) from exc
    if isinstance(exc, httpx.HTTPStatusError):
        detail = exc.response.text.strip()
        message = f"Ollama returned HTTP {exc.response.status_code}."
        if detail:
            message = f"{message} {detail[:300]}"
        raise OllamaResponseError(message) from exc
    raise OllamaConnectionError(f"{action} failed: {exc}") from exc


def fetch_running_models() -> list[dict]:
    try:
        response = httpx.get(
            f"{_base_url()}/api/ps", timeout=MODEL_INFO_TIMEOUT
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_ollama_error(exc, "Reading running Ollama models")

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaResponseError(
            "Ollama returned an unexpected running-model response."
        ) from exc

    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, list):
        raise OllamaResponseError(
            "Ollama returned an unexpected running-model response."
        )

    return [model for model in models if isinstance(model, dict)]


def fetch_model_info() -> dict:
    try:
        response = httpx.post(
            f"{_base_url()}/api/show",
            json={"model": _model_name()},
            timeout=MODEL_INFO_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_ollama_error(exc, "Reading the Ollama model configuration")

    try:
        data = response.json()
    except ValueError as exc:
        raise OllamaResponseError(
            "Ollama returned an unexpected model configuration."
        ) from exc

    if not isinstance(data, dict):
        raise OllamaResponseError(
            "Ollama returned an unexpected model configuration."
        )

    return data


def warm_up_model() -> None:
    payload = {
        "model": _model_name(),
        "messages": [{"role": "user", "content": "Ready?"}],
        "stream": False,
        "options": {"num_predict": 1},
    }

    try:
        response = httpx.post(
            _chat_url(), json=payload, timeout=WARMUP_TIMEOUT
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_ollama_error(exc, "Loading the Ollama model")


def send_message(
    message: str,
    timeout: httpx.Timeout = REQUEST_TIMEOUT,
    options: dict | None = None,
) -> str:
    payload = {
        "model": _model_name(),
        "messages": [{"role": "user", "content": message}],
        "stream": False,
    }
    if options:
        payload["options"] = options

    try:
        response = httpx.post(_chat_url(), json=payload, timeout=timeout)
        response.raise_for_status()
    except httpx.TimeoutException as exc:
        raise OllamaConnectionError("The Ollama request timed out.") from exc
    except httpx.ConnectError as exc:
        raise OllamaConnectionError(
            "Could not connect to Ollama. Make sure it is running."
        ) from exc
    except httpx.HTTPStatusError as exc:
        detail = exc.response.text.strip()
        message = f"Ollama returned HTTP {exc.response.status_code}."
        if detail:
            message = f"{message} {detail[:300]}"
        raise OllamaResponseError(message) from exc
    except httpx.RequestError as exc:
        raise OllamaConnectionError(f"Ollama request failed: {exc}") from exc

    try:
        content = response.json()["message"]["content"]
    except (ValueError, KeyError, TypeError) as exc:
        raise OllamaResponseError(
            "Ollama returned an unexpected response."
        ) from exc

    if not isinstance(content, str):
        raise OllamaResponseError("Ollama did not return a text response.")

    return content
