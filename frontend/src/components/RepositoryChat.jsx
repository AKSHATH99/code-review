import { useEffect, useRef, useState } from 'react'

const STORAGE_PREFIX = 'gitscope.chat.'
const STORAGE_VERSION = 1

function storageKey(repository) {
  return `${STORAGE_PREFIX}${repository}`
}

function isTurn(turn) {
  return Boolean(
    turn && typeof turn.id === 'string' && typeof turn.question === 'string',
  )
}

function recoverPending(turn) {
  if (turn.status !== 'pending') return turn
  return {
    ...turn,
    status: 'failed',
    error: 'Interrupted — the page reloaded before the answer arrived.',
  }
}

function loadHistory(repository, initialQuestion) {
  const empty = { turns: [], draft: initialQuestion || '' }
  if (!repository) return empty

  try {
    const raw = window.localStorage.getItem(storageKey(repository))
    if (!raw) return empty
    const parsed = JSON.parse(raw)
    const turns = Array.isArray(parsed?.turns)
      ? parsed.turns.filter(isTurn).map(recoverPending)
      : []
    return {
      turns,
      draft:
        typeof parsed?.draft === 'string' && parsed.draft
          ? parsed.draft
          : turns.length
            ? ''
            : initialQuestion || '',
    }
  } catch {
    return empty
  }
}

function newTurn(question, attachmentPath) {
  return {
    id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    question,
    attachment_path: attachmentPath || null,
    asked_at: new Date().toISOString(),
    status: 'pending',
    answer: null,
    error: null,
    provider: null,
    model: null,
    total_chunks: null,
    sources: [],
    elapsed_ms: null,
  }
}

function answered(turn, result, elapsedMs) {
  return {
    ...turn,
    status: 'answered',
    answer: result.answer ?? '',
    provider: result.provider ?? null,
    model: result.model ?? null,
    total_chunks: result.total_chunks ?? null,
    sources: result.sources ?? [],
    elapsed_ms: elapsedMs,
  }
}

function failed(turn, message, elapsedMs) {
  return { ...turn, status: 'failed', error: message, elapsed_ms: elapsedMs }
}

function formatTime(value) {
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return date.toLocaleTimeString([], {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
  })
}

function exportName(repository) {
  const slug = repository.replace(/[^a-z0-9._-]+/gi, '-') || 'repository'
  const stamp = new Date().toISOString().replace(/[:.]/g, '-')
  return `gitscope-chat-${slug}-${stamp}.json`
}

export default function RepositoryChat({
  repository,
  ready,
  gateMessage,
  busy,
  onSend,
  attachmentPath,
  providerLabel,
  initialQuestion = '',
  attachmentSlot = null,
}) {
  const [history, setHistory] = useState(() =>
    loadHistory(repository, initialQuestion),
  )
  const [pendingId, setPendingId] = useState(null)
  const [storageError, setStorageError] = useState('')
  const transcriptRef = useRef(null)

  useEffect(() => {
    setHistory(loadHistory(repository, initialQuestion))
    setPendingId(null)
  }, [repository, initialQuestion])

  useEffect(() => {
    if (!repository) return
    try {
      window.localStorage.setItem(
        storageKey(repository),
        JSON.stringify({
          version: STORAGE_VERSION,
          repository,
          turns: history.turns,
          draft: history.draft,
        }),
      )
      setStorageError('')
    } catch {
      setStorageError(
        'This conversation is too large to keep in local storage. Export it before clearing.',
      )
    }
  }, [history, repository])

  useEffect(() => {
    const node = transcriptRef.current
    if (node) node.scrollTop = node.scrollHeight
  }, [history.turns.length, pendingId])

  const locked = !ready || busy || Boolean(pendingId)

  async function ask(question) {
    const text = question.trim()
    if (!text || locked) return

    const turn = newTurn(text, attachmentPath)
    setHistory((previous) => ({
      ...previous,
      turns: [...previous.turns, turn],
      draft: '',
    }))
    setPendingId(turn.id)
    const started = performance.now()

    try {
      const result = await onSend(text)
      const elapsed = Math.round(performance.now() - started)
      setHistory((previous) => ({
        ...previous,
        turns: previous.turns.map((item) =>
          item.id === turn.id ? answered(item, result, elapsed) : item,
        ),
      }))
    } catch (error) {
      const elapsed = Math.round(performance.now() - started)
      setHistory((previous) => ({
        ...previous,
        turns: previous.turns.map((item) =>
          item.id === turn.id ? failed(item, error.message, elapsed) : item,
        ),
      }))
    } finally {
      setPendingId(null)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    ask(history.draft)
  }

  function handleClear() {
    if (pendingId) return
    if (
      !window.confirm(
        'Clear the saved conversation for this repository? Export it first if you still need it.',
      )
    ) {
      return
    }
    try {
      window.localStorage.removeItem(storageKey(repository))
    } catch {
      setStorageError('The saved conversation could not be removed.')
    }
    setHistory({ turns: [], draft: initialQuestion || '' })
  }

  function handleExport() {
    const payload = {
      schema: 'gitscope.chat/v1',
      repository,
      exported_at: new Date().toISOString(),
      turn_count: history.turns.length,
      turns: history.turns,
    }
    const blob = new Blob([JSON.stringify(payload, null, 2)], {
      type: 'application/json',
    })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = exportName(repository)
    document.body.append(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <>
      <div className="chunks-header">
        <div>
          <span className="result-label">Ask the repository</span>
          <p className="hint">
            The fifteen most relevant chunks are retrieved per question, plus
            any attached file. History stays in this browser — resend after
            reload to compare answers.
          </p>
        </div>
        <div className="chat-toolbar">
          <button
            type="button"
            className="secondary-button"
            onClick={handleExport}
            disabled={history.turns.length === 0}
          >
            Export JSON
          </button>
          <button
            type="button"
            className="secondary-button"
            onClick={handleClear}
            disabled={history.turns.length === 0 || Boolean(pendingId)}
          >
            Clear chat
          </button>
        </div>
      </div>

      {!ready && (
        <p className="loading-note" role="status">
          {gateMessage}
        </p>
      )}

      {storageError && (
        <p className="error-message" role="alert">
          {storageError}
        </p>
      )}

      <div className="chat-transcript" ref={transcriptRef} role="log">
        {history.turns.length === 0 && ready && (
          <p className="chat-empty">
            No questions yet. Answers stay here across reloads — useful for
            comparing retrieval runs.
          </p>
        )}

        {history.turns.map((turn, index) => (
          <article className="chat-turn" key={turn.id}>
            <div className="chat-turn-head">
              <span className="chat-turn-index">#{index + 1}</span>
              <span className="chat-turn-time">{formatTime(turn.asked_at)}</span>
              {turn.model && (
                <span className="chat-turn-model">
                  {providerLabel(turn.provider)} · {turn.model}
                </span>
              )}
              {turn.elapsed_ms !== null && (
                <span className="chat-turn-time">
                  {(turn.elapsed_ms / 1000).toFixed(1)}s
                </span>
              )}
              <button
                type="button"
                className="secondary-button chat-resend"
                onClick={() => ask(turn.question)}
                disabled={locked}
              >
                Resend
              </button>
            </div>

            <p className="chat-question">{turn.question}</p>

            {turn.attachment_path && (
              <span className="chat-attachment">
                attached {turn.attachment_path}
              </span>
            )}

            {turn.status === 'pending' && (
              <p className="loading-note" role="status">
                Retrieving relevant chunks and waiting for the model…
              </p>
            )}

            {turn.status === 'failed' && (
              <p className="error-message" role="alert">
                {turn.error}
              </p>
            )}

            {turn.answer && (
              <pre className="chunk-code chat-answer">
                <code>{turn.answer}</code>
              </pre>
            )}

            {turn.status === 'answered' && (
              <div className="chat-context">
                {turn.sources.length === 0 && (
                  <p className="notice">
                    No repository chunks were retrieved for this question.
                  </p>
                )}
                <p className="search-summary">
                  Top {turn.sources.length} of{' '}
                  {(turn.total_chunks ?? 0).toLocaleString()} chunks used as
                  context.
                </p>
                {turn.sources.length > 0 && (
                  <details className="chat-sources">
                    <summary>
                      Retrieved sources ({turn.sources.length})
                    </summary>
                    <div className="search-results">
                      {turn.sources.map((source, rank) => (
                        <article
                          className="search-result"
                          key={`${source.file_path}-${source.chunk_index}`}
                        >
                          <div className="search-result-head">
                            <span className="search-rank">#{rank + 1}</span>
                            <code className="search-path">
                              {source.file_path}
                            </code>
                            <span className="search-score">
                              {source.rrf_score != null
                                ? `rrf ${source.rrf_score.toFixed(4)}`
                                : `similarity ${source.similarity.toFixed(4)}`}
                            </span>
                          </div>
                          <div className="search-meta">
                            Chunk #{source.chunk_index} · lines {source.start_line}
                            –{source.end_line}
                          </div>
                          <pre className="chunk-code search-code">
                            <code>{source.content}</code>
                          </pre>
                        </article>
                      ))}
                    </div>
                  </details>
                )}
              </div>
            )}
          </article>
        ))}
      </div>

      {attachmentSlot}

      {ready && (
        <form className="chat-form" onSubmit={handleSubmit}>
          <label className="field-label" htmlFor="chat-question">
            Question
          </label>
          <div className="input-row">
            <input
              id="chat-question"
              type="text"
              value={history.draft}
              onChange={(event) =>
                setHistory((previous) => ({
                  ...previous,
                  draft: event.target.value,
                }))
              }
              placeholder="How does authentication work?"
              autoComplete="off"
              maxLength={4000}
              disabled={locked}
            />
            <button type="submit" disabled={locked || !history.draft.trim()}>
              {pendingId ? 'Thinking…' : 'Send'}
            </button>
          </div>
        </form>
      )}
    </>
  )
}