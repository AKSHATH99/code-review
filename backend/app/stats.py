from math import ceil
from pathlib import Path

from app.chunks import repository_root
from app.files import list_repository_files

CHARS_PER_TOKEN = 4
DEFAULT_LARGEST_FILES = 10


def estimate_tokens(characters: int) -> int:
    return ceil(characters / CHARS_PER_TOKEN)


def estimate_text_tokens(text: str) -> int:
    return estimate_tokens(len(text))


def compute_repository_stats(
    extract_dir: Path, largest_limit: int = DEFAULT_LARGEST_FILES
) -> dict:
    root = repository_root(extract_dir)
    files = list_repository_files(extract_dir)

    total_lines = 0
    total_characters = 0
    entries = []

    for file in files:
        try:
            text = (root / file["file_path"]).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue

        line_count = len(text.splitlines())
        character_count = len(text)

        total_lines += line_count
        total_characters += character_count
        entries.append(
            {
                "file_path": file["file_path"],
                "size": file["size"],
                "lines": line_count,
                "characters": character_count,
            }
        )

    largest_files = sorted(
        entries,
        key=lambda entry: (-entry["size"], entry["file_path"].lower()),
    )[:largest_limit]

    return {
        "total_files": len(files),
        "total_lines": total_lines,
        "total_characters": total_characters,
        "estimated_tokens": estimate_tokens(total_characters),
        "token_estimate_method": f"characters / {CHARS_PER_TOKEN}",
        "largest_files": largest_files,
    }
