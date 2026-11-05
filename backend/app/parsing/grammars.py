"""Tree-sitter grammar loading and language detection."""

import importlib
import importlib.metadata
from functools import lru_cache

LANGUAGE_BY_EXTENSION = {
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".mts": "typescript",
    ".cts": "typescript",
    ".tsx": "tsx",
    ".json": "json",
}

SUPPORTED_LANGUAGES = ("javascript", "typescript", "tsx", "json")

GRAMMAR_PACKAGES = {
    "javascript": ("tree_sitter_javascript", ("language",)),
    "typescript": ("tree_sitter_typescript", ("language_typescript", "language")),
    "tsx": ("tree_sitter_typescript", ("language_tsx",)),
    "json": ("tree_sitter_json", ("language",)),
}


class TreeSitterUnavailableError(Exception):
    pass


def language_for_path(file_path: str) -> str | None:
    dot = file_path.rfind(".")
    if dot == -1:
        return None
    return LANGUAGE_BY_EXTENSION.get(file_path[dot:].lower())


def is_supported_path(file_path: str) -> bool:
    return language_for_path(file_path) is not None


@lru_cache(maxsize=8)
def _load_language(language: str):
    from tree_sitter import Language

    package, attribute_names = GRAMMAR_PACKAGES[language]

    try:
        module = importlib.import_module(package)
    except ImportError as exc:
        raise TreeSitterUnavailableError(
            f"The '{package}' package is not installed ({exc})."
        ) from exc

    for attribute in attribute_names:
        factory = getattr(module, attribute, None)
        if factory is None:
            continue

        capsule = factory()
        try:
            return Language(capsule)
        except (TypeError, ValueError):
            # Newer tree-sitter releases also require the language name.
            try:
                return Language(capsule, language)
            except (TypeError, ValueError) as exc:
                raise TreeSitterUnavailableError(
                    f"Could not load the {language} grammar: {exc}"
                ) from exc

    raise TreeSitterUnavailableError(
        f"No usable grammar function was found in '{package}'."
    )


@lru_cache(maxsize=8)
def _load_parser(language: str):
    from tree_sitter import Parser

    grammar = _load_language(language)

    try:
        return Parser(grammar)
    except (TypeError, ValueError):
        parser = Parser()
        parser.set_language(grammar)
        return parser


def parser_for(language: str):
    if language not in GRAMMAR_PACKAGES:
        return None
    return _load_parser(language)


def grammar_versions() -> dict[str, str]:
    versions = {}
    for package in {name for name, _ in GRAMMAR_PACKAGES.values()}:
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = "not installed"

    try:
        versions["tree_sitter"] = importlib.metadata.version("tree-sitter")
    except importlib.metadata.PackageNotFoundError:
        versions["tree_sitter"] = "not installed"

    return versions


def is_available() -> bool:
    """True when at least one grammar loads, so files still get parsed."""
    return any(_loads(language) for language in SUPPORTED_LANGUAGES)


def _loads(language: str) -> bool:
    try:
        return parser_for(language) is not None
    except Exception:
        return False
