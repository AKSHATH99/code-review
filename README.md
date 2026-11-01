# GitScope

AI-powered GitHub repository intelligence.

This repository currently contains a React + Vite frontend and a FastAPI
backend. The frontend downloads a public repository, shows its metadata and
source statistics, and displays line-based source chunks with local embeddings. A single
**Ask the repository** question input reuses the semantic search to retrieve the
fifteen most relevant chunks and sends their code text to the selected generation
provider (Gemini when `GEMINI_API_KEY` is set, otherwise local Ollama) together
with the question, and displays the answer alongside the retrieved sources. A
separate **Repository analysis** panel sends the complete set of relevant
repository files to the same provider, using context-budgeted batching and
hierarchical summaries when the repository is too large for one request.
Embeddings and retrieval stay local; no vector database is used.

## Project structure

```
GitScope/
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── components/
│   │   │   ├── FileSidebar.jsx
│   │   │   ├── RepositoryCard.jsx
│   │   │   └── StatusBadge.jsx
│   │   ├── services/
│   │   │   └── api.js
│   │   ├── App.jsx
│   │   ├── index.css
│   │   └── main.jsx
│   ├── .env.example
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── routes/
│   │   │   ├── __init__.py
│   │   │   ├── analysis.py
│   │   │   ├── ollama.py
│   │   │   └── repositories.py
│   │   ├── analysis/
│   │   │   ├── __init__.py
│   │   │   ├── budget.py
│   │   │   ├── collector.py
│   │   │   ├── pipeline.py
│   │   │   └── prompts.py
│   │   ├── __init__.py
│   │   ├── chunks.py
│   │   ├── embeddings.py
│   │   ├── files.py
│   │   ├── gemini.py
│   │   ├── github.py
│   │   ├── llm.py
│   │   ├── llm_errors.py
│   │   ├── main.py
│   │   ├── ollama.py
│   │   ├── qa.py
│   │   ├── search.py
│   │   └── stats.py
│   ├── storage/          # downloaded ZIP archives (generated, gitignored)
│   ├── tests/
│   ├── .env.example
│   └── requirements.txt
├── .gitignore
└── README.md
```

## Prerequisites

- Node.js 20.19+ (or 22.12+) and npm
- Python 3.10+ with `venv` support
- A generation provider: a Gemini API key, or Ollama running locally

## Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
# CPU-only PyTorch keeps the install smaller if you do not have a GPU.
pip install --index-url https://download.pytorch.org/whl/cpu torch
pip install -r requirements.txt
```

Optional configuration:

```bash
cp .env.example .env
```

Run the API:

```bash
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000
```

- Health check: <http://localhost:8000/health>
- Interactive docs: <http://localhost:8000/docs>

Expected response from `/health`:

```json
{
  "status": "ok",
  "service": "gitscope-api"
}
```

## Generation provider

All natural-language generation (repository Q&A, the fixed test message,
`/chat`, and repository analysis) goes through a small provider layer in
`app/llm.py`.

| `LLM_PROVIDER` | Behaviour                                                  |
| -------------- | ---------------------------------------------------------- |
| `auto` (default) | Gemini when `GEMINI_API_KEY` is set, otherwise Ollama    |
| `gemini`       | Always Gemini; a missing key is a configuration error      |
| `ollama`       | Always local Ollama                                        |

Gemini requests use
`POST https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent`
with the `x-goog-api-key` header. The default model is `gemini-3.6-flash`; set
`GEMINI_MODEL` to use another model. For Flash and Lite models the request
disables thinking (`thinkingConfig.thinkingBudget: 0`) so reasoning tokens do
not consume the reserved output budget. Gemini input limits come from the model
metadata endpoint (`gemini_model_info:inputTokenLimit`); set `GEMINI_NUM_CTX`
to override that value for repository analysis.

Ollama behavior is unchanged: chats go to
`POST {OLLAMA_BASE_URL}/api/chat`, and analysis reads the runtime context from
`/api/ps` (sending a one-token warm-up request if the model is not loaded), then
falls back to `/api/show`.

Embeddings (`all-MiniLM-L6-v2`) and semantic search remain local in every
configuration. Neither provider receives embedding vectors. Configuration
errors (missing key, unknown model) return `500`; connection failures,
timeouts, rate limits, and other upstream errors return `502`.

## Repository download and extraction API

`POST /repositories/download` accepts a public GitHub repository URL, downloads
the default branch archive from GitHub on first use, saves it in the configured
storage directory, and extracts it next to the archive.

```bash
curl -X POST http://localhost:8000/repositories/download \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/octocat/Hello-World"}'
```

Successful response:

```json
{
  "status": "ok",
  "repository": "octocat/Hello-World",
  "zip_path": "/absolute/path/to/backend/storage/octocat-Hello-World.zip",
  "extract_dir": "/absolute/path/to/backend/storage/octocat-Hello-World"
}
```

- `400` — the URL is not a GitHub repository URL.
- `500` — the archive could not be extracted (corrupt archive or unsafe path).
- `502` — GitHub rejected the request or the download failed (for example, a
  missing or private repository).

The archive is named `<owner>-<repo>.zip` and stored in `STORAGE_DIR`
(default: `backend/storage`). Before downloading, the API checks whether that
file already exists and returns the existing path without calling GitHub.
Delete the file to force a fresh download.

Extraction reuses that cached ZIP and writes into `<owner>-<repo>` next to it.
Every archive member is resolved and checked against the extraction directory
first, so entries that escape it (for example `../file`) are rejected with a
`500` and nothing is extracted.

### Repository details

`GET /repositories/details?repo_url=...` returns metadata from the GitHub API.

```bash
curl "http://localhost:8000/repositories/details?repo_url=https%3A%2F%2Fgithub.com%2Foctocat%2FHello-World"
```

```json
{
  "repository": "octocat/Hello-World",
  "owner": "octocat",
  "name": "Hello-World",
  "description": "My first repository on GitHub!",
  "stars": 3871,
  "forks": 7249,
  "language": null,
  "default_branch": "master",
  "updated_at": "2026-10-28T16:44:39Z",
  "html_url": "https://github.com/octocat/Hello-World"
}
```

- `400` — the URL is not a GitHub repository URL.
- `404` — the repository does not exist or is not public.
- `502` — GitHub rejected the request or could not be reached.

Details use the public GitHub API, which allows 60 unauthenticated requests per
hour per IP address.

### Source chunks

`GET /repositories/chunks?repo_url=...` reads the already extracted repository,
splits every text file into line-based chunks, and returns them. It does not
download or extract anything, so the repository must be downloaded first.

```bash
curl "http://localhost:8000/repositories/chunks?repo_url=https%3A%2F%2Fgithub.com%2Foctocat%2FSpoon-Knife"
```

```json
{
  "repository": "octocat/Spoon-Knife",
  "chunk_size": 20,
  "total_chunks": 3,
  "chunks": [
    {
      "file_path": "README.md",
      "chunk_index": 0,
      "start_line": 1,
      "end_line": 9,
      "content": "### Well hello there!\n..."
    }
  ]
}
```

- `chunk_size` is optional (default `20`) and must be at least `1`.
- `file_path` is relative to the repository root; the archive's generated
  top-level folder is stripped.
- `chunk_index` starts at `0` per file. `start_line` and `end_line` are 1-based.
- Directories such as `.git`, `node_modules`, `dist`, `build`, and common virtual
  environments are skipped. Binary files (NUL bytes or invalid UTF-8) and
  symlinks are skipped too.
- `400` — the URL is not a GitHub repository URL.
- `404` — the repository has not been downloaded and extracted yet.
- `422` — `chunk_size` is smaller than 1.

The frontend requests chunks automatically after a repository is downloaded.
The panel shows a Queued, Processing, Ready, or Failed badge and displays one
chunk at a time with its file path, chunk index, line range, and a scrollable
code block, plus Previous/Next navigation.

### Repository files

`GET /repositories/files?repo_url=...` lists the UTF-8 text files in the
extracted repository using the same directory and binary-file rules as chunking.
Binary files, symlinks, and skipped directories such as `node_modules` are
omitted.

```json
{
  "repository": "octocat/Hello-World",
  "total_files": 1,
  "files": [
    {
      "file_path": "README.md",
      "size": 78
    }
  ]
}
```

`GET /repositories/file?repo_url=...&path=README.md` returns one file's text.

```json
{
  "repository": "octocat/Hello-World",
  "file_path": "README.md",
  "size": 78,
  "content": "Hello World!\n"
}
```

- The repository must be downloaded and extracted first; otherwise `404`.
- Absolute paths, `..`, skipped directories, and symlinks are rejected with
  `400`. Resolved paths must stay inside the extracted repository.
- Missing files return `404`; non-UTF-8 or binary files return `400`; files
  larger than 1 MB return `413`.
- `file_path` in responses is repository-relative.

### Repository statistics

`GET /repositories/stats?repo_url=...` summarizes the extracted repository's
UTF-8 source files using the same directory and binary-file rules as file
listing and chunking. It reads each file to count lines and characters, then
estimates tokens as characters divided by four.

```bash
curl "http://localhost:8000/repositories/stats?repo_url=https%3A%2F%2Fgithub.com%2Foctocat%2FHello-World"
```

```json
{
  "repository": "octocat/Hello-World",
  "total_files": 1,
  "total_lines": 1,
  "total_characters": 13,
  "estimated_tokens": 4,
  "token_estimate_method": "characters / 4",
  "largest_files": [
    {
      "file_path": "README.md",
      "size": 13,
      "lines": 1,
      "characters": 13
    }
  ]
}
```

- `total_files`, `total_lines`, and `total_characters` cover the same source
  files returned by `GET /repositories/files`.
- `estimated_tokens` is `ceil(total_characters / 4)`. It is an approximation,
  not a tokenizer result.
- `largest_files` is sorted by byte size descending, then path, and includes
  each file's line and character counts. The optional `largest` query parameter
  sets how many files are returned (default `10`, minimum `1`, maximum `50`).
- `400` — invalid repository URL.
- `404` — the repository has not been downloaded and extracted yet.
- `422` — `largest` is outside the allowed range.
- `500` — a source file could not be read.

The frontend requests statistics automatically after the download finishes, so
the panel is populated while chunking and embeddings are still running. It
shows Queued, Processing, Ready, or Failed in place and lists the largest files
with line counts and sizes.

### Chunk embeddings

`POST /repositories/embeddings` chunks the extracted repository with the same
line-based chunker and generates one 384-dimensional embedding per chunk using
the local `all-MiniLM-L6-v2` Sentence Transformers model. No external embedding
API is called, and embeddings are returned in the response only — they are not
persisted.

```bash
curl -X POST http://localhost:8000/repositories/embeddings \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/octocat/Spoon-Knife"}'
```

Abbreviated response:

```json
{
  "repository": "octocat/Spoon-Knife",
  "model": "all-MiniLM-L6-v2",
  "chunk_size": 20,
  "total_chunks": 3,
  "total_embeddings": 3,
  "dimensions": 384,
  "embeddings": [
    {
      "file_path": "README.md",
      "chunk_index": 0,
      "start_line": 1,
      "end_line": 9,
      "values": [0.012345, -0.004321, 0.008765]
    }
  ]
}
```

- `chunk_size` is an optional query parameter (default `20`, minimum `1`), so
  embedding chunks match the chunks endpoint.
- Every embedding keeps its chunk's file path, chunk index, start line, and end
  line. `values` contains all 384 numbers; the example above is shortened.
- `400` — invalid repository URL.
- `404` — the repository has not been downloaded and extracted yet.
- `422` — `chunk_size` is smaller than 1.
- `500` — the model could not be loaded or embedding generation failed.

The model is loaded lazily on the first request and cached in the backend
process, so later requests do not reload it. The first run downloads about 90 MB
of model weights from Hugging Face into the local model cache.

The frontend generates embeddings automatically after chunking finishes. The
panel shows a Queued, Processing, Ready, or Failed badge, and results show the
total chunks processed, embeddings generated, and embedding dimensions, plus a
preview of the first 10 values for one selected embedding. Previous/Next
navigation changes the selected chunk.

### Semantic search

`POST /repositories/search` embeds the question with the same local model and
compares it with the cached chunk embeddings using NumPy cosine similarity. It
returns the five highest-scoring chunks in descending order. The repository is
not re-embedded for each question: `POST /repositories/embeddings` fills an
in-memory cache that search reuses. The endpoint keeps its five-result default;
repository Q&A calls the same function with a higher limit.

```bash
curl -X POST http://localhost:8000/repositories/search \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/AKSHATH99/illustrated-work-gallery", "query": "How are gallery items displayed?"}'
```

Abbreviated response:

```json
{
  "repository": "AKSHATH99/illustrated-work-gallery",
  "query": "How are gallery items displayed?",
  "model": "all-MiniLM-L6-v2",
  "chunk_size": 20,
  "total_chunks": 603,
  "results": [
    {
      "file_path": "src/components/projects/ProjectMedia.tsx",
      "chunk_index": 7,
      "start_line": 141,
      "end_line": 160,
      "content": "...",
      "similarity": 0.3464
    }
  ]
}
```

- Embeddings must be generated first in the same backend process. The cache is
  process-local and is cleared when the backend restarts, so submit the
  repository again after a restart to rebuild it.
- `chunk_size` is an optional query parameter (default `20`). It must match the
  size used to generate the cached embeddings.
- Results include the repository-relative path, chunk index, line range, chunk
  content, and cosine similarity, sorted from highest to lowest.
- `400` — invalid repository URL or empty query.
- `409` — embeddings have not been generated yet.
- `422` — `chunk_size` is smaller than 1.
- `500` — the model could not be loaded or the search failed.

The frontend has no separate search form. The **Ask the repository** panel calls
this endpoint automatically for every question once the download, chunking, and
embedding steps finish, and uses the returned chunks as the model context. The
retrieved chunks appear below the answer as cards with file path, line numbers,
similarity score, and a scrollable code block.

### Generation connectivity test

`POST /api/ollama/test` sends a fixed `Hi` message through the selected
generation provider (`LLM_PROVIDER`) and returns the generated text. It is a
connectivity check only: no repository context, search results, or conversation
history are sent, and nothing is stored.

When using Ollama, make sure it is running and the configured model is
available:

```bash
ollama serve
ollama pull llama3.2:3b
```

Then call the endpoint:

```bash
curl -X POST http://localhost:8000/api/ollama/test
```

```json
{
  "response": "..."
}
```

- `LLM_PROVIDER` selects the provider. With Gemini, the key comes from
  `GEMINI_API_KEY` and the model from `GEMINI_MODEL`. With Ollama, the base URL
  comes from `OLLAMA_BASE_URL` (default `http://localhost:11434`) and the model
  from `OLLAMA_MODEL`.
- Requests are non-streaming. Ollama manages its own model loading, so the first
  request after a model is pulled can take longer while the weights load.
- `500` — required provider configuration is missing.
- `502` — the provider is unreachable, the request timed out, a rate limit was
  hit, or the provider returned an unsuccessful response.

```json
{
  "detail": "Ollama returned HTTP 404. {\"error\":\"model 'llama3.2:3b' not found\"}"
}
```

### Chat

`POST /api/ollama/chat` sends a message supplied by the caller to the selected
generation provider. It includes no repository content, embeddings, or previous
messages. The frontend uses `POST /api/ollama/ask` instead; `/chat` remains
available for direct, context-free prompts.

```bash
curl -X POST http://localhost:8000/api/ollama/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Explain what semantic search is in two sentences."}'
```

```json
{
  "response": "..."
}
```

- `400` — the message is empty or only whitespace.
- `422` — the message is missing or longer than 60000 characters.
- `500` — required provider configuration is missing.
- `502` — the provider is unreachable, the request timed out, or the provider
  returned an unsuccessful response.

### Repository Q&A

`POST /api/ollama/ask` is the endpoint the frontend uses for questions. It
retrieves context with the existing semantic search, builds a prompt from the
retrieved code text, and sends that prompt through the selected generation
provider. It does not re-embed the repository per question, and it never sends
embedding vectors to the provider.

Processing order:

1. `search_chunks()` loads the cached chunk embeddings for the repository and
   ranks them against the embedded question with NumPy cosine similarity.
2. The top fifteen chunks are formatted as context, each labeled with its
   repository-relative file path and 1-based line range. Q&A requests this
   larger limit from the same search function; the standalone search endpoint
   still returns five.
3. `send_message()` sends the instructions, question, and code context to the
   selected provider.
4. The endpoint returns the answer, provider, model, and the same source
   metadata.

```bash
curl -X POST http://localhost:8000/api/ollama/ask \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/AKSHATH99/illustrated-work-gallery", "question": "How are gallery items displayed?"}'
```

Abbreviated response:

```json
{
  "repository": "AKSHATH99/illustrated-work-gallery",
  "question": "How are gallery items displayed?",
  "provider": "gemini",
  "model": "gemini-3.6-flash",
  "total_chunks": 603,
  "answer": "Gallery items are rendered by ... (src/components/projects/ProjectMedia.tsx, lines 21-40).",
  "sources": [
    {
      "file_path": "src/components/projects/ProjectMedia.tsx",
      "chunk_index": 1,
      "start_line": 21,
      "end_line": 40,
      "content": "...",
      "similarity": 0.4229
    }
  ]
}
```

- The prompt instructs the model to answer only from the supplied context,
  reference source files and line ranges when possible, and state clearly when
  the context is insufficient.
- `attachment` is optional. When the frontend sidebar has a selected file, its
  text is appended as additional context; it is trimmed to 50,000 characters.
- Embeddings must have been generated in the same backend process. The cache is
  not persisted, so after a backend restart reload the repository.
- Q&A allows up to 240 seconds for the provider to generate a response, because
  the larger context takes longer. The `/test` and `/chat` endpoints keep their
  120-second timeout.
- `400` — invalid repository URL or empty question.
- `409` — embeddings are not ready for this repository.
- `422` — the question, attachment path, or attachment content exceeds its
  limit (4000, 1000, and 50000 characters respectively).
- `500` — embedding generation failed or provider configuration is missing.
- `502` — the provider is unreachable, the request timed out, a rate limit was
  hit, or the provider returned an unsuccessful response.

The frontend shows a repository file sidebar after a repository is downloaded.
Selecting a file reads its text, displays an attachment chip, and adds it to the
question request. File selection is optional: every question already uses the
automatically retrieved repository chunks.

The **Ask the repository** panel has one question input and **Send Message**
button, shown once the repository download, chunking, and embedding steps are
complete. Until then it displays the current preparation step. On submit,
retrieval and generation happen automatically. The panel shows the answer in a
scrollable block with the provider and model, then lists the retrieved sources
with file path, chunk index, line range, similarity score, and code, plus
loading and error states.

### Complete repository analysis

`POST /repositories/analysis` analyses the whole extracted repository with the
selected generation provider. It is independent of semantic search and
repository Q&A: it does not read cached embeddings or RAG chunks, and it does not
change the five-result search endpoint or the fifteen-chunk Q&A retrieval.

Processing order:

1. **Collect files** with the existing repository walker and the same UTF-8,
   binary, and symlink rules. Additional directories such as coverage output,
   framework build caches, dependency folders, and platform build folders are
   skipped. Lockfiles, minified assets, source maps, snapshots, and real `.env`
   files are excluded. Source code, configuration, package manifests, and
   documentation are included, and every file keeps its repository-relative
   path.
2. **Calculate the context budget** for the selected provider:
   - With Gemini, `GEMINI_NUM_CTX` takes precedence when set. Otherwise the
     backend reads `inputTokenLimit` from the Gemini model metadata endpoint.
   - With Ollama, `OLLAMA_NUM_CTX` takes precedence when set. Otherwise the
     backend reads the loaded model's runtime context from Ollama's `/api/ps`.
     If the model is not loaded, it sends a one-token warm-up request, re-reads
     `/api/ps`, and then reuses that loaded model for analysis. If the runtime
     value is unavailable, it reads `num_ctx` from `/api/show` parameters, then
     the model's `*context_length` metadata.
   - The budget reserves estimated tokens for the system instructions, the
     analysis prompt, expected output (1500 tokens), and a safety margin of
     `max(512, 10% of the context)`. The remainder is the input budget.
   - No fixed repository-size threshold is used. If no input budget remains, the
     endpoint returns `500` with guidance instead of guessing.
3. **Choose the strategy** by comparing the formatted file blocks (paths plus
   content) with the input budget. If they fit, one non-streaming chat request
   analyses every file.
4. **Batch and summarize** when they do not fit:
   - Complete files stay together whenever they fit in a batch.
   - Oversized files are split by lines with their path and 1-based line ranges
     preserved; a single oversized line is split by characters.
   - Batches are packed up to the input budget. Each batch summary preserves
     paths, responsibilities, functions, classes, exports, APIs, technologies,
     relationships, and relevant details.
   - Summary groups are merged hierarchically until the combined summaries fit,
     then a final synthesis produces the repository overview.
   - Files are never silently dropped or truncated. If summaries cannot be
     reduced within six merge stages, the request fails with an explicit error.
5. **Generate the final analysis** covering purpose and functionality,
   technologies, frontend/backend architecture, modules and responsibilities,
   component interactions, entry points, and overall structure. The prompt
   requires grounded statements and distinguishes confirmed details from
   assumptions.

Analysis requests use the selected provider and are non-streaming. Gemini
receives the budgeted content with `maxOutputTokens` mapped from the reserved
output; thinking is disabled for Flash and Lite models. Ollama receives the
detected context as `num_ctx` and caps generation with `num_predict` so the
reserved output stays inside the budget. Each call uses a 600-second timeout.

```bash
curl -X POST http://localhost:8000/repositories/analysis \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/octocat/Spoon-Knife"}'
```

Abbreviated response:

```json
{
  "repository": "gitscope-fixture/small",
  "analysis": "Repository-level overview ...",
  "metadata": {
    "strategy": "hierarchical_summarization",
    "total_files": 11,
    "estimated_repository_tokens": 1510,
    "provider": "ollama",
    "model": "llama3.2:3b",
    "context_capacity": 3072,
    "context_source": "OLLAMA_NUM_CTX",
    "available_input_tokens": 849,
    "reserved_tokens": {
      "system_instructions": 72,
      "analysis_prompt": 139,
      "expected_output": 1500,
      "safety_margin": 512
    },
    "batches_processed": 2,
    "hierarchy_stages": 2,
    "elapsed_seconds": 311.37
  }
}
```

- `strategy` is `single_request` or `hierarchical_summarization`.
- `provider` is `gemini` or `ollama`.
- `estimated_repository_tokens` is the content estimate
  `ceil(characters / 4)`; the strategy decision also accounts for file headers
  and separators.
- `context_capacity` is the detected model context, and `context_source`
  records where it came from (`GEMINI_NUM_CTX`,
  `gemini_model_info:inputTokenLimit`, `OLLAMA_NUM_CTX`,
  `ollama_ps:context_length`, `ollama_show:num_ctx`, or
  `ollama_show:model_info`).
- `batches_processed` and `hierarchy_stages` are `0` for single requests.
- The repository must already be downloaded and extracted.
- `400` — invalid URL or no analysable files.
- `404` — the repository has not been downloaded yet.
- `500` — missing context information, invalid provider configuration, a file
  read failure, or summaries that cannot be reduced.
- `502` — the provider is unreachable, the model is missing, a rate limit was
  hit, or a request failed.

The **Repository analysis** panel appears after the repository is downloaded,
below embeddings and above the Ask the repository question input. The **Analyse
Entire Repository** button starts an independent request, shows elapsed time
while the model works, and then displays the overview plus the strategy, file
count, estimated repository tokens, provider, model, model context, input
budget, batch count, merge stages, elapsed time, and context source. Errors from
the endpoint are shown in place. An analysis can take several minutes for a large
repository; the frontend allows up to 30 minutes.

## Frontend setup

```bash
cd frontend
npm install
```

Optional configuration:

```bash
cp .env.example .env
```

Run the dev server:

```bash
cd frontend
npm run dev
```

The app runs at <http://localhost:5173>. The dev server is configured with
`strictPort: true`, so it fails instead of silently switching ports if 5173 is
taken.

Other scripts:

```bash
npm run build     # production build into dist/
npm run preview   # preview the production build
```

## Configuration

| Variable             | Location | Default                                              | Purpose                              |
| -------------------- | -------- | ---------------------------------------------------- | ------------------------------------ |
| `VITE_API_BASE_URL`  | frontend | `http://localhost:8000`                              | Base URL used for API requests       |
| `CORS_ORIGINS`       | backend  | `http://localhost:5173,http://127.0.0.1:5173`        | Origins allowed to call the API      |
| `STORAGE_DIR`        | backend  | `backend/storage`                                    | Directory for reused ZIP archives    |
| `LLM_PROVIDER`       | backend  | `auto`                                               | `auto`, `gemini`, or `ollama`        |
| `GEMINI_API_KEY`     | backend  | none                                                 | Gemini key; enables Gemini with `auto` |
| `GEMINI_MODEL`       | backend  | `gemini-3.6-flash`                                   | Gemini model name                    |
| `GEMINI_NUM_CTX`     | backend  | none (detected from Gemini)                          | Repository-analysis context override |
| `OLLAMA_BASE_URL`    | backend  | `http://localhost:11434`                             | Local Ollama server URL              |
| `OLLAMA_MODEL`       | backend  | none (required when using Ollama)                    | Ollama model name                    |
| `OLLAMA_NUM_CTX`     | backend  | none (detected from Ollama)                          | Repository-analysis context override |

`.env` files are ignored by Git. Only `.env.example` files are committed, and
they must never contain real secrets.

## Current status

- `GET /health` returns the service status and is used by the frontend.
- `POST /repositories/download` downloads a public repository ZIP on first use,
  reuses the stored archive on later requests, and extracts it into a
  repository-specific directory.
- `GET /repositories/details` returns repository metadata from GitHub.
- `GET /repositories/files` lists UTF-8 text files in the extracted repository,
  and `GET /repositories/file` safely returns one file's text.
- `GET /repositories/stats` reports source file, line, character, and estimated
  token totals plus the largest files by size.
- `GET /repositories/chunks` splits extracted text files into line-based chunks.
- `POST /repositories/embeddings` generates one local 384-dimensional embedding
  per chunk with `all-MiniLM-L6-v2`, loading the model once per backend process
  and caching the chunk vectors for search.
- `POST /repositories/search` embeds the question and returns the top five chunks
  ranked by NumPy cosine similarity, reusing cached chunk embeddings.
- `POST /api/ollama/test` sends a fixed message through the selected generation
  provider and returns its response, reporting configuration, connection, rate
  limit, and upstream errors.
- `POST /api/ollama/ask` retrieves the top fifteen chunks with the existing
  semantic search, prompts the selected provider with their code and line
  ranges, and returns the answer, provider, model, and retrieved sources.
- `POST /repositories/analysis` collects relevant source, configuration,
  manifest, and documentation files, detects the provider's context budget, and
  either analyses the repository in one request or uses budgeted batches with
  hierarchical summaries. It returns the analysis plus provider, strategy, file,
  token, context, batch, and timing metadata.
- The frontend accepts a repository URL and runs the preparation pipeline
  automatically: download and extraction, statistics, file listing, chunking,
  then embeddings. Each panel reports Queued, Processing, Ready, or Failed in
  place.
- The frontend shows the download status and saved ZIP path, and displays the
  repository owner, description, stars, forks, language, default branch, and
  last-updated date.
- A repository statistics panel appears as soon as the download completes,
  while chunking and embeddings continue, and reports file, line, character,
  and estimated token totals plus the ten largest files.
- Chunks and embeddings are generated without extra button clicks and appear as
  soon as each step finishes, with Previous/Next navigation and a numerical
  embedding preview.
- The single **Ask the repository** question input appears only after all
  preparation steps finish. Each question automatically retrieves the top
  fifteen matching chunks and sends their code text to the selected provider;
  the answer is shown with the provider, model, retrieved paths, line ranges,
  similarity scores, and code.
- The left sidebar lists repository text files. Selecting a file optionally adds
  its text as extra context; manual selection is not required.
- A separate **Repository analysis** panel shows the **Analyse Entire
  Repository** button after download. While running, it shows elapsed time; the
  result includes the overview, strategy, analysis metadata, and errors.

### Troubleshooting

- **Backend shows "Disconnected"**: confirm the API is running on port 8000 and
  that `VITE_API_BASE_URL` matches. If you serve the frontend from a different
  origin, add that origin to `CORS_ORIGINS`.
- **Port already in use**: stop the conflicting process or adjust the port in
  `vite.config.js` (and the backend command) and keep `CORS_ORIGINS` in sync.
- **Generation test returns 500**: with Gemini, set `GEMINI_API_KEY` and check
  `GEMINI_MODEL`; with Ollama, set `OLLAMA_MODEL` in `backend/.env` (for example
  `llama3.2:3b`). Restart the backend after changing configuration.
- **Generation test returns 502**: with Gemini, check the network connection,
  API quota, and rate limits. With Ollama, confirm `ollama serve` is running on
  `OLLAMA_BASE_URL` and that the model is installed (`ollama list`), or pull it
  with `ollama pull llama3.2:3b`.
- **Gemini returns 429**: the API key has hit its rate or quota limit. Wait and
  retry, raise the limit in Google AI Studio, or set `LLM_PROVIDER=ollama`.
- **Gemini returns 404**: `GEMINI_MODEL` is not available to this key. Check the
  model name or list models with the Gemini API.
- **Repository question returns 409**: the running backend has no cached
  embeddings for the repository, usually because it restarted. Submit the
  repository URL again to rebuild chunks and embeddings.
- **Repository analysis returns 500 about the context window**: the provider did
  not report a usable context limit. With Gemini, set `GEMINI_NUM_CTX` to the
  model's input token limit. With Ollama, set `OLLAMA_NUM_CTX` to the value used
  by the Ollama server. Restart the backend after changing configuration.
- **Repository analysis returns 502**: confirm the selected provider is
  reachable, the model exists, and the API quota has not been exhausted.
- **Repository analysis is slow**: large repositories require multiple batch
  summaries and merge stages. The panel shows elapsed time; the request remains
  active for up to 30 minutes in the frontend. A larger context window reduces
  the number of batches.
