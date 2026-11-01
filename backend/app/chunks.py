import os
from pathlib import Path

DEFAULT_CHUNK_SIZE = 20
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


def chunk_text(
    file_path: str, text: str, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[dict]:
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1.")

    lines = text.splitlines()
    chunks = []

    for chunk_index, start in enumerate(range(0, len(lines), chunk_size)):
        chunk_lines = lines[start : start + chunk_size]
        chunks.append(
            {
                "file_path": file_path,
                "chunk_index": chunk_index,
                "start_line": start + 1,
                "end_line": start + len(chunk_lines),
                "content": "\n".join(chunk_lines),
            }
        )

    return chunks


def repository_root(extract_dir: Path) -> Path:
    entries = list(extract_dir.iterdir())
    if len(entries) == 1 and entries[0].is_dir():
        return entries[0]
    return extract_dir


def chunk_repository(
    extract_dir: Path, chunk_size: int = DEFAULT_CHUNK_SIZE
) -> list[dict]:
    chunks = []
    walk_root = repository_root(extract_dir)

    for root, dirs, files in os.walk(walk_root):
        dirs[:] = sorted(
            directory for directory in dirs if directory not in SKIP_DIRS
        )

        for file_name in sorted(files):
            path = Path(root) / file_name
            if path.is_symlink():
                continue

            try:
                data = path.read_bytes()
            except OSError:
                continue

            if b"\x00" in data[:8192]:
                continue

            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                continue

            relative_path = path.relative_to(walk_root).as_posix()
            chunks.extend(chunk_text(relative_path, text, chunk_size))

    return chunks
