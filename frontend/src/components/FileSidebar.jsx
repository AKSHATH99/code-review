export default function FileSidebar({
  files,
  status,
  error,
  selectedPath,
  onSelect,
}) {
  return (
    <aside className="file-sidebar" aria-label="Repository files">
      <div className="file-sidebar-head">
        <span className="result-label">Files</span>
        {status === 'success' && (
          <span className="file-count">{files.length}</span>
        )}
      </div>

      {status === 'loading' && (
        <p className="loading-note" role="status">
          Loading files…
        </p>
      )}

      {status === 'error' && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}

      {status === 'success' && files.length === 0 && (
        <p className="notice file-empty">No text files found.</p>
      )}

      {status === 'success' && files.length > 0 && (
        <ul className="file-list">
          {files.map((file) => {
            const separator = file.file_path.lastIndexOf('/')
            const name =
              separator === -1
                ? file.file_path
                : file.file_path.slice(separator + 1)
            const directory =
              separator === -1 ? '' : file.file_path.slice(0, separator)
            const selected = selectedPath === file.file_path

            return (
              <li key={file.file_path}>
                <button
                  type="button"
                  className={`file-item${selected ? ' is-active' : ''}`}
                  onClick={() => onSelect(file)}
                  title={file.file_path}
                  aria-pressed={selected}
                >
                  <span className="file-name">{name}</span>
                  {directory && <span className="file-dir">{directory}</span>}
                </button>
              </li>
            )
          })}
        </ul>
      )}
    </aside>
  )
}
