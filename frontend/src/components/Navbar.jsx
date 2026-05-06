import { Link, useLocation } from 'react-router-dom'
import { useState, useEffect } from 'react'
import { fetchHealth } from '../api/client'

export default function Navbar() {
  const { pathname } = useLocation()
  const [health, setHealth] = useState(null)

  useEffect(() => {
    fetchHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: 'unreachable' }))

    const t = setInterval(() => {
      fetchHealth()
        .then(setHealth)
        .catch(() => setHealth({ status: 'unreachable' }))
    }, 15_000)
    return () => clearInterval(t)
  }, [])

  const dot = health?.status === 'ok'
    ? { background: '#22c55e' }
    : { background: '#ef4444' }

  return (
    <nav style={{
      background: 'var(--surface)',
      borderBottom: '1px solid var(--border)',
      padding: '0 24px',
      display: 'flex',
      alignItems: 'center',
      gap: '32px',
      height: '54px',
      position: 'sticky',
      top: 0,
      zIndex: 10,
    }}>
      <Link to="/" style={{
        fontWeight: 700,
        fontSize: '15px',
        color: 'var(--text)',
        letterSpacing: '-0.01em',
      }}>
        IMS
      </Link>

      <Link to="/" style={{
        fontSize: '14px',
        color: pathname === '/' ? 'var(--accent)' : 'var(--text-muted)',
        fontWeight: pathname === '/' ? 600 : 400,
      }}>
        Live Feed
      </Link>

      <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: '8px' }}>
        <span style={{
          width: 8, height: 8, borderRadius: '50%',
          display: 'inline-block', ...dot,
        }} />
        <span style={{ fontSize: '13px', color: 'var(--text-muted)' }}>
          {health?.status ?? 'checking…'}
        </span>
      </div>
    </nav>
  )
}
