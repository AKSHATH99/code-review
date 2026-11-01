from pathlib import PurePosixPath
from pathlib import Path

from app.chunks import SKIP_DIRS, repository_root
from app.files import list_repository_files
from app.stats import estimate_text_tokens

# Uppercase variants match case-sensitive directory names during the walk;
# _is_relevant compares lowercased parts.
ANALYSIS_SKIP_DIRS = {
    ".cache",
    ".gradle",
    ".idea",
    ".next",
    ".nuxt",
    ".nyc_output",
    ".output",
    ".parcel-cache",
    ".svelte-kit",
    ".turbo",
    ".vercel",
    ".vscode",
    "coverage",
    "deriveddata",
    "DerivedData",
    "htmlcov",
    "out",
    "pods",
    "Pods",
    "storybook-static",
    "target",
    "vendor",
}

LOCKFILE_NAMES = {
    "bun.lock",
    "bun.lockb",
    "cargo.lock",
    "cartfile.resolved",
    "composer.lock",
    "flake.lock",
    "gemfile.lock",
    "go.sum",
    "gradle.lockfile",
    "mix.lock",
    "npm-shrinkwrap.json",
    "package-lock.json",
    "packages.lock.json",
    "pdm.lock",
    "pipfile.lock",
    "pnpm-lock.yaml",
    "podfile.lock",
    "poetry.lock",
    "project.assets.json",
    "pubspec.lock",
    "uv.lock",
    "yarn.lock",
}

SOURCE_SUFFIXES = {
    ".adoc",
    ".asm",
    ".astro",
    ".bash",
    ".bat",
    ".c",
    ".cc",
    ".cfg",
    ".clj",
    ".cljs",
    ".cmake",
    ".cmd",
    ".conf",
    ".cpp",
    ".cs",
    ".css",
    ".cxx",
    ".dart",
    ".erl",
    ".ex",
    ".exs",
    ".fish",
    ".fs",
    ".go",
    ".gql",
    ".gradle",
    ".graphql",
    ".groovy",
    ".h",
    ".hcl",
    ".hh",
    ".hpp",
    ".hrl",
    ".htm",
    ".html",
    ".hxx",
    ".ini",
    ".ipynb",
    ".java",
    ".jl",
    ".js",
    ".json",
    ".jsonc",
    ".jsx",
    ".kt",
    ".kts",
    ".less",
    ".lua",
    ".m",
    ".md",
    ".mdx",
    ".mk",
    ".mm",
    ".mjs",
    ".nix",
    ".php",
    ".plist",
    ".prisma",
    ".properties",
    ".proto",
    ".ps1",
    ".py",
    ".pyi",
    ".r",
    ".rb",
    ".rs",
    ".rst",
    ".sass",
    ".sbt",
    ".scala",
    ".scss",
    ".sh",
    ".sol",
    ".sql",
    ".svelte",
    ".sv",
    ".swift",
    ".tf",
    ".tfvars",
    ".toml",
    ".ts",
    ".tsx",
    ".txt",
    ".v",
    ".vb",
    ".vhd",
    ".vhdl",
    ".vue",
    ".xml",
    ".yaml",
    ".yml",
    ".zsh",
}

CONFIG_FILENAMES = {
    ".babelrc",
    ".dockerignore",
    ".editorconfig",
    ".env.example",
    ".env.sample",
    ".env.template",
    ".eslintrc",
    ".gitattributes",
    ".gitignore",
    ".npmrc",
    ".nvmrc",
    ".prettierrc",
    ".python-version",
    ".ruby-version",
    ".stylelintrc",
    ".tool-versions",
    "authors",
    "brewfile",
    "changelog",
    "cmakelists.txt",
    "codeowners",
    "contributing",
    "copying",
    "dockerfile",
    "gemfile",
    "gnumakefile",
    "install",
    "jenkinsfile",
    "justfile",
    "licence",
    "license",
    "makefile",
    "notice",
    "pipfile",
    "procfile",
    "rakefile",
    "readme",
    "security",
    "todo",
    "vagrantfile",
}


class AnalysisCollectionError(Exception):
    pass


def _is_relevant(file_path: str) -> bool:
    path = PurePosixPath(file_path)
    name = path.name.lower()

    if any(part.lower() in ANALYSIS_SKIP_DIRS for part in path.parts[:-1]):
        return False

    if name in LOCKFILE_NAMES or name.endswith(".lock"):
        return False

    if name.startswith(".env") and not name.endswith(
        (".example", ".sample", ".template")
    ):
        return False

    if name.endswith((".min.js", ".min.css", ".map", ".snap")):
        return False

    return path.suffix.lower() in SOURCE_SUFFIXES or name in CONFIG_FILENAMES


def collect_analysis_files(extract_dir: Path) -> list[dict]:
    root = repository_root(extract_dir)
    skip_dirs = SKIP_DIRS | ANALYSIS_SKIP_DIRS
    listed = list_repository_files(extract_dir, skip_dirs=skip_dirs)

    files = []
    for entry in listed:
        if not _is_relevant(entry["file_path"]):
            continue

        path = root / entry["file_path"]
        try:
            content = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise AnalysisCollectionError(
                f"Could not read {entry['file_path']}: {exc}"
            ) from exc

        files.append(
            {
                "file_path": entry["file_path"],
                "size": entry["size"],
                "content": content,
                "characters": len(content),
                "lines": len(content.splitlines()),
                "estimated_tokens": estimate_text_tokens(content),
            }
        )

    return files
