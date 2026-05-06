import { useState, useEffect } from 'react'
import { fetchSignals } from '../api/client'

export default function SignalList({ incidentId }) {
  const [data, setData]     = useState(null)
  const [skip, setSkip]     = useState(0)
  const [loading, setLoading] = useState(false)
  const limit = 20

  useEffect(() => {
    setLoading(true)
    fetchSignals(incidentId, limit, skip)
      .then(setData)
      .finally(() => setLoading(false))
  }, [incidentId, skip])

  if (!data) return (
    <div style={{ color: 'var(--text-muted)', fontSize: 14, padding: '16px 0' }}>
      <span className="spinner" /> Loading signals…
    </div>
  )

  if (data.signals.length === 0) return (
    <p style={{ color: 'var(--text-muted)', fontSize: 14 }}>
      No signals linked yet. They arrive within a few seconds of ingestion.
    </p>
  )

  return (
    <div>
      <div style={{ display: 'flex', alignItems: 'center',
                    justifyContent: 'space-between', marginBottom: 12 }}>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
          {data.total} signal{data.total !== 1 ? 's' : ''} total
          {loading && <span className="spinner" style={{ marginLeft: 8 }} />}
        </span>
        <div style={{ display: 'flex', gap: 8 }}>
          <button
            className="btn-secondary"
            style={{ padding: '4px 12px', fontSize: 13 }}
            disabled={skip === 0}
            onClick={() => setSkip(s => Math.max(0, s - limit))}
          >← Prev</button>
          <button
            className="btn-secondary"
            style={{ padding: '4px 12px', fontSize: 13 }}
            disabled={skip + limit >= data.total}
            onClick={() => setSkip(s => s + limit)}
          >Next →</button>
        </div>
      </div>

      <div style={{ overflowX: 'auto' }}>
        <table>
          <thead>
            <tr>
              <th>Time</th>
              <th>Error code</th>
              <th>Severity</th>
              <th>Latency</th>
              <th>Message</th>
              <th>Host</th>
            </tr>
          </thead>
          <tbody>
            {data.signals.map(s => (
              <tr key={s.signal_id}>
                <td style={{ whiteSpace: 'nowrap', fontSize: 12,
                             color: 'var(--text-muted)' }}>
                  {new Date(s.timestamp).toLocaleTimeString()}
                </td>
                <td>
                  <code style={{ fontSize: 12, background: 'var(--bg)',
                                 padding: '2px 6px', borderRadius: 4 }}>
                    {s.error_code}
                  </code>
                </td>
                <td style={{ fontSize: 13, fontWeight: 500 }}>{s.severity}</td>
                <td style={{ fontSize: 13 }}>{s.latency_ms} ms</td>
                <td style={{ fontSize: 13, maxWidth: 280,
                             overflow: 'hidden', textOverflow: 'ellipsis',
                             whiteSpace: 'nowrap' }}>
                  {s.message}
                </td>
                <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>
                  {s.source_host ?? '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
