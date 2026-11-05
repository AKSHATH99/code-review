"""Per-repository ingestion reports for the Tree-sitter chunking pipeline."""

from pathlib import Path

from app.chunks import chunk_repository
from app.parsing.grammars import (
    SUPPORTED_LANGUAGES,
    grammar_versions,
    is_available,
)
from app.structural_chunks import (
    MAX_SPLIT_DEPTH,
    STRUCTURAL_MODE,
    max_chunk_characters,
    text_chunk_characters,
    text_chunk_overlap_characters,
)

MAX_FILE_ROWS = 300

REPORTS: dict[str, dict] = {}


def new_report(repository: str) -> dict:
    return {
        "repository": repository,
        "tree_sitter_available": is_available(),
        "supported_languages": list(SUPPORTED_LANGUAGES),
        "grammar_versions": grammar_versions(),
        "limits": {
            "max_chunk_characters": max_chunk_characters(),
            "text_chunk_characters": text_chunk_characters(),
            "text_chunk_overlap_characters": text_chunk_overlap_characters(),
            "max_split_depth": MAX_SPLIT_DEPTH,
        },
        "files_scanned": 0,
        "files_skipped": 0,
        "files_supported": 0,
        "files_parsed": 0,
        "files_with_errors": 0,
        "files_text_chunked": 0,
        "structures_extracted": 0,
        "chunks_generated": 0,
        "chunks_embedded": 0,
        "chunks_by_type": {},
        "languages_seen": {},
        "files": [],
        "files_truncated": False,
    }


def record_file(report: dict, stats: dict) -> None:
    report["files_scanned"] += 1

    if stats["supported"]:
        report["files_supported"] += 1

    if stats["parsed"]:
        report["files_parsed"] += 1

    if stats["has_errors"] or stats.get("parse_error"):
        report["files_with_errors"] += 1

    if stats["mode"] != STRUCTURAL_MODE:
        report["files_text_chunked"] += 1

    report["structures_extracted"] += stats["structures"]
    report["chunks_generated"] += stats["chunks"]

    if stats["language"]:
        report["languages_seen"][stats["language"]] = (
            report["languages_seen"].get(stats["language"], 0) + 1
        )

    for chunk_type, count in stats.get("chunk_type_counts", {}).items():
        report["chunks_by_type"][chunk_type] = (
            report["chunks_by_type"].get(chunk_type, 0) + count
        )

    if len(report["files"]) < MAX_FILE_ROWS:
        report["files"].append(
            {
                "file_path": stats["file_path"],
                "mode": stats["mode"],
                "language": stats["language"],
                "structures": stats["structures"],
                "chunks": stats["chunks"],
                "has_errors": stats["has_errors"],
            }
        )
    else:
        report["files_truncated"] = True


def store_report(report: dict) -> None:
    REPORTS[report["repository"]] = report


def get_report(repository: str) -> dict | None:
    return REPORTS.get(repository)


def mark_embedded(repository: str, count: int) -> None:
    report = get_report(repository)
    if report is not None:
        report["chunks_embedded"] = count


def build_report(extract_dir: Path, repository: str) -> dict:
    """Chunk the whole repository once and record how the pipeline behaved."""
    report = new_report(repository)
    chunk_repository(extract_dir, report)
    store_report(report)
    return report
