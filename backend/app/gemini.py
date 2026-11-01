import os

import httpx

from app.llm_errors import (
    LLMConfigurationError,
    LLMConnectionError,
    LLMResponseError,
)

DEFAULT_API_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
DEFAULT_MODEL = "gemini-3.6-flash"
DEFAULT_MAX_OUTPUT_TOKENS = 4096
DEFAULT_TEMPERATURE = 0.2
REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
MODEL_INFO_TIMEOUT = httpx.Timeout(15.0, connect=5.0)

BLOCKED_FINISH_REASONS = {
    "SAFETY",
    "RECITATION",
    "BLOCKLIST",
    "PROHIBITED_CONTENT",
    "SPII",
    "IMAGE_SAFETY",
}


def _api_base_url() -> str:
    return os.getenv(
        "GEMINI_API_BASE_URL", DEFAULT_API_BASE_URL
    ).strip().rstrip("/")


def _api_key() -> str:
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        raise LLMConfigurationError(
            "GEMINI_API_KEY is not set. Add it to backend/.env or set "
            "LLM_PROVIDER=ollama to use local Ollama."
        )
    return key


def _model_name() -> str:
    model = os.getenv("GEMINI_MODEL", DEFAULT_MODEL).strip() or DEFAULT_MODEL
    if model.startswith("models/"):
        model = model[len("models/") :]
    return model


def get_model_name() -> str:
    return _model_name()


def _error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except ValueError:
        return response.text.strip()[:300]

    error = data.get("error") if isinstance(data, dict) else None
    if not isinstance(error, dict):
        return response.text.strip()[:300]

    message = str(error.get("message", "")).strip()
    status = str(error.get("status", "")).strip()
    if status:
        message = f"{message} ({status})" if message else status
    return message[:300]


def _raise_for_gemini_error(exc: httpx.HTTPError, action: str) -> None:
    if isinstance(exc, httpx.TimeoutException):
        raise LLMConnectionError(f"{action} timed out.") from exc
    if isinstance(exc, httpx.ConnectError):
        raise LLMConnectionError(
            "Could not connect to Gemini. Check your network connection."
        ) from exc
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        detail = _error_detail(exc.response)
        message = f"Gemini returned HTTP {status}."
        if detail:
            message = f"{message} {detail}"
        if status in (401, 403):
            raise LLMConfigurationError(
                f"{message} Check GEMINI_API_KEY or set LLM_PROVIDER=ollama."
            ) from exc
        if status == 404:
            raise LLMConfigurationError(
                f"{message} Check GEMINI_MODEL."
            ) from exc
        raise LLMResponseError(message) from exc
    raise LLMConnectionError(f"{action} failed: {exc}") from exc


def fetch_model_info() -> dict:
    model = _model_name()
    try:
        response = httpx.get(
            f"{_api_base_url()}/models/{model}",
            headers={"x-goog-api-key": _api_key()},
            timeout=MODEL_INFO_TIMEOUT,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_gemini_error(
            exc, "Reading the Gemini model configuration"
        )

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMResponseError(
            "Gemini returned an unexpected model configuration."
        ) from exc

    if not isinstance(data, dict):
        raise LLMResponseError(
            "Gemini returned an unexpected model configuration."
        )

    return data


def _generation_config(options: dict | None, model: str) -> dict:
    options = options or {}
    max_output = options.get("num_predict")
    if (
        not isinstance(max_output, int)
        or isinstance(max_output, bool)
        or max_output <= 0
    ):
        max_output = DEFAULT_MAX_OUTPUT_TOKENS

    config = {
        "temperature": DEFAULT_TEMPERATURE,
        "maxOutputTokens": max_output,
    }

    if "flash" in model.lower() or "lite" in model.lower():
        config["thinkingConfig"] = {"thinkingBudget": 0}

    return config


def _extract_text(data: dict) -> str:
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        feedback = data.get("promptFeedback")
        reason = (
            feedback.get("blockReason")
            if isinstance(feedback, dict)
            else None
        )
        if reason:
            raise LLMResponseError(f"Gemini blocked the prompt ({reason}).")
        raise LLMResponseError("Gemini returned no response candidates.")

    candidate = candidates[0]
    if not isinstance(candidate, dict):
        raise LLMResponseError("Gemini returned an unexpected response.")

    content = candidate.get("content")
    parts = content.get("parts") if isinstance(content, dict) else None
    text = "".join(
        part["text"]
        for part in parts or []
        if isinstance(part, dict) and isinstance(part.get("text"), str)
    )

    if not text.strip():
        finish = str(candidate.get("finishReason", "")).strip()
        if finish in BLOCKED_FINISH_REASONS:
            raise LLMResponseError(
                f"Gemini blocked the response ({finish})."
            )
        if finish == "MAX_TOKENS":
            raise LLMResponseError(
                "Gemini ran out of output tokens before returning text."
            )
        raise LLMResponseError("Gemini did not return a text response.")

    return text


def send_message(
    message: str,
    timeout: httpx.Timeout = REQUEST_TIMEOUT,
    options: dict | None = None,
) -> str:
    model = _model_name()
    payload = {
        "contents": [
            {"role": "user", "parts": [{"text": message}]},
        ],
        "generationConfig": _generation_config(options, model),
    }

    try:
        response = httpx.post(
            f"{_api_base_url()}/models/{model}:generateContent",
            headers={
                "x-goog-api-key": _api_key(),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=timeout,
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        _raise_for_gemini_error(exc, "The Gemini request")

    try:
        data = response.json()
    except ValueError as exc:
        raise LLMResponseError("Gemini returned an unexpected response.") from exc

    if not isinstance(data, dict):
        raise LLMResponseError("Gemini returned an unexpected response.")

    return _extract_text(data)
