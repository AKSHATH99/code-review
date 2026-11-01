import os
from pathlib import Path

from app.chunks import SKIP_DIRS, repository_root

MAX_FILE_BYTES = 1024 * 1024


class RepositoryFileError(Exception):
    pass


class UnsafeFilePathError(RepositoryFileError):
    pass


class RepositoryFileNotFoundError(RepositoryFileError):
    pass


class RepositoryFileTooLargeError(RepositoryFileError):
    pass


class UnsupportedFileError(RepositoryFileError):
    pass


def list_repository_files(
    extract_dir: Path, skip_dirs: set[str] = SKIP_DIRS
) -> list[dict]:
    root = repository_root(extract_dir)
    files = []

    for current_dir, dirs, names in os.walk(root):
        dirs[:] = sorted(
            directory for directory in dirs if directory not in skip_dirs
        )

        for name in sorted(names):
            path = Path(current_dir) / name
            if path.is_symlink():
                continue

            try:
                data = path.read_bytes()
            except OSError:
                continue

            if b"\x00" in data[:8192]:
                continue

            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                continue

            files.append(
                {
                    "file_path": path.relative_to(root).as_posix(),
                    "size": len(data),
                }
            )

    files.sort(key=lambda item: item["file_path"].lower())
    return files


def read_repository_file(extract_dir: Path, file_path: str) -> dict:
    root = repository_root(extract_dir).resolve()
    normalized = file_path.strip().replace("\\", "/")
    parts = Path(normalized).parts

    if (
        not normalized
        or normalized.startswith("/")
        or any(part in {"", ".", ".."} or part in SKIP_DIRS for part in parts)
    ):
        raise UnsafeFilePathError("Invalid repository file path.")

    candidate = root / normalized
    if candidate.is_symlink():
        raise UnsafeFilePathError("Invalid repository file path.")

    target = candidate.resolve()
    if not target.is_relative_to(root):
        raise UnsafeFilePathError("Invalid repository file path.")

    if not target.is_file():
        raise RepositoryFileNotFoundError(
            f"File {normalized} was not found in the repository."
        )

    size = target.stat().st_size
    if size > MAX_FILE_BYTES:
        raise RepositoryFileTooLargeError(
            f"File {normalized} is too large to read (limit 1 MB)."
        )

    try:
        data = target.read_bytes()
    except OSError as exc:
        raise RepositoryFileError(f"Could not read {normalized}: {exc}") from exc

    if b"\x00" in data[:8192]:
        raise UnsupportedFileError(
            f"File {normalized} is not a UTF-8 text file."
        )

    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedFileError(
            f"File {normalized} is not a UTF-8 text file."
        ) from exc

    return {
        "file_path": target.relative_to(root).as_posix(),
        "size": len(data),
        "content": content,
    }
