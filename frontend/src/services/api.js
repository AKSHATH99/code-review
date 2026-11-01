const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

async function requestJson(path, { timeoutMs = 15000, ...options } = {}) {
  const controller = new AbortController()
  const timeout = setTimeout(() => controller.abort(), timeoutMs)

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      signal: controller.signal,
    })

    if (!response.ok) {
      let detail = null
      try {
        const body = await response.json()
        detail = body.detail
      } catch {
        detail = null
      }
      throw new Error(detail || `Request failed with status ${response.status}`)
    }

    return await response.json()
  } catch (error) {
    if (error.name === 'AbortError') {
      throw new Error('The request timed out. Check that the backend is running.')
    }
    if (error instanceof TypeError) {
      throw new Error('Could not reach the backend. Make sure it is running.')
    }
    throw error
  } finally {
    clearTimeout(timeout)
  }
}

export function fetchHealth() {
  return requestJson('/health', { timeoutMs: 5000 })
}

export function fetchGenerationProvider() {
  return requestJson('/api/ollama/provider', { timeoutMs: 10000 })
}

export function fetchRepositoryDetails(repoUrl) {
  return requestJson(
    `/repositories/details?repo_url=${encodeURIComponent(repoUrl)}`,
  )
}

export function fetchRepositoryChunks(repoUrl) {
  return requestJson(
    `/repositories/chunks?repo_url=${encodeURIComponent(repoUrl)}`,
    { timeoutMs: 120000 },
  )
}

export function fetchRepositoryFiles(repoUrl) {
  return requestJson(
    `/repositories/files?repo_url=${encodeURIComponent(repoUrl)}`,
    { timeoutMs: 120000 },
  )
}

export function fetchRepositoryStats(repoUrl) {
  return requestJson(
    `/repositories/stats?repo_url=${encodeURIComponent(repoUrl)}`,
    { timeoutMs: 120000 },
  )
}

export function fetchRepositoryFile(repoUrl, filePath) {
  return requestJson(
    `/repositories/file?repo_url=${encodeURIComponent(repoUrl)}&path=${encodeURIComponent(filePath)}`,
    { timeoutMs: 30000 },
  )
}

export function fetchRepositoryEmbeddings(repoUrl) {
  return requestJson('/repositories/embeddings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl }),
    timeoutMs: 300000,
  })
}

export function searchRepository(repoUrl, query) {
  return requestJson('/repositories/search', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl, query }),
    timeoutMs: 120000,
  })
}

export function downloadRepository(repoUrl) {
  return requestJson('/repositories/download', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl }),
    timeoutMs: 120000,
  })
}

export function sendOllamaMessage(message) {
  return requestJson('/api/ollama/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message }),
    timeoutMs: 180000,
  })
}

export function analyzeRepository(repoUrl) {
  return requestJson('/repositories/analysis', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ repo_url: repoUrl }),
    timeoutMs: 1800000,
  })
}

export function askRepositoryQuestion({ repoUrl, question, attachment }) {
  const payload = { repo_url: repoUrl, question }
  if (attachment) {
    payload.attachment = {
      file_path: attachment.file_path,
      content: attachment.content,
    }
  }

  return requestJson('/api/ollama/ask', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
    timeoutMs: 300000,
  })
}
