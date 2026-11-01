import json
import os
import re
import tempfile
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

GITHUB_HOSTS = {"github.com", "www.github.com"}
DOWNLOAD_HOSTS = GITHUB_HOSTS | {"codeload.github.com"}
REPOSITORY_PATH = re.compile(r"^/([A-Za-z0-9-]{1,39})/([A-Za-z0-9._-]{1,100})/?$")
CHUNK_SIZE = 1024 * 1024
DEFAULT_STORAGE_DIR = Path(__file__).resolve().parent.parent / "storage"


class GithubDownloadError(Exception):
    pass


class RepositoryNotFoundError(Exception):
    pass


class GithubLookupError(Exception):
    pass


class ZipExtractionError(Exception):
    pass


def parse_github_repo_url(repo_url: str) -> str:
    try:
        parsed = urllib.parse.urlparse(repo_url.strip())
    except ValueError as exc:
        raise ValueError("Invalid repository URL.") from exc

    if (
        parsed.scheme not in ("http", "https")
        or parsed.netloc.lower() not in GITHUB_HOSTS
    ):
        raise ValueError(
            "Repository URL must point to https://github.com/<owner>/<repo>."
        )

    match = REPOSITORY_PATH.fullmatch(parsed.path)
    if match is None:
        raise ValueError(
            "Repository URL must point to https://github.com/<owner>/<repo>."
        )

    owner, repo = match.groups()
    repo = repo.removesuffix(".git")
    if not repo or repo in {".", ".."}:
        raise ValueError("Repository URL must include a valid repository name.")

    return f"{owner}/{repo}"


def storage_dir() -> Path:
    configured = os.getenv("STORAGE_DIR")
    directory = Path(configured or DEFAULT_STORAGE_DIR).expanduser().resolve()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def repository_extract_dir(repository: str) -> Path:
    return storage_dir() / repository.replace("/", "-")


def download_repository_zip(repo_url: str) -> tuple[str, Path]:
    repository = parse_github_repo_url(repo_url)
    archive_name = f"{repository.replace('/', '-')}.zip"

    try:
        zip_path = storage_dir() / archive_name
    except OSError as exc:
        raise GithubDownloadError(
            f"Could not access the repository storage directory: {exc}"
        ) from exc

    if zip_path.is_file():
        return repository, zip_path

    archive_url = f"https://github.com/{repository}/archive/HEAD.zip"
    request = urllib.request.Request(
        archive_url, headers={"User-Agent": "GitScope/0.1"}
    )
    temp_path = None

    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            final_host = urllib.parse.urlparse(response.geturl()).netloc.lower()
            if final_host not in DOWNLOAD_HOSTS:
                raise GithubDownloadError(f"Unexpected archive host: {final_host}")

            with tempfile.NamedTemporaryFile(
                dir=zip_path.parent,
                prefix=f".{archive_name}.",
                suffix=".part",
                delete=False,
            ) as archive:
                temp_path = Path(archive.name)
                while chunk := response.read(CHUNK_SIZE):
                    archive.write(chunk)

        os.replace(temp_path, zip_path)
        temp_path = None
    except GithubDownloadError:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise
    except OSError as exc:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
        raise GithubDownloadError(
            f"Failed to download {repository} from GitHub: {exc}"
        ) from exc

    return repository, zip_path


def extract_repository_zip(zip_path: Path) -> Path:
    extract_dir = zip_path.parent / zip_path.stem

    try:
        extract_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ZipExtractionError(
            f"Could not create extraction directory: {exc}"
        ) from exc

    try:
        with zipfile.ZipFile(zip_path) as archive:
            root = extract_dir.resolve()
            for member in archive.infolist():
                member_name = member.filename.replace("\\", "/")
                target = (extract_dir / member_name).resolve()
                if not target.is_relative_to(root):
                    raise ZipExtractionError(
                        f"Unsafe path in archive: {member.filename}"
                    )

            archive.extractall(extract_dir)
    except ZipExtractionError:
        raise
    except (zipfile.BadZipFile, RuntimeError, OSError, ValueError) as exc:
        raise ZipExtractionError(
            f"Failed to extract {zip_path.name}: {exc}"
        ) from exc

    return extract_dir


def fetch_repository_details(repo_url: str) -> dict:
    repository = parse_github_repo_url(repo_url)
    api_url = f"https://api.github.com/repos/{repository}"
    request = urllib.request.Request(
        api_url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "GitScope/0.1",
        },
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RepositoryNotFoundError(
                f"Repository {repository} was not found on GitHub."
            ) from exc
        raise GithubLookupError(
            f"GitHub returned HTTP {exc.code} while fetching {repository} details."
        ) from exc
    except OSError as exc:
        raise GithubLookupError(
            f"Failed to fetch {repository} details: {exc}"
        ) from exc

    owner, name = repository.split("/")
    owner_data = data.get("owner") or {}

    return {
        "repository": repository,
        "owner": owner_data.get("login") or owner,
        "name": data.get("name") or name,
        "description": data.get("description"),
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "language": data.get("language"),
        "default_branch": data.get("default_branch"),
        "updated_at": data.get("updated_at"),
        "html_url": f"https://github.com/{repository}",
    }
