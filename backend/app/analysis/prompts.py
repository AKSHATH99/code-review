SYSTEM_INSTRUCTIONS = (
    "You are a senior software engineer performing a careful repository review. "
    "Base every statement on the supplied repository content. Do not invent "
    "features, files, APIs, or behaviour that the content does not support. "
    "Clearly distinguish confirmed implementation details from assumptions."
)

FINAL_ANALYSIS_INSTRUCTIONS = (
    "Produce a repository-level analysis that explains:\n"
    "- What the project does, its main purpose, and its functionality.\n"
    "- The technologies, frameworks, and libraries used.\n"
    "- The frontend and backend architecture where applicable.\n"
    "- Important modules and their responsibilities.\n"
    "- How major components interact.\n"
    "- The main entry points and important files.\n"
    "- The overall repository structure.\n"
    "Reference repository-relative file paths. Mark anything inferred as an "
    "assumption. Never invent functionality that the repository content does "
    "not support."
)

BATCH_SUMMARY_INSTRUCTIONS = (
    "You are analysing one batch of repository files for a later repository-level "
    "synthesis. Summarise the batch and preserve:\n"
    "- Repository-relative file paths.\n"
    "- The main responsibility of each file or module.\n"
    "- Important functions, classes, exports, and APIs.\n"
    "- Technologies and libraries visible in the content.\n"
    "- Important relationships between components, including cross-file usage.\n"
    "- Relevant implementation details, configuration, and entry points.\n"
    "Do not omit files. Stay grounded in the supplied content and mark uncertain "
    "inferences as assumptions."
)

SUMMARY_MERGE_INSTRUCTIONS = (
    "Merge the following intermediate repository summaries into one compact, "
    "information-dense summary. Preserve distinct file paths, module "
    "responsibilities, important functions and classes, technologies, "
    "component relationships, and relevant implementation details. Do not "
    "invent information and mark uncertain inferences as assumptions."
)


def format_file_block(item: dict) -> str:
    label = f"=== File: {item['file_path']}"
    if item.get("start_line") is not None:
        label += f" (lines {item['start_line']}-{item['end_line']})"
    return f"{label} ===\n{item['content']}"


def format_file_blocks(items: list[dict]) -> str:
    return "\n\n".join(format_file_block(item) for item in items)


def build_single_analysis_prompt(files: list[dict]) -> str:
    return "\n\n".join(
        [
            SYSTEM_INSTRUCTIONS,
            FINAL_ANALYSIS_INSTRUCTIONS,
            f"Repository content ({len(files)} files):",
            format_file_blocks(files),
        ]
    )


def build_batch_summary_prompt(
    items: list[dict], batch_number: int, batch_total: int
) -> str:
    return "\n\n".join(
        [
            SYSTEM_INSTRUCTIONS,
            BATCH_SUMMARY_INSTRUCTIONS,
            f"Batch {batch_number} of {batch_total}.",
            format_file_blocks(items),
        ]
    )


def build_merge_summary_prompt(
    summaries: list[str], target_tokens: int
) -> str:
    body = "\n\n".join(
        f"--- Summary {index} ---\n{summary}"
        for index, summary in enumerate(summaries, start=1)
    )
    return "\n\n".join(
        [
            SYSTEM_INSTRUCTIONS,
            SUMMARY_MERGE_INSTRUCTIONS,
            f"Keep the merged summary under about {target_tokens} tokens.",
            body,
        ]
    )


def build_final_synthesis_prompt(summaries: list[str]) -> str:
    body = "\n\n".join(
        f"--- Summary {index} ---\n{summary}"
        for index, summary in enumerate(summaries, start=1)
    )
    return "\n\n".join(
        [
            SYSTEM_INSTRUCTIONS,
            FINAL_ANALYSIS_INSTRUCTIONS,
            "The intermediate summaries below are the complete record of the "
            "repository. Use them to produce the final analysis without dropping "
            "important files or responsibilities.",
            body,
        ]
    )
