from app.chunks import DEFAULT_CHUNK_SIZE
from app.llm import (
    LONG_REQUEST_TIMEOUT,
    get_model_name,
    provider_name,
    send_message,
)
from app.search import search_chunks

CONTEXT_TOP_K = 15

PROMPT_INSTRUCTIONS = (
    "You are a repository assistant. Answer the user's question using only the "
    "repository context supplied below. When the context supports it, reference "
    "the source file path and line range. If the context is insufficient to "
    "answer, say so clearly instead of guessing."
)


def build_repository_prompt(
    question: str, chunks: list[dict], attachment: dict | None = None
) -> str:
    lines = [
        PROMPT_INSTRUCTIONS,
        "",
        "Question:",
        question,
        "",
        "Repository context:",
    ]

    for index, chunk in enumerate(chunks, start=1):
        lines.extend(
            [
                f"[{index}] File: {chunk['file_path']} "
                f"(lines {chunk['start_line']}-{chunk['end_line']})",
                chunk["content"],
                "",
            ]
        )

    if attachment:
        lines.extend(
            [
                "Additional file selected by the user:",
                f"File: {attachment['file_path']}",
                attachment["content"],
                "",
            ]
        )

    lines.append("Answer:")
    return "\n".join(lines)


def answer_repository_question(
    repository: str, question: str, attachment: dict | None = None
) -> dict:
    total_chunks, sources = search_chunks(
        repository, DEFAULT_CHUNK_SIZE, question, limit=CONTEXT_TOP_K
    )
    prompt = build_repository_prompt(question, sources, attachment)
    provider = provider_name()
    model = get_model_name()

    return {
        "repository": repository,
        "question": question,
        "provider": provider,
        "model": model,
        "total_chunks": total_chunks,
        "answer": send_message(prompt, timeout=LONG_REQUEST_TIMEOUT),
        "sources": sources,
    }
