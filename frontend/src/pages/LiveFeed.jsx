import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchIncidents } from '../api/client'
import { PriorityBadge, StatusBadge } from '../components/Badge'

function timeAgo(dateStr) {
  const diff = Math.floor((Date.now() - new Date(dateStr)) / 1000)
  if (diff < 60)  return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export default function LiveFeed() {
  const [data, setData]       = useState(null)
  const [error, setError]     = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const [countdown, setCountdown]     = useState(5)
  const navigate = useNavigate()
  const intervalRef = useRef(null)

  const load = () => {
    fetchIncidents()
      .then(d => {
        setData(d)
        setError(null)
        setLastRefresh(new Date())
        setCountdown(5)
      })
      .catch(e => setError(e.message))
  }

  useEffect(() => {
    load()
    intervalRef.current = setInterval(load, 5_000)
    const tick = setInterval(() => setCountdown(c => Math.max(0, c - 1)), 1_000)
    return () => {
      clearInterval(intervalRef.current)
      clearInterval(tick)
    }
  }, [])

  return (
    <div className="page">
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between', marginBottom: 24 }}>
        <div>
          <h1 style={{ fontSize: 22, fontWeight: 600 }}>Live incident feed</h1>
          <p style={{ color: 'var(--text-muted)', fontSize: 13, marginTop: 4 }}>
            Auto-refreshes every 5 seconds · {countdown}s until next refresh
          </p>
        </div>
        <button className="btn-secondary" onClick={load} style={{ fontSize: 13 }}>
          Refresh now
        </button>
      </div>

      {error && <div className="error-box">Failed to load incidents: {error}</div>}

      {/* Stats row */}
      {data && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)',
                      gap: 12, marginBottom: 24 }}>
          {[
            { label: 'Total active', value: data.total },
            { label: 'P0 critical',
              value: data.incidents.filter(i => i.priority === 'P0').length,
              color: 'var(--p0-text)' },
            { label: 'P1 high',
              value: data.incidents.filter(i => i.priority === 'P1').length,
              color: 'var(--p1-text)' },
            { label: 'P2 medium',
              value: data.incidents.filter(i => i.priority === 'P2').length,
              color: 'var(--p2-text)' },
          ].map(({ label, value, color }) => (
            <div key={label} className="card" style={{ padding: '16px 20px' }}>
              <div style={{ fontSize: 24, fontWeight: 600,
                            color: color ?? 'var(--text)' }}>
                {value}
              </div>
              <div style={{ fontSize: 12, color: 'var(--text-muted)',
                            marginTop: 2 }}>
                {label}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Incident table */}
      <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
        {!data ? (
          <div style={{ padding: 24, color: 'var(--text-muted)' }}>
            <span className="spinner" /> Loading…
          </div>
        ) : data.incidents.length === 0 ? (
          <div style={{ padding: 40, textAlign: 'center',
                        color: 'var(--text-muted)' }}>
            <div style={{ fontSize: 32, marginBottom: 8 }}>✓</div>
            <div style={{ fontWeight: 500 }}>All clear — no active incidents</div>
            <div style={{ fontSize: 13, marginTop: 4 }}>
              Incidents appear here within seconds of the first signal arriving.
            </div>
          </div>
        ) : (
          <table>
            <thead>
              <tr>
                <th>Priority</th>
                <th>Component</th>
                <th>Type</th>
                <th>Status</th>
                <th>Signals</th>
                <th>Created</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.incidents.map(incident => (
                <tr
                  key={incident.id}
                  style={{ cursor: 'pointer' }}
                  onClick={() => navigate(`/incidents/${incident.id}`)}
                >
                  <td><PriorityBadge priority={incident.priority} /></td>
                  <td style={{ fontWeight: 500, fontSize: 14 }}>
                    {incident.component_id}
                  </td>
                  <td>
                    <code style={{ fontSize: 12, background: 'var(--bg)',
                                   padding: '2px 6px', borderRadius: 4 }}>
                      {incident.component_type}
                    </code>
                  </td>
                  <td><StatusBadge status={incident.status} /></td>
                  <td style={{ fontSize: 14 }}>{incident.signal_count}</td>
                  <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    {timeAgo(incident.created_at)}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: 13, color: 'var(--accent)' }}>
                      View →
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>

      {lastRefresh && (
        <p style={{ fontSize: 12, color: 'var(--text-muted)',
                    marginTop: 12, textAlign: 'right' }}>
          Last updated: {lastRefresh.toLocaleTimeString()}
        </p>
      )}
    </div>
  )
}
