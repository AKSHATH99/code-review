import os
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    "node_modules",
    "dist",
    "build",
    "venv",
    ".venv",
    "env",
    ".tox",
    "__pycache__",
}


def repository_root(extract_dir: Path) -> Path:
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


def chunk_repository(
    extract_dir: Path,
    report: dict | None = None,
) -> list[dict]:
    # Imported here because app.ingestion reads chunk_repository from this
    # module, and a top-level import would be circular.
    from app import ingestion
    from app.structural_chunks import chunk_source

    chunks = []
    walk_root = repository_root(extract_dir)

    for root, dirs, files in os.walk(walk_root):
        dirs[:] = sorted(
            directory for directory in dirs if directory not in SKIP_DIRS
        )

        for file_name in sorted(files):
            path = Path(root) / file_name
            if path.is_symlink():
                if report is not None:
                    report["files_skipped"] += 1
                continue

            try:
                data = path.read_bytes()
            except OSError:
                if report is not None:
                    report["files_skipped"] += 1
                continue

            if b"\x00" in data[:8192]:
                if report is not None:
                    report["files_skipped"] += 1
                continue

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                if report is not None:
                    report["files_skipped"] += 1
                continue

            relative_path = path.relative_to(walk_root).as_posix()
            file_chunks, file_stats = chunk_source(relative_path, text)

            if report is not None:
                ingestion.record_file(report, file_stats)

            for index, chunk in enumerate(file_chunks):
                chunk["chunk_index"] = index
                chunks.append(chunk)

    return chunks
