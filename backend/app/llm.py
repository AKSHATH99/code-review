import os

import httpx

from app import gemini, ollama
from app.llm_errors import LLMConfigurationError

REQUEST_TIMEOUT = httpx.Timeout(120.0, connect=5.0)
LONG_REQUEST_TIMEOUT = httpx.Timeout(240.0, connect=5.0)
ANALYSIS_REQUEST_TIMEOUT = httpx.Timeout(600.0, connect=5.0)

PROVIDER_AUTO = "auto"
PROVIDER_GEMINI = "gemini"
PROVIDER_OLLAMA = "ollama"
VALID_PROVIDERS = {PROVIDER_AUTO, PROVIDER_GEMINI, PROVIDER_OLLAMA}


def configured_provider() -> str:
    provider = os.getenv("LLM_PROVIDER", PROVIDER_AUTO).strip().lower()
    if not provider:
        provider = PROVIDER_AUTO
    if provider not in VALID_PROVIDERS:
        raise LLMConfigurationError(
            "LLM_PROVIDER must be auto, gemini, or ollama."
        )
    return provider


def provider_name() -> str:
    provider = configured_provider()
    if provider == PROVIDER_AUTO:
        return (
            PROVIDER_GEMINI
            if os.getenv("GEMINI_API_KEY", "").strip()
            else PROVIDER_OLLAMA
        )
    if (
        provider == PROVIDER_GEMINI
        and not os.getenv("GEMINI_API_KEY", "").strip()
    ):
        raise LLMConfigurationError(
            "LLM_PROVIDER is set to gemini but GEMINI_API_KEY is not set. "
            "Add the key to backend/.env or set LLM_PROVIDER=ollama."
        )
    return provider


def get_model_name() -> str:
    if provider_name() == PROVIDER_GEMINI:
        return gemini.get_model_name()
    return ollama.get_model_name()


def send_message(
    message: str,
    timeout: httpx.Timeout | None = None,
    options: dict | None = None,
) -> str:
    if provider_name() == PROVIDER_GEMINI:
        return gemini.send_message(
            message,
            timeout=timeout or gemini.REQUEST_TIMEOUT,
            options=options,
        )
    return ollama.send_message(
        message,
        timeout=timeout or ollama.REQUEST_TIMEOUT,
        options=options,
    )
