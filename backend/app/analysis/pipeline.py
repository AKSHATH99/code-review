import time
from pathlib import Path

from app.analysis.budget import (
    RESERVED_OUTPUT_TOKENS,
    ContextBudget,
    calculate_context_budget,
)
from app.analysis.collector import collect_analysis_files
from app.analysis.prompts import (
    build_batch_summary_prompt,
    build_final_synthesis_prompt,
    build_merge_summary_prompt,
    build_single_analysis_prompt,
    format_file_block,
    format_file_blocks,
)
from app.llm import ANALYSIS_REQUEST_TIMEOUT, send_message
from app.stats import CHARS_PER_TOKEN, estimate_text_tokens, estimate_tokens

MAX_HIERARCHY_STAGES = 6


class RepositoryAnalysisError(Exception):
    pass


class NoAnalysableFilesError(RepositoryAnalysisError):
    pass


class AnalysisPipelineError(RepositoryAnalysisError):
    pass


def _item_tokens(item: dict) -> int:
    return estimate_text_tokens(format_file_block(item))


def _request_options(
    budget: ContextBudget, max_output: int = RESERVED_OUTPUT_TOKENS
) -> dict:
    return {
        "num_ctx": budget.context_length,
        "num_predict": max(1, max_output),
    }


def _split_file(file: dict, budget: int) -> list[dict]:
    lines = file["content"].splitlines()
    header = (
        f"=== File: {file['file_path']} "
        f"(lines 1-{len(lines)}) ==="
    )
    content_budget = max(1, budget - estimate_text_tokens(header))
    max_chars = max(1, content_budget * CHARS_PER_TOKEN)

    sections = []
    current_lines = []
    start_line = 0
    end_line = 0
    used_chars = 0

    def emit():
        nonlocal current_lines, start_line, end_line, used_chars
        if not current_lines:
            return
        sections.append(
            {
                "file_path": file["file_path"],
                "content": "\n".join(current_lines),
                "start_line": start_line,
                "end_line": end_line,
            }
        )
        current_lines = []
        start_line = 0
        end_line = 0
        used_chars = 0

    for number, line in enumerate(lines, start=1):
        if len(line) > max_chars:
            emit()
            for offset in range(0, len(line), max_chars):
                sections.append(
                    {
                        "file_path": file["file_path"],
                        "content": line[offset : offset + max_chars],
                        "start_line": number,
                        "end_line": number,
                    }
                )
            continue

        if not current_lines:
            current_lines = [line]
            start_line = number
            end_line = number
            used_chars = len(line)
            continue

        added = 1 + len(line)
        if used_chars + added > max_chars:
            emit()
            current_lines = [line]
            start_line = number
            end_line = number
            used_chars = len(line)
        else:
            current_lines.append(line)
            end_line = number
            used_chars += added

    emit()
    return sections


def _build_sections(files: list[dict], budget: int) -> list[dict]:
    sections = []
    for file in files:
        whole = {
            "file_path": file["file_path"],
            "content": file["content"],
            "start_line": None,
            "end_line": None,
        }
        if _item_tokens(whole) <= budget:
            sections.append(whole)
        else:
            sections.extend(_split_file(file, budget))
    return sections


def _group_sections(sections: list[dict], budget: int) -> list[list[dict]]:
    groups = []
    current = []
    used = 0

    for section in sections:
        tokens = _item_tokens(section)
        if tokens > budget:
            raise AnalysisPipelineError(
                f"The input budget of {budget} tokens is too small to send "
                f"{section['file_path']}. Increase the configured context "
                "window or use a model with a larger context."
            )
        if current and used + tokens > budget:
            groups.append(current)
            current = []
            used = 0
        current.append(section)
        used += tokens

    if current:
        groups.append(current)

    return groups


def _summaries_tokens(summaries: list[str]) -> int:
    return sum(estimate_text_tokens(summary) + 4 for summary in summaries)


def _group_summaries(
    summaries: list[str], budget: int
) -> list[list[str]]:
    # Each piece costs a few extra tokens (separator and label), so leave room
    # for that overhead when splitting an oversized summary.
    max_chars = max(1, budget - 4) * CHARS_PER_TOKEN
    pieces = []
    for summary in summaries:
        if estimate_text_tokens(summary) <= budget:
            pieces.append(summary)
        else:
            for offset in range(0, len(summary), max_chars):
                pieces.append(summary[offset : offset + max_chars])

    groups = []
    current = []
    used = 0
    for piece in pieces:
        tokens = estimate_text_tokens(piece) + 4
        if tokens > budget:
            raise AnalysisPipelineError(
                f"The input budget of {budget} tokens is too small for the "
                "intermediate summaries. Increase the configured context "
                "window or use a model with a larger context."
            )
        if current and used + tokens > budget:
            groups.append(current)
            current = []
            used = 0
        current.append(piece)
        used += tokens

    if current:
        groups.append(current)

    return groups


def _reduce_summaries(
    summaries: list[str], budget: ContextBudget
) -> tuple[list[str], int]:
    stages = 0
    available = budget.available_input_tokens

    while _summaries_tokens(summaries) > available:
        if stages >= MAX_HIERARCHY_STAGES:
            raise AnalysisPipelineError(
                "The intermediate summaries could not be reduced below the "
                "available context budget."
            )

        groups = _group_summaries(summaries, available)
        target_tokens = min(
            RESERVED_OUTPUT_TOKENS,
            max(1, available // max(1, len(groups))),
        )
        summaries = [
            send_message(
                build_merge_summary_prompt(group, target_tokens),
                timeout=ANALYSIS_REQUEST_TIMEOUT,
                options=_request_options(budget, target_tokens),
            )
            for group in groups
        ]
        stages += 1

    return summaries, stages


def analyze_repository(extract_dir: Path) -> dict:
    started = time.monotonic()
    files = collect_analysis_files(extract_dir)
    if not files:
        raise NoAnalysableFilesError(
            "No analysable source, configuration, or documentation files were "
            "found in this repository."
        )

    budget = calculate_context_budget()
    estimated_repository_tokens = estimate_tokens(
        sum(file["characters"] for file in files)
    )
    files_prompt_tokens = (
        estimate_text_tokens(format_file_blocks(files)) if files else 0
    )

    if files_prompt_tokens <= budget.available_input_tokens:
        analysis = send_message(
            build_single_analysis_prompt(files),
            timeout=ANALYSIS_REQUEST_TIMEOUT,
            options=_request_options(budget),
        )
        strategy = "single_request"
        batches_processed = 0
        hierarchy_stages = 0
    else:
        sections = _build_sections(files, budget.available_input_tokens)
        batches = _group_sections(
            sections, budget.available_input_tokens
        )
        summaries = [
            send_message(
                build_batch_summary_prompt(
                    batch, index, len(batches)
                ),
                timeout=ANALYSIS_REQUEST_TIMEOUT,
                options=_request_options(budget),
            )
            for index, batch in enumerate(batches, start=1)
        ]
        summaries, hierarchy_stages = _reduce_summaries(summaries, budget)
        analysis = send_message(
            build_final_synthesis_prompt(summaries),
            timeout=ANALYSIS_REQUEST_TIMEOUT,
            options=_request_options(budget),
        )
        strategy = "hierarchical_summarization"
        batches_processed = len(batches)

    return {
        "analysis": analysis,
        "metadata": {
            "strategy": strategy,
            "total_files": len(files),
            "estimated_repository_tokens": estimated_repository_tokens,
            "provider": budget.provider,
            "model": budget.model,
            "context_capacity": budget.context_length,
            "context_source": budget.context_source,
            "available_input_tokens": budget.available_input_tokens,
            "reserved_tokens": budget.reserved_metadata(),
            "batches_processed": batches_processed,
            "hierarchy_stages": hierarchy_stages,
            "elapsed_seconds": round(time.monotonic() - started, 2),
        },
    }
