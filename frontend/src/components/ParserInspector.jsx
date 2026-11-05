import { useEffect, useRef, useState } from 'react'
import SyntaxTree from './SyntaxTree.jsx'
import { fetchIngestionReport, inspectRepositoryFile } from '../services/api.js'

const TABS = [
  { id: 'tree', label: 'Syntax tree' },
  { id: 'structures', label: 'Structures' },
  { id: 'chunks', label: 'Final chunks' },
  { id: 'pipeline', label: 'Pipeline' },
]

const MAX_CHUNK_ROWS = 60
const MAX_FILE_ROWS = 60

const CHUNK_TYPE_LABELS = {
  symbol: 'Whole symbol',
  symbol_part: 'Symbol part',
  text: 'Text chunk',
}

function chunkTypeLabel(type) {
  return CHUNK_TYPE_LABELS[type] ?? type ?? '—'
}

function lineRange(chunk) {
  return chunk.start_line === chunk.end_line
    ? `line ${chunk.start_line}`
    : `lines ${chunk.start_line}–${chunk.end_line}`
}

function formatChars(value) {
  return `${(value ?? 0).toLocaleString()} chars`
}

function Stat({ label, value }) {
  return (
    <div>
      <dt>{label}</dt>
      <dd>{value}</dd>
    </div>
  )
}

export default function ParserInspector({ repoUrl, filePath }) {
  const [tab, setTab] = useState('tree')
  const [fileStatus, setFileStatus] = useState('idle')
  const [fileError, setFileError] = useState('')
  const [inspectResult, setInspectResult] = useState(null)
  const [report, setReport] = useState(null)
  const [reportStatus, setReportStatus] = useState('idle')
  const [reportError, setReportError] = useState('')
  const latestFileRequest = useRef(0)
  const latestReportRequest = useRef(0)

  useEffect(() => {
    const requestId = latestFileRequest.current + 1
    latestFileRequest.current = requestId

    if (!filePath) {
      setInspectResult(null)
      setFileStatus('idle')
      setFileError('')
      return undefined
    }

    setFileStatus('loading')
    setInspectResult(null)
    setFileError('')

    inspectRepositoryFile(repoUrl, filePath)
      .then((result) => {
        if (latestFileRequest.current !== requestId) return
        setInspectResult(result)
        setFileStatus('success')
      })
      .catch((error) => {
        if (latestFileRequest.current !== requestId) return
        setFileError(error.message)
        setFileStatus('error')
      })

    return () => {
      latestFileRequest.current += 1
    }
  }, [repoUrl, filePath])

  function loadReport() {
    const requestId = latestReportRequest.current + 1
    latestReportRequest.current = requestId

    setReportStatus('loading')
    setReportError('')

    fetchIngestionReport(repoUrl)
      .then((result) => {
        if (latestReportRequest.current !== requestId) return
        setReport(result)
        setReportStatus('success')
      })
      .catch((error) => {
        if (latestReportRequest.current !== requestId) return
        setReportError(error.message)
        setReportStatus('error')
      })
  }

  useEffect(() => {
    if (tab !== 'pipeline' || reportStatus !== 'idle') return undefined
    loadReport()
    return undefined
  }, [tab, reportStatus])

  const structures = inspectResult?.structures ?? []
  const chunks = inspectResult?.chunks ?? []
  const errors = inspectResult?.errors ?? []

  return (
    <div className="inspector">
      <div className="inspector-tabs" role="tablist">
        {TABS.map((entry) => (
          <button
            key={entry.id}
            type="button"
            role="tab"
            aria-selected={tab === entry.id}
            className={`inspector-tab${tab === entry.id ? ' is-active' : ''}`}
            onClick={() => setTab(entry.id)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {tab !== 'pipeline' && !filePath && (
        <p className="notice">
          Select a file in the sidebar to inspect its syntax tree, extracted
          structures, and final chunks.
        </p>
      )}

      {tab !== 'pipeline' && fileStatus === 'loading' && (
        <p className="loading-note" role="status">
          Parsing {filePath} with Tree-sitter…
        </p>
      )}

      {tab !== 'pipeline' && fileStatus === 'error' && (
        <p className="error-message" role="alert">
          {fileError}
        </p>
      )}

      {tab !== 'pipeline' && fileStatus === 'success' && inspectResult && (
        <>
          <div className="chunk-summary">
            <span>
              {inspectResult.mode === 'structural'
                ? `Tree-sitter ${inspectResult.language}`
                : 'Size-based text chunks'}
            </span>
            <span>
              {structures.length} structures · {chunks.length} chunks ·{' '}
              {inspectResult.node_count.toLocaleString()} nodes
            </span>
          </div>
          <code className="chunk-file">{filePath}</code>

          {inspectResult.parse_error && (
            <p className="error-message" role="alert">
              Parser failed: {inspectResult.parse_error}
            </p>
          )}

          {errors.length > 0 && (
            <p className="notice">
              {errors.length} syntax error{errors.length === 1 ? '' : 's'} were
              recovered. Structures below are still usable.
            </p>
          )}

          {tab === 'tree' && (
            <>
              {inspectResult.truncated_after_line && (
                <p className="hint">
                  Only the first {inspectResult.truncated_after_line} lines were
                  parsed; the rest is chunked by size.
                </p>
              )}
              <SyntaxTree
                nodes={inspectResult.tree}
                truncated={inspectResult.tree_truncated}
                emptyMessage={
                  inspectResult.mode === 'structural'
                    ? 'This file has an empty syntax tree.'
                    : 'This file type is not parsed by Tree-sitter, so there is no syntax tree.'
                }
              />
            </>
          )}

          {tab === 'structures' &&
            (structures.length === 0 ? (
              <p className="notice">
                No named structures were extracted from this file.
              </p>
            ) : (
              <ul className="inspector-list">
                {structures.map((structure) => (
                  <li key={structure.id}>
                    <details>
                      <summary>
                        <code className="structure-name">{structure.name}</code>
                        <span className="chunk-type-tag">
                          {structure.symbol_type}
                        </span>
                        {structure.json_path && (
                          <code className="json-path">
                            {structure.json_path}
                          </code>
                        )}
                        {structure.exported && (
                          <span className="chunk-type-tag">exported</span>
                        )}
                        {structure.parent_symbol && (
                          <span className="structure-parent">
                            in {structure.parent_symbol}
                          </span>
                        )}
                        <span className="tree-lines">
                          {structure.start_line === structure.end_line
                            ? `line ${structure.start_line}`
                            : `lines ${structure.start_line}–${structure.end_line}`}
                        </span>
                        <span className="tree-lines">
                          {structure.start_index}–{structure.end_index}
                        </span>
                      </summary>
                      <pre className="chunk-code">
                        <code>{structure.source_code}</code>
                      </pre>
                    </details>
                  </li>
                ))}
              </ul>
            ))}

          {tab === 'chunks' &&
            (chunks.length === 0 ? (
              <p className="notice">This file produced no chunks.</p>
            ) : (
              <>
                <ul className="inspector-list">
                  {chunks.slice(0, MAX_CHUNK_ROWS).map((chunk, index) => (
                    <li key={`${index}:${chunk.chunk_id}`}>
                      <details>
                        <summary>
                          <span className="chunk-type-tag">
                            {chunkTypeLabel(chunk.chunk_type)}
                          </span>
                          {chunk.symbol ? (
                            <code className="structure-name">{chunk.symbol}</code>
                          ) : (
                            <code className="structure-name">—</code>
                          )}
                          {chunk.json_path && (
                            <code className="json-path">{chunk.json_path}</code>
                          )}
                          {chunk.parent_symbol && (
                            <span className="structure-parent">
                              in {chunk.parent_symbol}
                            </span>
                          )}
                          {chunk.contains?.length > 0 && (
                            <span className="structure-parent">
                              {chunk.contains.join(', ')}
                            </span>
                          )}
                          <span className="tree-lines">{lineRange(chunk)}</span>
                          <span className="tree-lines">
                            {chunk.characters} chars ·{' '}
                            {chunk.estimated_tokens} tok
                          </span>
                        </summary>
                        <code className="chunk-file">{chunk.chunk_id}</code>
                        <pre className="chunk-code">
                          <code>{chunk.content}</code>
                        </pre>
                      </details>
                    </li>
                  ))}
                </ul>
                {chunks.length > MAX_CHUNK_ROWS && (
                  <p className="hint">
                    Showing the first {MAX_CHUNK_ROWS} of {chunks.length} chunks
                    for this file.
                  </p>
                )}
              </>
            ))}
        </>
      )}

      {tab === 'pipeline' && (
        <div className="inspector-pipeline">
          <div className="inspector-toolbar">
            <button
              type="button"
              className="secondary-button"
              onClick={loadReport}
              disabled={reportStatus === 'loading'}
            >
              {reportStatus === 'loading' ? 'Recounting…' : 'Recount pipeline'}
            </button>
          </div>

          {reportStatus === 'error' && (
            <p className="error-message" role="alert">
              {reportError}
            </p>
          )}

          {reportStatus === 'success' && report && (
            <>
              {report.tree_sitter_available ? null : (
                <p className="notice">
                  Tree-sitter grammars are not installed, so every file was
                  chunked by size. Install the dependencies listed in
                  backend/requirements.txt and restart the backend.
                </p>
              )}

              <dl className="embedding-stats stats-grid">
                <Stat label="Files scanned" value={report.files_scanned} />
                <Stat label="Files parsed" value={report.files_parsed} />
                <Stat label="Files with errors" value={report.files_with_errors} />
                <Stat label="Files skipped" value={report.files_skipped} />
                <Stat
                  label="Structures extracted"
                  value={report.structures_extracted.toLocaleString()}
                />
                <Stat
                  label="Chunks generated"
                  value={report.chunks_generated.toLocaleString()}
                />
                <Stat
                  label="Chunks embedded"
                  value={report.chunks_embedded.toLocaleString()}
                />
                <Stat
                  label="Text-chunked files"
                  value={report.files_text_chunked}
                />
              </dl>

              <div className="chunk-summary">
                <span>Chunk types</span>
                <span>
                  {Object.entries(report.chunks_by_type)
                    .map(
                      ([type, count]) =>
                        `${chunkTypeLabel(type)} ${count.toLocaleString()}`,
                    )
                    .join(' · ') || 'none'}
                </span>
              </div>

              <div className="chunk-summary">
                <span>Size limits</span>
                <span>
                  symbols {formatChars(report.limits.max_chunk_characters)} ·
                  text {formatChars(report.limits.text_chunk_characters)} with{' '}
                  {formatChars(report.limits.text_chunk_overlap_characters)}{' '}
                  overlap · split depth {report.limits.max_split_depth}
                </span>
              </div>

              <div className="chunk-summary">
                <span>Grammars</span>
                <span>
                  {Object.entries(report.grammar_versions)
                    .map(([name, version]) => `${name} ${version}`)
                    .join(' · ')}
                </span>
              </div>

              {report.files.length > 0 && (
                <ul className="inspector-list inspector-file-list">
                  {report.files.slice(0, MAX_FILE_ROWS).map((file) => (
                    <li key={file.file_path}>
                      <div className="inspector-file-row">
                        <code className="chunk-file">{file.file_path}</code>
                        <span className="chunk-type-tag">
                          {file.mode === 'structural'
                            ? file.language
                            : 'text chunks'}
                        </span>
                        <span className="tree-lines">
                          {file.structures} symbols · {file.chunks} chunks
                          {file.has_errors ? ' · recovered errors' : ''}
                        </span>
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {report.files_truncated && (
                <p className="hint">
                  File rows are limited to the first {MAX_FILE_ROWS} of{' '}
                  {report.files_scanned} scanned files.
                </p>
              )}
            </>
          )}

          {reportStatus === 'loading' && !report && (
            <p className="loading-note" role="status">
              Re-running ingestion over the extracted files to count structures
              and chunks…
            </p>
          )}
        </div>
      )}
    </div>
  )
}
