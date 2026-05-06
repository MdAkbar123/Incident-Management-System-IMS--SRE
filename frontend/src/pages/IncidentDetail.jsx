import { useState, useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { fetchIncident, updateStatus } from '../api/client'
import { PriorityBadge, StatusBadge } from '../components/Badge'
import SignalList from '../components/SignalList'
import TimelineVisualization from '../components/TimelineVisualization'
import IncidentRelationships from '../components/IncidentRelationships'

const TRANSITIONS = {
  OPEN:          ['INVESTIGATING'],
  INVESTIGATING: ['RESOLVED'],
  RESOLVED:      [],
  CLOSED:        [],
}

function formatDate(str) {
  if (!str) return '—'
  // Backend always sends UTC ISO-8601 with a 'Z' suffix.
  // new Date() parses that correctly; toLocaleString() converts to
  // the browser's local timezone for display — intentional.
  return new Date(str).toLocaleString()
}

export default function IncidentDetail() {
  const { id } = useParams()
  const navigate = useNavigate()
  const [incident, setIncident] = useState(null)
  const [timeline, setTimeline] = useState(null)
  const [error, setError]       = useState(null)
  const [transitioning, setTransitioning] = useState(false)
  const [transitionError, setTransitionError] = useState(null)

  const load = () => {
    fetchIncident(id)
      .then(setIncident)
      .catch(e => setError(e.response?.data?.detail ?? e.message))

    fetch(`/api/incidents/${id}/timeline`)
      .then(r => r.json())
      .then(setTimeline)
      .catch(() => setTimeline(null))
  }

  useEffect(() => { load() }, [id])

  const handleTransition = async (status) => {
    setTransitioning(true)
    setTransitionError(null)
    try {
      const updated = await updateStatus(id, status)
      setIncident(prev => ({ ...prev, ...updated }))
    } catch (e) {
      setTransitionError(e.response?.data?.detail ?? e.message)
    } finally {
      setTransitioning(false)
    }
  }

  if (error) return (
    <div className="page">
      <div className="error-box">{error}</div>
      <button className="btn-secondary" onClick={() => navigate('/')}>
        ← Back to feed
      </button>
    </div>
  )

  if (!incident) return (
    <div className="page" style={{ color: 'var(--text-muted)' }}>
      <span className="spinner" /> Loading incident…
    </div>
  )

  const nextStates = TRANSITIONS[incident.status] ?? []

  // Only show "Resolved at" once the incident has actually been resolved.
  // incident.resolved_at is null until the RESOLVED transition is stamped
  // server-side — using updated_at here was the bug (it's set on creation).
  const isResolved = ['RESOLVED', 'CLOSED'].includes(incident.status)

  const detailRows = [
    ['Component type', incident.component_type],
    ['Priority',       incident.priority],
    ['Status',         incident.status],
    ['Signal count',   incident.signal_count],
    ['Detected at',    formatDate(incident.created_at)],
    // Row is only included when the incident has reached RESOLVED/CLOSED
    // and a real resolved_at timestamp exists on the object.
    ...(isResolved
      ? [['Resolved at', formatDate(incident.resolved_at)]]
      : []
    ),
  ]

  return (
    <div className="page">
      {/* Back link */}
      <Link to="/" style={{ fontSize: 13, color: 'var(--text-muted)',
                             display: 'inline-block', marginBottom: 16 }}>
        ← Back to live feed
      </Link>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'flex-start',
                    justifyContent: 'space-between', marginBottom: 24,
                    gap: 16, flexWrap: 'wrap' }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center',
                        gap: 10, marginBottom: 6 }}>
            <PriorityBadge priority={incident.priority} />
            <StatusBadge status={incident.status} />
          </div>
          <h1 style={{ fontSize: 20, fontWeight: 600 }}>
            {incident.component_id}
          </h1>
          <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 2 }}>
            {incident.id}
          </p>
        </div>

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {nextStates.map(s => (
            <button
              key={s}
              className="btn-primary"
              disabled={transitioning}
              onClick={() => handleTransition(s)}
            >
              {transitioning
                ? <><span className="spinner" />Working…</>
                : `Mark as ${s}`
              }
            </button>
          ))}

          {incident.status === 'RESOLVED' && !incident.rca && (
            <button
              className="btn-danger"
              onClick={() => navigate(`/incidents/${id}/rca`)}
            >
              Submit RCA & Close
            </button>
          )}

          {incident.status === 'CLOSED' && (
            <span style={{ fontSize: 13, color: 'var(--text-muted)',
                           alignSelf: 'center' }}>
              Incident closed
            </span>
          )}
        </div>
      </div>

      {transitionError && (
        <div className="error-box" style={{ marginBottom: 16 }}>
          {transitionError}
        </div>
      )}

      {/* Details grid */}
      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr',
                    gap: 16, marginBottom: 24 }}>
        <div className="card">
          <h2 style={{ fontSize: 14, fontWeight: 600,
                       marginBottom: 16 }}>Incident details</h2>
          <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr',
                       gap: '8px 20px', fontSize: 14 }}>
            {detailRows.map(([k, v]) => (
              <>
                <dt key={`k-${k}`} style={{ color: 'var(--text-muted)',
                                            fontWeight: 500, whiteSpace: 'nowrap' }}>
                  {k}
                </dt>
                <dd key={`v-${k}`}>{v}</dd>
              </>
            ))}
          </dl>
        </div>

        {/* RCA panel */}
        <div className="card">
          <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
            Root cause analysis
          </h2>
          {incident.rca ? (
            <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr',
                         gap: '8px 20px', fontSize: 14 }}>
              {[
                ['MTTR (Detected → Resolved)', incident.rca.mttr_human],
                ['Category',                   incident.rca.root_cause_category],
                ['RCA Assessment Start',        formatDate(incident.rca.start_time)],
                ['RCA Assessment End',          formatDate(incident.rca.end_time)],
                ['Submitted',                   formatDate(incident.rca.submitted_at)],
              ].map(([k, v]) => (
                <>
                  <dt key={`r-${k}`} style={{ color: 'var(--text-muted)',
                                              fontWeight: 500,
                                              whiteSpace: 'nowrap' }}>
                    {k}
                  </dt>
                  <dd key={`rv-${k}`}>{v}</dd>
                </>
              ))}
              <dt style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
                Fix applied
              </dt>
              <dd style={{ fontSize: 13 }}>{incident.rca.fix_applied}</dd>
              <dt style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
                Prevention
              </dt>
              <dd style={{ fontSize: 13 }}>{incident.rca.prevention_steps}</dd>
            </dl>
          ) : (
            <div style={{ color: 'var(--text-muted)', fontSize: 14 }}>
              {incident.status === 'RESOLVED'
                ? <>
                    RCA not yet submitted.{' '}
                    <Link to={`/incidents/${id}/rca`}>
                      Submit RCA to close this incident →
                    </Link>
                  </>
                : 'RCA will be required before this incident can be closed.'
              }
            </div>
          )}
        </div>
      </div>

      {/* Incident Relationships */}
      <IncidentRelationships incidentId={id} />

      {/* Timeline visualization */}
      {timeline && (
        <TimelineVisualization timelineData={timeline} />
      )}

      {/* Signal list */}
      <div className="card">
        <h2 style={{ fontSize: 14, fontWeight: 600, marginBottom: 16 }}>
          Raw signals
        </h2>
        <SignalList incidentId={id} />
      </div>
    </div>
  )
}