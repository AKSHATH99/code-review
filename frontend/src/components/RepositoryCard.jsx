function formatCount(value) {
  return (value ?? 0).toLocaleString('en-US')
}

function formatDate(value) {
  if (!value) return 'unknown'

  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return 'unknown'

  return date.toLocaleDateString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
  })
}

export default function RepositoryCard({ repo }) {
  return (
    <article className="repo-card">
      <div className="repo-header">
        <div>
          <p className="repo-owner">{repo.owner}</p>
          <h2 className="repo-name">{repo.name}</h2>
        </div>
        <a
          className="repo-link"
          href={repo.html_url}
          target="_blank"
          rel="noreferrer"
        >
          View on GitHub ↗
        </a>
      </div>

      <p className={repo.description ? 'repo-description' : 'repo-description muted'}>
        {repo.description || 'No description provided.'}
      </p>

      <dl className="repo-stats">
        <div>
          <dt>Stars</dt>
          <dd>{formatCount(repo.stars)}</dd>
        </div>
        <div>
          <dt>Forks</dt>
          <dd>{formatCount(repo.forks)}</dd>
        </div>
        <div>
          <dt>Language</dt>
          <dd>{repo.language || '—'}</dd>
        </div>
        <div>
          <dt>Default branch</dt>
          <dd>{repo.default_branch || '—'}</dd>
        </div>
      </dl>

      <p className="repo-updated">Last updated {formatDate(repo.updated_at)}</p>
    </article>
  )
}
