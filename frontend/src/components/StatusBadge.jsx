const LABELS = {
  running: 'Running',
  checking: 'Checking…',
  connected: 'Connected',
  disconnected: 'Disconnected',
  downloading: 'Downloading…',
  downloaded: 'Downloaded',
  processing: 'Processing…',
  ready: 'Ready',
  queued: 'Queued',
  failed: 'Failed',
}

export default function StatusBadge({ status }) {
  return (
    <span className="status-badge" data-status={status} role="status">
      <span className="status-dot" aria-hidden="true" />
      {LABELS[status] ?? status}
    </span>
  )
}
