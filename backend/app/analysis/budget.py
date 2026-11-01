import os
import re
from dataclasses import dataclass
from math import ceil

from app.analysis.prompts import (
    BATCH_SUMMARY_INSTRUCTIONS,
    FINAL_ANALYSIS_INSTRUCTIONS,
    SUMMARY_MERGE_INSTRUCTIONS,
    SYSTEM_INSTRUCTIONS,
)
from app import gemini, llm
from app.ollama import (
    fetch_model_info,
    fetch_running_models,
    warm_up_model,
)
from app.stats import estimate_text_tokens

RESERVED_OUTPUT_TOKENS = 1500
SAFETY_MARGIN_RATIO = 0.1
MIN_SAFETY_MARGIN_TOKENS = 512


class ContextBudgetError(Exception):
    pass


@dataclass(frozen=True)
class ContextBudget:
    provider: str
    model: str
    context_length: int
    context_source: str
    system_tokens: int
    prompt_tokens: int
    output_tokens: int
    safety_margin_tokens: int
    available_input_tokens: int

    def reserved_metadata(self) -> dict:
        return {
            "system_instructions": self.system_tokens,
            "analysis_prompt": self.prompt_tokens,
            "expected_output": self.output_tokens,
            "safety_margin": self.safety_margin_tokens,
        }


def _discover_context_length(info: dict) -> tuple[int | None, str | None]:
    parameters = info.get("parameters")
    if isinstance(parameters, list):
        parameters = "\n".join(str(item) for item in parameters)
    if isinstance(parameters, str):
        match = re.search(r"(?:^|\n)\s*num_ctx\s+(\d+)\b", parameters)
        if match and int(match.group(1)) > 0:
            return int(match.group(1)), "ollama_show:num_ctx"

    model_info = info.get("model_info")
    if isinstance(model_info, dict):
        lengths = [
            value
            for key, value in model_info.items()
            if key.endswith("context_length")
            and isinstance(value, int)
            and not isinstance(value, bool)
            and value > 0
        ]
        if lengths:
            return max(lengths), "ollama_show:model_info"

    return None, None


def _matches_model(item: dict, model: str) -> bool:
    names = {
        str(item.get("name", "")).lower(),
        str(item.get("model", "")).lower(),
    }
    wanted = model.lower()
    if wanted in names:
        return True
    wanted_base = wanted.split(":", 1)[0]
    return any(
        name and name.split(":", 1)[0] == wanted_base for name in names
    )


def _running_context_length(models: list[dict], model: str) -> int | None:
    for item in models:
        if not _matches_model(item, model):
            continue
        value = item.get("context_length")
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return None


def _resolve_ollama_context_length(model: str) -> tuple[int, str]:
    override = os.getenv("OLLAMA_NUM_CTX", "").strip()
    if override:
        try:
            context_length = int(override)
        except ValueError as exc:
            raise ContextBudgetError(
                "OLLAMA_NUM_CTX must be a positive integer."
            ) from exc
        if context_length <= 0:
            raise ContextBudgetError(
                "OLLAMA_NUM_CTX must be a positive integer."
            )
        return context_length, "OLLAMA_NUM_CTX"

    context_length = _running_context_length(fetch_running_models(), model)
    if context_length is not None:
        return context_length, "ollama_ps:context_length"

    warm_up_model()
    context_length = _running_context_length(fetch_running_models(), model)
    if context_length is not None:
        return context_length, "ollama_ps:context_length"

    context_length, source = _discover_context_length(fetch_model_info())
    if context_length is None:
        raise ContextBudgetError(
            f"Could not determine the context window for {model}. "
            "Set OLLAMA_NUM_CTX to the model's configured context length."
        )

    return context_length, source


def _resolve_gemini_context_length(model: str) -> tuple[int, str]:
    override = os.getenv("GEMINI_NUM_CTX", "").strip()
    if override:
        try:
            context_length = int(override)
        except ValueError as exc:
            raise ContextBudgetError(
                "GEMINI_NUM_CTX must be a positive integer."
            ) from exc
        if context_length <= 0:
            raise ContextBudgetError(
                "GEMINI_NUM_CTX must be a positive integer."
            )
        return context_length, "GEMINI_NUM_CTX"

    info = gemini.fetch_model_info()
    context_length = info.get("inputTokenLimit")
    if (
        isinstance(context_length, int)
        and not isinstance(context_length, bool)
        and context_length > 0
    ):
        return context_length, "gemini_model_info:inputTokenLimit"

    raise ContextBudgetError(
        f"Could not determine the context window for {model}. "
        "Set GEMINI_NUM_CTX to the model's input token limit."
    )


def calculate_context_budget() -> ContextBudget:
    provider = llm.provider_name()
    model = llm.get_model_name()

    if provider == llm.PROVIDER_GEMINI:
        context_length, context_source = _resolve_gemini_context_length(model)
    else:
        context_length, context_source = _resolve_ollama_context_length(model)

    system_tokens = estimate_text_tokens(SYSTEM_INSTRUCTIONS)
    prompt_tokens = max(
        estimate_text_tokens(FINAL_ANALYSIS_INSTRUCTIONS),
        estimate_text_tokens(BATCH_SUMMARY_INSTRUCTIONS),
        estimate_text_tokens(SUMMARY_MERGE_INSTRUCTIONS),
    )
    output_tokens = RESERVED_OUTPUT_TOKENS
    safety_margin_tokens = max(
        MIN_SAFETY_MARGIN_TOKENS, ceil(context_length * SAFETY_MARGIN_RATIO)
    )
    reserved = (
        system_tokens
        + prompt_tokens
        + output_tokens
        + safety_margin_tokens
    )
    available_input_tokens = context_length - reserved

    if available_input_tokens <= 0:
        raise ContextBudgetError(
            f"The {model} context window ({context_length} tokens) is too small "
            "for the reserved analysis instructions and output. Increase the "
            "context window or use a model with a larger context."
        )

    return ContextBudget(
        provider=provider,
        model=model,
        context_length=context_length,
        context_source=context_source,
        system_tokens=system_tokens,
        prompt_tokens=prompt_tokens,
        output_tokens=output_tokens,
        safety_margin_tokens=safety_margin_tokens,
        available_input_tokens=available_input_tokens,
    )
