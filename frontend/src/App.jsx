import { useEffect, useRef, useState } from 'react'
import FileSidebar from './components/FileSidebar.jsx'
import ParserInspector from './components/ParserInspector.jsx'
import RepositoryCard from './components/RepositoryCard.jsx'
import RepositoryChat from './components/RepositoryChat.jsx'
import StatusBadge from './components/StatusBadge.jsx'
import {
  analyzeRepository,
  askRepositoryQuestion,
  downloadRepository,
  fetchGenerationProvider,
  fetchHealth,
  fetchRepositoryChunks,
  fetchRepositoryDetails,
  fetchRepositoryEmbeddings,
  fetchRepositoryFile,
  fetchRepositoryFiles,
  fetchRepositoryStats,
} from './services/api.js'

const MAX_ATTACHMENT_CHARS = 50000
const DEFAULT_REPO_URL = 'https://github.com/AKSHATH99/illustrated-work-gallery'
const DEFAULT_QUESTION = 'what projects are showcased in this portfolio'

function formatFileSize(size) {
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(1)} KB`
}

function pipelineBadgeStatus(status) {
  if (status === 'loading') return 'processing'
  if (status === 'success') return 'ready'
  if (status === 'error') return 'failed'
  return 'queued'
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return '—'
  const total = Math.round(seconds)
  if (total < 60) return `${total}s`
  const minutes = Math.floor(total / 60)
  const remainder = total % 60
  return `${minutes}m ${remainder.toString().padStart(2, '0')}s`
}

function analysisStrategyLabel(strategy) {
  if (strategy === 'single_request') return 'Single request'
  if (strategy === 'hierarchical_summarization') {
    return 'Batched, hierarchical summaries'
  }
  return strategy || '—'
}

function providerLabel(provider) {
  if (provider === 'gemini') return 'Gemini'
  if (provider === 'ollama') return 'Ollama'
  return provider || 'AI model'
}

export default function App() {
  const [backendStatus, setBackendStatus] = useState('checking')
  const [url, setUrl] = useState(DEFAULT_REPO_URL)
  const [downloadStatus, setDownloadStatus] = useState('idle')
  const [downloadResult, setDownloadResult] = useState(null)
  const [downloadError, setDownloadError] = useState('')
  const [details, setDetails] = useState(null)
  const [detailsError, setDetailsError] = useState('')
  const [detailsLoading, setDetailsLoading] = useState(false)
  const [chunksStatus, setChunksStatus] = useState('idle')
  const [chunkData, setChunkData] = useState(null)
  const [chunksError, setChunksError] = useState('')
  const [chunkIndex, setChunkIndex] = useState(0)
  const [embeddingsStatus, setEmbeddingsStatus] = useState('idle')
  const [embeddingData, setEmbeddingData] = useState(null)
  const [embeddingsError, setEmbeddingsError] = useState('')
  const [embeddingIndex, setEmbeddingIndex] = useState(0)
  const [analysisStatus, setAnalysisStatus] = useState('idle')
  const [analysisResult, setAnalysisResult] = useState(null)
  const [analysisError, setAnalysisError] = useState('')
  const [analysisElapsed, setAnalysisElapsed] = useState(0)
  const [generationProvider, setGenerationProvider] = useState(null)
  const [statsStatus, setStatsStatus] = useState('idle')
  const [stats, setStats] = useState(null)
  const [statsError, setStatsError] = useState('')
  const [filesStatus, setFilesStatus] = useState('idle')
  const [files, setFiles] = useState([])
  const [filesError, setFilesError] = useState('')
  const [selectedFilePath, setSelectedFilePath] = useState('')
  const [developerView, setDeveloperView] = useState(false)
  const [attachment, setAttachment] = useState(null)
  const [attachmentStatus, setAttachmentStatus] = useState('idle')
  const [attachmentError, setAttachmentError] = useState('')
  const latestRequest = useRef(0)
  const latestChunksRequest = useRef(0)
  const latestEmbeddingsRequest = useRef(0)
  const latestOllamaRequest = useRef(0)
  const latestFileRequest = useRef(0)
  const latestStatsRequest = useRef(0)
  const latestAnalysisRequest = useRef(0)

  async function loadGenerationProvider() {
    try {
      const info = await fetchGenerationProvider()
      setGenerationProvider(info)
      return info
    } catch {
      setGenerationProvider(null)
      return null
    }
  }

  useEffect(() => {
    let cancelled = false

    fetchGenerationProvider()
      .then((info) => {
        if (!cancelled) setGenerationProvider(info)
      })
      .catch(() => {
        if (!cancelled) setGenerationProvider(null)
      })

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    let cancelled = false

    async function checkBackend() {
      try {
        const health = await fetchHealth()
        if (!cancelled) {
          setBackendStatus(health.status === 'ok' ? 'connected' : 'disconnected')
        }
      } catch {
        if (!cancelled) {
          setBackendStatus('disconnected')
        }
      }
    }

    checkBackend()

    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (!downloadResult) return undefined

    let cancelled = false
    setFilesStatus('loading')
    setFiles([])
    setFilesError('')
    setSelectedFilePath('')
    setAttachment(null)
    setAttachmentStatus('idle')
    setAttachmentError('')
    latestFileRequest.current += 1

    fetchRepositoryFiles(`https://github.com/${downloadResult.repository}`)
      .then((result) => {
        if (cancelled) return
        setFiles(result.files)
        setFilesStatus('success')
      })
      .catch((error) => {
        if (cancelled) return
        setFilesError(error.message)
        setFilesStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [downloadResult])

  useEffect(() => {
    if (!downloadResult) return undefined

    let cancelled = false
    const requestId = latestStatsRequest.current + 1
    latestStatsRequest.current = requestId

    setStatsStatus('loading')
    setStats(null)
    setStatsError('')

    fetchRepositoryStats(`https://github.com/${downloadResult.repository}`)
      .then((result) => {
        if (cancelled || latestStatsRequest.current !== requestId) return
        setStats(result)
        setStatsStatus('success')
      })
      .catch((error) => {
        if (cancelled || latestStatsRequest.current !== requestId) return
        setStatsError(error.message)
        setStatsStatus('error')
      })

    return () => {
      cancelled = true
    }
  }, [downloadResult])

  useEffect(() => {
    if (analysisStatus !== 'loading') return undefined

    const started = Date.now()
    setAnalysisElapsed(0)
    const timer = setInterval(() => {
      setAnalysisElapsed(Math.floor((Date.now() - started) / 1000))
    }, 1000)

    return () => clearInterval(timer)
  }, [analysisStatus])

  async function handleSubmit(event) {
    event.preventDefault()

    const repoUrl = url.trim()
    if (!repoUrl || pipelineBusy) return

    const requestId = latestRequest.current + 1
    latestRequest.current = requestId

    setDownloadStatus('downloading')
    setDownloadResult(null)
    setDownloadError('')
    setDetails(null)
    setDetailsError('')
    setDetailsLoading(true)
    setChunksStatus('idle')
    setChunkData(null)
    setChunksError('')
    setChunkIndex(0)
    latestChunksRequest.current += 1
    setEmbeddingsStatus('idle')
    setEmbeddingData(null)
    setEmbeddingsError('')
    setEmbeddingIndex(0)
    latestEmbeddingsRequest.current += 1
    setStatsStatus('idle')
    setStats(null)
    setStatsError('')
    latestStatsRequest.current += 1
    setFilesStatus('idle')
    setFiles([])
    setFilesError('')
    setSelectedFilePath('')
    setAttachment(null)
    setAttachmentStatus('idle')
    setAttachmentError('')
    latestFileRequest.current += 1
    latestOllamaRequest.current += 1
    setAnalysisStatus('idle')
    setAnalysisResult(null)
    setAnalysisError('')
    setAnalysisElapsed(0)
    latestAnalysisRequest.current += 1

    fetchRepositoryDetails(repoUrl)
      .then((info) => {
        if (latestRequest.current === requestId) setDetails(info)
      })
      .catch((error) => {
        if (latestRequest.current === requestId) setDetailsError(error.message)
      })
      .finally(() => {
        if (latestRequest.current === requestId) setDetailsLoading(false)
      })

    try {
      const result = await downloadRepository(repoUrl)
      if (latestRequest.current !== requestId) return
      setDownloadResult(result)
      setDownloadStatus('downloaded')

      const repositoryUrl = `https://github.com/${result.repository}`
      if (!(await prepareChunks(repositoryUrl, requestId))) return
      await prepareEmbeddings(repositoryUrl, requestId)
    } catch (error) {
      if (latestRequest.current === requestId) {
        setDownloadError(error.message)
        setDownloadStatus('failed')
      }
    }
  }

  async function prepareChunks(repositoryUrl, requestId) {
    const chunkRequestId = latestChunksRequest.current + 1
    latestChunksRequest.current = chunkRequestId

    setChunksStatus('loading')
    setChunksError('')
    setChunkData(null)
    setChunkIndex(0)

    try {
      const result = await fetchRepositoryChunks(repositoryUrl)
      if (
        latestRequest.current !== requestId ||
        latestChunksRequest.current !== chunkRequestId
      ) {
        return false
      }
      setChunkData(result)
      setChunksStatus('success')
      return true
    } catch (error) {
      if (
        latestRequest.current !== requestId ||
        latestChunksRequest.current !== chunkRequestId
      ) {
        return false
      }
      setChunksError(error.message)
      setChunksStatus('error')
      return false
    }
  }

  async function prepareEmbeddings(repositoryUrl, requestId) {
    const embeddingsRequestId = latestEmbeddingsRequest.current + 1
    latestEmbeddingsRequest.current = embeddingsRequestId

    setEmbeddingsStatus('loading')
    setEmbeddingsError('')
    setEmbeddingData(null)
    setEmbeddingIndex(0)

    try {
      const result = await fetchRepositoryEmbeddings(repositoryUrl)
      if (
        latestRequest.current !== requestId ||
        latestEmbeddingsRequest.current !== embeddingsRequestId
      ) {
        return false
      }
      setEmbeddingData(result)
      setEmbeddingsStatus('success')
      return true
    } catch (error) {
      if (
        latestRequest.current !== requestId ||
        latestEmbeddingsRequest.current !== embeddingsRequestId
      ) {
        return false
      }
      setEmbeddingsError(error.message)
      setEmbeddingsStatus('error')
      return false
    }
  }

  async function handleSelectFile(file) {
    if (!downloadResult) return

    const requestId = latestFileRequest.current + 1
    latestFileRequest.current = requestId

    setSelectedFilePath(file.file_path)
    setAttachmentStatus('loading')
    setAttachmentError('')
    setAttachment(null)

    try {
      const result = await fetchRepositoryFile(
        `https://github.com/${downloadResult.repository}`,
        file.file_path,
      )
      if (latestFileRequest.current !== requestId) return

      const content = result.content.slice(0, MAX_ATTACHMENT_CHARS)
      setAttachment({
        file_path: result.file_path,
        content,
        size: result.size,
        truncated: content.length < result.content.length,
      })
      setAttachmentStatus('success')
    } catch (error) {
      if (latestFileRequest.current !== requestId) return
      setAttachmentError(error.message)
      setAttachmentStatus('error')
    }
  }

  function handleRemoveAttachment() {
    latestFileRequest.current += 1
    setSelectedFilePath('')
    setAttachment(null)
    setAttachmentStatus('idle')
    setAttachmentError('')
  }

  async function askQuestion(question) {
    const requestId = latestOllamaRequest.current + 1
    latestOllamaRequest.current = requestId

    const result = await askRepositoryQuestion({
      repoUrl: `https://github.com/${downloadResult.repository}`,
      question,
      attachment,
    })
    if (latestOllamaRequest.current !== requestId) {
      throw new Error('A newer question replaced this one.')
    }
    return result
  }

  async function handleAnalyzeRepository() {
    if (!downloadResult || analysisStatus === 'loading') return

    const requestId = latestAnalysisRequest.current + 1
    latestAnalysisRequest.current = requestId

    await loadGenerationProvider()

    setAnalysisStatus('loading')
    setAnalysisError('')
    setAnalysisResult(null)

    try {
      const result = await analyzeRepository(
        `https://github.com/${downloadResult.repository}`,
      )
      if (latestAnalysisRequest.current !== requestId) return
      setAnalysisResult(result)
      setAnalysisStatus('success')
    } catch (error) {
      if (latestAnalysisRequest.current !== requestId) return
      setAnalysisError(error.message)
      setAnalysisStatus('error')
    }
  }

  const chunks = chunkData?.chunks ?? []
  const currentChunk = chunks[chunkIndex]
  const embeddings = embeddingData?.embeddings ?? []
  const currentEmbedding = embeddings[embeddingIndex]
  const embeddingPreview = currentEmbedding
    ? currentEmbedding.values.slice(0, 10)
    : []
  const analysisModelLabel = generationProvider
    ? `${providerLabel(generationProvider.provider)} · ${generationProvider.model}`
    : 'Detecting…'
  const pipelineBusy =
    downloadStatus === 'downloading' ||
    chunksStatus === 'loading' ||
    embeddingsStatus === 'loading'
  const repoReady =
    downloadStatus === 'downloaded' &&
    chunksStatus === 'success' &&
    embeddingsStatus === 'success'
  const repoSummaryVisible = Boolean(
    details ||
      detailsLoading ||
      downloadResult ||
      (detailsError && downloadStatus !== 'failed'),
  )

  let gateMessage = 'Enter a repository link to start asking questions.'
  if (downloadStatus === 'downloading') {
    gateMessage = 'Downloading the repository…'
  } else if (downloadStatus === 'failed') {
    gateMessage =
      'The repository could not be downloaded. Submit the link again to retry.'
  } else if (downloadStatus === 'downloaded') {
    if (chunksStatus === 'loading') {
      gateMessage = 'Splitting the repository into chunks…'
    } else if (chunksStatus === 'error') {
      gateMessage = 'Chunking failed. Submit the link again to retry.'
    } else if (
      embeddingsStatus === 'loading' ||
      embeddingsStatus === 'idle'
    ) {
      gateMessage = 'Generating local embeddings…'
    } else if (embeddingsStatus === 'error') {
      gateMessage =
        'Embedding generation failed. Submit the link again to retry.'
    }
  }

  const downloadSection = (
    <section className="result-panel" aria-label="Download result">
      <div className="result-head">
        <span className="result-label">Download</span>
        <StatusBadge
          status={
            downloadStatus === 'downloaded'
              ? 'downloaded'
              : downloadStatus === 'failed'
                ? 'failed'
                : 'downloading'
          }
        />
      </div>
      {downloadResult && (
        <code className="zip-path">{downloadResult.zip_path}</code>
      )}
      {downloadError && (
        <p className="error-message" role="alert">
          {downloadError}
        </p>
      )}
    </section>
  )

  const statsSection = (
    <section className="chunks-panel stats-panel" aria-label="Repository statistics">
      <div className="chunks-header">
        <div>
          <span className="result-label">Repository statistics</span>
          <p className="hint">
            Counts cover the same UTF-8 text files used for chunking.
            Tokens are estimated from characters.
          </p>
        </div>
        <StatusBadge status={pipelineBadgeStatus(statsStatus)} />
      </div>

      {statsStatus === 'loading' && (
        <p className="loading-note" role="status">
          Counting source files, lines, and estimated tokens…
        </p>
      )}

      {statsStatus === 'error' && (
        <p className="error-message" role="alert">
          {statsError}
        </p>
      )}

      {statsStatus === 'success' && stats && (
        <div className="chunk-viewer">
          <dl className="embedding-stats stats-grid">
            <div>
              <dt>Source files</dt>
              <dd>{stats.total_files.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Source lines</dt>
              <dd>{stats.total_lines.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Characters</dt>
              <dd>{stats.total_characters.toLocaleString()}</dd>
            </div>
            <div>
              <dt>Estimated tokens</dt>
              <dd>{stats.estimated_tokens.toLocaleString()}</dd>
            </div>
          </dl>

          {stats.largest_files.length > 0 && (
            <details className="stats-files">
              <summary className="chunk-summary">
                <span>Largest source files</span>
                <span>
                  Tokens estimated as {stats.token_estimate_method}
                </span>
              </summary>
              <ol className="stats-file-list">
                {stats.largest_files.map((file, index) => (
                  <li key={file.file_path}>
                    <span className="search-rank">{index + 1}</span>
                    <code className="stats-file-path">
                      {file.file_path}
                    </code>
                    <span className="stats-file-meta">
                      {file.lines.toLocaleString()} lines
                    </span>
                    <span className="search-score">
                      {formatFileSize(file.size)}
                    </span>
                  </li>
                ))}
              </ol>
            </details>
          )}
        </div>
      )}
    </section>
  )

  const chunksSection = (
    <section className="chunks-panel" aria-label="Source chunks">
      <div className="chunks-header">
        <div>
          <span className="result-label">Source chunks</span>
          <p className="hint">
            JavaScript, JSX, TypeScript, TSX and JSON files are split
            along their own syntax; files without a grammar are split by
            character size with a small overlap.
          </p>
        </div>
        <StatusBadge status={pipelineBadgeStatus(chunksStatus)} />
      </div>

      {chunksStatus === 'loading' && (
        <p className="loading-note" role="status">
          Reading extracted files and generating chunks…
        </p>
      )}

      {chunksStatus === 'idle' && (
        <p className="loading-note" role="status">
          {downloadStatus === 'failed'
            ? 'Chunking was skipped because the download failed.'
            : 'Waiting for the repository download to finish…'}
        </p>
      )}

      {chunksStatus === 'error' && (
        <p className="error-message" role="alert">
          {chunksError}
        </p>
      )}

      {chunksStatus === 'success' &&
        chunkData &&
        (chunkData.total_chunks === 0 ? (
          <p className="notice">
            No text source files were found in this repository.
          </p>
        ) : (
          <div className="chunk-viewer">
            <div className="chunk-summary">
              <span>
                {chunkData.total_chunks.toLocaleString()} chunks
              </span>
              <span>
                Chunk #{currentChunk.chunk_index} ·{' '}
                {currentChunk.chunk_type ?? 'text'} · lines{' '}
                {currentChunk.start_line}–{currentChunk.end_line}
              </span>
            </div>
            <code className="chunk-file">{currentChunk.file_path}</code>
            <pre className="chunk-code">
              <code>{currentChunk.content}</code>
            </pre>
            <div className="chunk-nav">
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setChunkIndex((index) => Math.max(0, index - 1))
                }
                disabled={chunkIndex === 0}
              >
                ← Previous
              </button>
              <span className="chunk-position">
                {chunkIndex + 1} / {chunks.length}
              </span>
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setChunkIndex((index) =>
                    Math.min(chunks.length - 1, index + 1),
                  )
                }
                disabled={chunkIndex >= chunks.length - 1}
              >
                Next →
              </button>
            </div>
          </div>
        ))}
    </section>
  )

  const embeddingsSection = (
    <section className="chunks-panel" aria-label="Embeddings">
      <div className="chunks-header">
        <div>
          <span className="result-label">Embeddings</span>
          <p className="hint">
            One local vector per chunk is generated with
            all-MiniLM-L6-v2 automatically.
          </p>
        </div>
        <StatusBadge status={pipelineBadgeStatus(embeddingsStatus)} />
      </div>

      {embeddingsStatus === 'idle' && (
        <p className="loading-note" role="status">
          {chunksStatus === 'error'
            ? 'Embeddings were skipped because chunking failed.'
            : 'Waiting for chunking to finish…'}
        </p>
      )}

      {embeddingsStatus === 'loading' && (
        <p className="loading-note" role="status">
          Generating embeddings locally. The first run downloads the model
          and may take a minute…
        </p>
      )}

      {embeddingsStatus === 'error' && (
        <p className="error-message" role="alert">
          {embeddingsError}
        </p>
      )}

      {embeddingsStatus === 'success' &&
        embeddingData &&
        (embeddingData.total_embeddings === 0 ? (
          <p className="notice">
            No text chunks were found to embed in this repository.
          </p>
        ) : (
          <div className="chunk-viewer">
            <dl className="embedding-stats">
              <div>
                <dt>Chunks processed</dt>
                <dd>{embeddingData.total_chunks.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Embeddings generated</dt>
                <dd>{embeddingData.total_embeddings.toLocaleString()}</dd>
              </div>
              <div>
                <dt>Dimensions</dt>
                <dd>{embeddingData.dimensions.toLocaleString()}</dd>
              </div>
            </dl>
            <div className="chunk-summary">
              <span>
                Embedding {embeddingIndex + 1} of {embeddings.length}
              </span>
              <span>
                Chunk #{currentEmbedding.chunk_index} · lines{' '}
                {currentEmbedding.start_line}–{currentEmbedding.end_line}
              </span>
            </div>
            <code className="chunk-file">
              {currentEmbedding.file_path}
            </code>
            <pre className="chunk-code embedding-preview">
              <code>
                {`[${embeddingPreview
                  .map((value) => value.toFixed(6))
                  .join(', ')}]`}
              </code>
            </pre>
            <p className="hint embedding-hint">
              First {embeddingPreview.length} of{' '}
              {embeddingData.dimensions} values.
            </p>
            <div className="chunk-nav">
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setEmbeddingIndex((index) => Math.max(0, index - 1))
                }
                disabled={embeddingIndex === 0}
              >
                ← Previous
              </button>
              <span className="chunk-position">
                {embeddingIndex + 1} / {embeddings.length}
              </span>
              <button
                type="button"
                className="secondary-button"
                onClick={() =>
                  setEmbeddingIndex((index) =>
                    Math.min(embeddings.length - 1, index + 1),
                  )
                }
                disabled={embeddingIndex >= embeddings.length - 1}
              >
                Next →
              </button>
            </div>
          </div>
        ))}
    </section>
  )

  const inspectorSection = downloadResult && (
    <section
      className="chunks-panel"
      aria-label="Parser inspection (developer view)"
    >
      <div className="chunks-header">
        <div>
          <span className="result-label">Tree-sitter inspection</span>
          <p className="hint">
            Developer view of ingestion: syntax trees, extracted
            structures, structure-aware chunks, and pipeline totals.
            JavaScript, JSX, TypeScript, TSX and JSON files chunk along
            their own syntax; other file types split by size.
          </p>
        </div>
        <button
          type="button"
          className="secondary-button"
          onClick={() => setDeveloperView((open) => !open)}
          aria-expanded={developerView}
        >
          {developerView ? 'Hide inspector' : 'Show inspector'}
        </button>
      </div>

      {developerView && (
        <ParserInspector
          repoUrl={`https://github.com/${downloadResult.repository}`}
          filePath={selectedFilePath || currentChunk?.file_path || ''}
        />
      )}
    </section>
  )

  const analysisSection = (
    <section className="chunks-panel" aria-label="Repository analysis">
      <div className="chunks-header">
        <div>
          <span className="result-label">Repository analysis</span>
          <p className="hint">
            Analyse the whole repository with the configured AI model.
            Relevant source, configuration, package manifests, and
            documentation files are sent directly; semantic search and
            RAG chunks are not used.
          </p>
          <p className="hint">
            Model in use: {analysisModelLabel}
          </p>
        </div>
        <StatusBadge status={pipelineBadgeStatus(analysisStatus)} />
      </div>

      <div className="input-row analysis-actions">
        <button
          type="button"
          onClick={handleAnalyzeRepository}
          disabled={analysisStatus === 'loading'}
        >
          {analysisStatus === 'loading'
            ? 'Analysing entire repository…'
            : 'Analyse Entire Repository'}
        </button>
      </div>

      {analysisStatus === 'loading' && (
        <p className="loading-note" role="status">
          Reading files and waiting for {analysisModelLabel} ·{' '}
          {formatDuration(analysisElapsed)} elapsed. Large repositories
          are summarised in batches and can take several minutes.
        </p>
      )}

      {analysisStatus === 'error' && (
        <p className="error-message" role="alert">
          {analysisError}
        </p>
      )}

      {analysisStatus === 'success' && analysisResult && (
        <div className="analysis-result">
          <dl className="embedding-stats analysis-meta">
            <div>
              <dt>Strategy</dt>
              <dd className="analysis-strategy">
                {analysisStrategyLabel(
                  analysisResult.metadata.strategy,
                )}
              </dd>
            </div>
            <div>
              <dt>Files analysed</dt>
              <dd>
                {analysisResult.metadata.total_files.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt>Estimated repo tokens</dt>
              <dd>
                {analysisResult.metadata.estimated_repository_tokens.toLocaleString()}
              </dd>
            </div>
            <div>
              <dt>Model context</dt>
              <dd>
                {analysisResult.metadata.context_capacity.toLocaleString()}{' '}
                tokens
              </dd>
            </div>
            <div>
              <dt>Input budget</dt>
              <dd>
                {analysisResult.metadata.available_input_tokens.toLocaleString()}{' '}
                tokens
              </dd>
            </div>
            <div>
              <dt>Batches</dt>
              <dd>
                {analysisResult.metadata.batches_processed > 0
                  ? analysisResult.metadata.batches_processed.toLocaleString()
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Merge stages</dt>
              <dd>
                {analysisResult.metadata.hierarchy_stages > 0
                  ? analysisResult.metadata.hierarchy_stages.toLocaleString()
                  : '—'}
              </dd>
            </div>
            <div>
              <dt>Elapsed</dt>
              <dd>
                {formatDuration(
                  analysisResult.metadata.elapsed_seconds,
                )}
              </dd>
            </div>
          </dl>

          <p className="hint analysis-source">
            {providerLabel(analysisResult.metadata.provider)} ·{' '}
            {analysisResult.metadata.model} · context window from{' '}
            {analysisResult.metadata.context_source}. Reserved for
            instructions, output, and safety:{' '}
            {(
              analysisResult.metadata.reserved_tokens
                .system_instructions +
              analysisResult.metadata.reserved_tokens.analysis_prompt +
              analysisResult.metadata.reserved_tokens.expected_output +
              analysisResult.metadata.reserved_tokens.safety_margin
            ).toLocaleString()}{' '}
            tokens.
          </p>

          <span className="result-label">Overview</span>
          <pre className="chunk-code analysis-output">
            <code>{analysisResult.analysis}</code>
          </pre>
        </div>
      )}
    </section>
  )

  const chatSection = (
    <section className="chunks-panel chat-panel" aria-label="Repository questions">
      <RepositoryChat
        repository={downloadResult?.repository ?? ''}
        ready={repoReady}
        gateMessage={gateMessage}
        busy={attachmentStatus === 'loading'}
        onSend={askQuestion}
        attachmentPath={attachment?.file_path ?? null}
        providerLabel={providerLabel}
        initialQuestion={DEFAULT_QUESTION}
        attachmentSlot={
          repoReady ? (
            <>
              {attachmentStatus === 'loading' && (
                <p className="loading-note attachment-note" role="status">
                  Loading file content…
                </p>
              )}

              {attachmentStatus === 'error' && (
                <p className="error-message" role="alert">
                  {attachmentError}
                </p>
              )}

              {attachment && (
                <div className="attachment">
                  <div className="attachment-info">
                    <span className="attachment-path">
                      {attachment.file_path}
                    </span>
                    <span className="attachment-meta">
                      {formatFileSize(attachment.size)} ·{' '}
                      {attachment.truncated
                        ? `first ${MAX_ATTACHMENT_CHARS.toLocaleString()} characters`
                        : 'full text'}{' '}
                      attached as text
                    </span>
                  </div>
                  <button
                    type="button"
                    className="secondary-button attachment-remove"
                    onClick={handleRemoveAttachment}
                  >
                    Remove
                  </button>
                </div>
              )}
            </>
          ) : null
        }
      />
    </section>
  )

  return (
    <div className={`app${downloadResult ? ' app-with-files' : ''}`}>
      <header className="site-header">
        <div className="brand">
          <h1 className="brand-title">GitScope</h1>
          <p className="tagline">AI-powered GitHub repository intelligence</p>
        </div>

        <div className="service-status" aria-label="Service status">
          <div className="service-row">
            <span>Frontend</span>
            <StatusBadge status="running" />
          </div>
          <div className="service-row">
            <span>Backend</span>
            <StatusBadge status={backendStatus} />
          </div>
        </div>
      </header>

      <div className={downloadResult ? 'workspace-layout' : undefined}>
        {downloadResult && (
          <FileSidebar
            files={files}
            status={filesStatus}
            error={filesError}
            selectedPath={selectedFilePath}
            onSelect={handleSelectFile}
          />
        )}
        <main className="workspace">
          <section className="form-panel" aria-label="Download a repository">
            <form className="repo-form" onSubmit={handleSubmit}>
              <label className="field-label" htmlFor="repo-url">
                Public GitHub repository URL
              </label>
              <div className="input-row">
                <input
                  id="repo-url"
                  type="url"
                  value={url}
                  onChange={(event) => setUrl(event.target.value)}
                  placeholder="https://github.com/owner/repository"
                  autoComplete="off"
                  spellCheck="false"
                  required
                  disabled={pipelineBusy}
                />
                <button type="submit" disabled={pipelineBusy}>
                  {pipelineBusy ? 'Preparing…' : 'Analyze Repository'}
                </button>
              </div>
              <p className="hint">
                The repository is downloaded, split into chunks, and embedded
                locally in one step.
              </p>
            </form>

            {repoSummaryVisible && (
              <div className="repo-summary">
                <div className="repo-summary-identity">
                  {detailsLoading && !details && !detailsError && (
                    <p className="loading-note" role="status">
                      Fetching repository details…
                    </p>
                  )}

                  {detailsError && downloadStatus !== 'failed' && (
                    <p className="notice" role="status">
                      Repository details unavailable: {detailsError}
                    </p>
                  )}

                  {details && <RepositoryCard repo={details} />}
                </div>
                {downloadResult && (
                  <div className="repo-summary-stats">{statsSection}</div>
                )}
              </div>
            )}
          </section>

          {downloadError && (
            <p className="error-message" role="alert">
              {downloadError}
            </p>
          )}

          {downloadStatus === 'idle' ? (
            chatSection
          ) : (
            <div className="content-grid">
              <div className="chat-column">
                {chatSection}
                {downloadResult && analysisSection}
              </div>

              <div className="pipeline-column">
                <section
                  className="pipeline-rail"
                  aria-label="Preparation pipeline"
                >
                  <span className="result-label">Pipeline</span>
                  <ol className="pipeline-steps-vertical">
                    <li>
                      <span>Download</span>
                      <StatusBadge
                        status={
                          downloadStatus === 'downloaded'
                            ? 'downloaded'
                            : downloadStatus === 'failed'
                              ? 'failed'
                              : 'downloading'
                        }
                      />
                    </li>
                    <li>
                      <span>Chunks</span>
                      <StatusBadge
                        status={pipelineBadgeStatus(chunksStatus)}
                      />
                    </li>
                    <li>
                      <span>Embeddings</span>
                      <StatusBadge
                        status={pipelineBadgeStatus(embeddingsStatus)}
                      />
                    </li>
                  </ol>
                </section>
                {downloadSection}
                {chunksSection}
                {embeddingsSection}
                {inspectorSection}
              </div>
            </div>
          )}
        </main>
      </div>
    </div>
  )
}