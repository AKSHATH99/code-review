function lineRange(node) {
  return node.start_line === node.end_line
    ? `${node.start_line}`
    : `${node.start_line}–${node.end_line}`
}

function NodeLabel({ node }) {
  return (
    <>
      <code className="tree-type">{node.type}</code>
      <span className="tree-lines">{lineRange(node)}</span>
      <span className="tree-preview">{node.preview || '—'}</span>
    </>
  )
}

function TreeNode({ node, depth }) {
  const children = node.children ?? []
  const className = [
    'tree-node',
    node.named ? '' : 'tree-node-anonymous',
    node.has_error ? 'tree-node-error' : '',
  ]
    .filter(Boolean)
    .join(' ')

  if (children.length === 0) {
    return (
      <li className={className}>
        <span className="tree-leaf">
          <NodeLabel node={node} />
        </span>
      </li>
    )
  }

  return (
    <li className={className}>
      <details open={depth < 1}>
        <summary>
          <NodeLabel node={node} />
          <span className="tree-count">{children.length}</span>
        </summary>
        <ul className="tree-children">
          {children.map((child, index) => (
            <TreeNode
              key={`${child.type}:${child.start_line}:${child.start_index ?? 0}:${index}`}
              node={child}
              depth={depth + 1}
            />
          ))}
        </ul>
      </details>
    </li>
  )
}

export default function SyntaxTree({ nodes, truncated, emptyMessage }) {
  if (!nodes || nodes.length === 0) {
    return (
      <p className="notice">
        {emptyMessage ?? 'No syntax tree was returned for this file.'}
      </p>
    )
  }

  return (
    <div className="syntax-tree">
      {truncated && (
        <p className="hint">
          Only the first part of this tree is shown to keep the view readable.
        </p>
      )}
      <ul className="tree-children">
        {nodes.map((node, index) => (
          <TreeNode
            key={`${node.type}:${node.start_line}:${index}`}
            node={node}
            depth={0}
          />
        ))}
      </ul>
    </div>
  )
}
