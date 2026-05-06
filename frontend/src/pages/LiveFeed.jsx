import { Fragment, useState, useEffect, useRef } from 'react'
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
  const [expandedRoots, setExpandedRoots] = useState({})  // Track which roots are expanded
  const navigate = useNavigate()
  const intervalRef = useRef(null)

  // Toggle expand/collapse for a root incident
  const toggleExpand = (rootId) => {
    setExpandedRoots(prev => ({
      ...prev,
      [rootId]: !prev[rootId]
    }))
  }

  const load = () => {
    fetchIncidents(true)
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

  // Group incidents: root incidents and cascaded incidents
  const groupIncidents = () => {
    if (!data || !data.incidents) return { roots: [], cascaded: {} }
    
    const cascadedMap = {}  // cascaded_id -> root_id
    const cascadedByRoot = {}  // root_id -> [cascaded_ids]
    
    // First pass: identify root incidents and build cascaded map
    data.incidents.forEach(inc => {
      if (inc.correlation?.is_cascaded_from) {
        cascadedMap[inc.id] = inc.correlation.is_cascaded_from
        if (!cascadedByRoot[inc.correlation.is_cascaded_from]) {
          cascadedByRoot[inc.correlation.is_cascaded_from] = []
        }
        cascadedByRoot[inc.correlation.is_cascaded_from].push(inc.id)
      }
    })
    
    // Identify root incidents (not cascaded from anything)
    const roots = data.incidents.filter(inc => !cascadedMap[inc.id])
    
    return { roots, cascadedByRoot }
  }

  const { roots, cascadedByRoot } = groupIncidents()

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
      <div className="card" style={{ padding: 0, overflowX: 'auto' }}>
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
          <table className="incident-table">
            <colgroup>
              <col className="incident-table__expand" />
              <col className="incident-table__priority" />
              <col className="incident-table__component" />
              <col className="incident-table__type" />
              <col className="incident-table__status" />
              <col className="incident-table__signals" />
              <col className="incident-table__created" />
              <col className="incident-table__actions" />
            </colgroup>
            <thead>
              <tr>
                <th></th>
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
              {/* Render root incidents with their cascaded children */}
              {roots.map(rootIncident => {
                const cascadedIds = cascadedByRoot[rootIncident.id] || []
                const isExpanded = expandedRoots[rootIncident.id] !== false
                const hasCascaded = cascadedIds.length > 0
                
                return (
                  <Fragment key={rootIncident.id}>
                    {/* Root incident row */}
                    <tr
                      style={{ 
                        cursor: 'pointer',
                        backgroundColor: hasCascaded ? 'var(--bg-hover)' : 'transparent'
                      }}
                      onClick={() => navigate(`/incidents/${rootIncident.id}`)}
                    >
                      <td style={{ width: 24, textAlign: 'center' }}>
                        {hasCascaded && (
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              toggleExpand(rootIncident.id)
                            }}
                            style={{
                              background: 'none',
                              border: 'none',
                              cursor: 'pointer',
                              fontSize: 14,
                              color: 'var(--text)',
                              padding: '0 4px'
                            }}
                            title={isExpanded ? 'Collapse' : 'Expand'}
                          >
                            {isExpanded ? '▼' : '▶'}
                          </button>
                        )}
                      </td>
                      <td><PriorityBadge priority={rootIncident.priority} /></td>
                      <td style={{ fontWeight: 500, fontSize: 14 }}>
                        {rootIncident.component_id}
                      </td>
                      <td>
                        <code style={{ fontSize: 12, background: 'var(--bg)',
                                       padding: '2px 6px', borderRadius: 4 }}>
                          {rootIncident.component_type}
                        </code>
                      </td>
                      <td><StatusBadge status={rootIncident.status} /></td>
                      <td style={{ fontSize: 14 }}>{rootIncident.signal_count}</td>
                      <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                        {timeAgo(rootIncident.created_at)}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        {hasCascaded && (
                          <span style={{ fontSize: 11, color: 'var(--text-muted)',
                                         background: 'var(--bg)', padding: '2px 6px',
                                         borderRadius: 3, marginRight: 8 }}>
                            {cascadedIds.length} cascaded
                          </span>
                        )}
                        <span style={{ fontSize: 13, color: 'var(--accent)' }}>
                          View →
                        </span>
                      </td>
                    </tr>
                    
                    {/* Cascaded incidents (if expanded) */}
                    {hasCascaded && isExpanded && cascadedIds.map(cascadedId => {
                      const cascadedInc = data.incidents.find(i => i.id === cascadedId)
                      if (!cascadedInc) return null
                      return (
                        <tr
                          key={cascadedId}
                          style={{
                            cursor: 'pointer',
                            backgroundColor: 'var(--bg)',
                          }}
                          onClick={() => navigate(`/incidents/${cascadedId}`)}
                        >
                          <td style={{ width: 24 }}></td>
                          <td style={{ paddingLeft: 32 }}>
                            <PriorityBadge priority={cascadedInc.priority} />
                          </td>
                          <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                            ↳ {cascadedInc.component_id}
                          </td>
                          <td>
                            <code style={{ fontSize: 12, background: 'transparent',
                                           padding: '2px 6px', color: 'var(--text-muted)' }}>
                              {cascadedInc.component_type}
                            </code>
                          </td>
                          <td><StatusBadge status={cascadedInc.status} /></td>
                          <td style={{ fontSize: 14 }}>{cascadedInc.signal_count}</td>
                          <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                            {timeAgo(cascadedInc.created_at)}
                          </td>
                          <td style={{ textAlign: 'right', fontSize: 11 }}>
                            <span style={{ color: 'var(--text-muted)', marginRight: 8 }}>
                              🔴 cascaded
                            </span>
                          </td>
                        </tr>
                      )
                    })}
                  </Fragment>
                )
              })}

              {/* Show independent cascaded incidents (shown in list but also under root) */}
              {data.incidents.filter(inc => inc.correlation?.is_cascaded_from).map(cascadedInc => (
                <tr
                  key={`independent-${cascadedInc.id}`}
                  style={{ cursor: 'pointer', opacity: 0.7 }}
                  onClick={() => navigate(`/incidents/${cascadedInc.id}`)}
                >
                  <td style={{ width: 24 }}></td>
                  <td><PriorityBadge priority={cascadedInc.priority} /></td>
                  <td style={{ fontWeight: 500, fontSize: 14 }}>
                    {cascadedInc.component_id}
                  </td>
                  <td>
                    <code style={{ fontSize: 12, background: 'var(--bg)',
                                   padding: '2px 6px', borderRadius: 4 }}>
                      {cascadedInc.component_type}
                    </code>
                  </td>
                  <td><StatusBadge status={cascadedInc.status} /></td>
                  <td style={{ fontSize: 14 }}>{cascadedInc.signal_count}</td>
                  <td style={{ fontSize: 13, color: 'var(--text-muted)' }}>
                    {timeAgo(cascadedInc.created_at)}
                  </td>
                  <td style={{ textAlign: 'right' }}>
                    <span style={{ fontSize: 11, background: 'var(--p0-bg)',
                                   color: 'var(--p0-text)', padding: '2px 6px',
                                   borderRadius: 3, marginRight: 8 }}>
                      🔴 cascaded from {cascadedInc.correlation.is_cascaded_from.slice(0, 8)}
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
