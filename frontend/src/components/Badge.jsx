export function PriorityBadge({ priority }) {
  const styles = {
    P0: { background: 'var(--p0-bg)', color: 'var(--p0-text)',
          border: '1px solid var(--p0-border)' },
    P1: { background: 'var(--p1-bg)', color: 'var(--p1-text)',
          border: '1px solid var(--p1-border)' },
    P2: { background: 'var(--p2-bg)', color: 'var(--p2-text)',
          border: '1px solid var(--p2-border)' },
  }
  return (
    <span style={{
      ...styles[priority],
      padding: '2px 8px',
      borderRadius: '99px',
      fontSize: '12px',
      fontWeight: 600,
      letterSpacing: '0.03em',
    }}>
      {priority}
    </span>
  )
}

export function StatusBadge({ status }) {
  const styles = {
    OPEN:          { background: 'var(--open-bg)',
                     color: 'var(--open-text)' },
    INVESTIGATING: { background: 'var(--investigating-bg)',
                     color: 'var(--investigating-text)' },
    RESOLVED:      { background: 'var(--resolved-bg)',
                     color: 'var(--resolved-text)' },
    CLOSED:        { background: 'var(--closed-bg)',
                     color: 'var(--closed-text)' },
  }
  return (
    <span style={{
      ...styles[status] ?? {},
      padding: '2px 8px',
      borderRadius: '99px',
      fontSize: '12px',
      fontWeight: 500,
    }}>
      {status}
    </span>
  )
}
