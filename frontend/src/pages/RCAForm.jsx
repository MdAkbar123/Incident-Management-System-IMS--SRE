import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { fetchIncident, submitRCA, APIError } from '../api/client'
import { PriorityBadge, StatusBadge } from '../components/Badge'

const ROOT_CAUSE_OPTIONS = [
  'INFRASTRUCTURE',
  'CODE_BUG',
  'CONFIG_CHANGE',
  'DEPENDENCY_FAILURE',
  'Unknown',
]

function calcMTTR(start, end) {
  if (!start || !end) return null
  const diff = (new Date(end) - new Date(start)) / 1000
  if (diff <= 0) return null
  const h = Math.floor(diff / 3600)
  const m = Math.floor((diff % 3600) / 60)
  const s = Math.floor(diff % 60)
  if (h > 0) return `${h}h ${String(m).padStart(2,'0')}m ${String(s).padStart(2,'0')}s`
  if (m > 0) return `${m}m ${String(s).padStart(2,'0')}s`
  return `${s}s`
}

export default function RCAForm() {
  const { id } = useParams()
  const navigate = useNavigate()

  const [incident, setIncident] = useState(null)
  const [loadError, setLoadError] = useState(null)

  const [form, setForm] = useState({
    start_time:          '',
    end_time:            '',
    root_cause_category: 'INFRASTRUCTURE',
    fix_applied:         '',
    prevention_steps:    '',
  })

  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [result, setResult] = useState(null)

  useEffect(() => {
    fetchIncident(id)
      .then(inc => {
        setIncident(inc)
        // Pre-fill start_time from incident creation
        if (inc.created_at) {
          const dt = new Date(inc.created_at)
          setForm(f => ({
            ...f,
            start_time: dt.toISOString().slice(0, 16),
          }))
        }
        // Pre-fill end_time to now
        setForm(f => ({
          ...f,
          end_time: new Date().toISOString().slice(0, 16),
        }))
      })
      .catch(e => setLoadError(e.response?.data?.detail ?? e.message))
  }, [id])

  const set = (field) => (e) =>
    setForm(f => ({ ...f, [field]: e.target.value }))

  const mttrPreview = calcMTTR(form.start_time, form.end_time)

  const handleSubmit = async (e) => {
    e.preventDefault()
    setSubmitError(null)
    setSubmitting(true)

    // Validate MTTR before sending
    if (!mttrPreview) {
      setSubmitError('End time must be after start time.')
      setSubmitting(false)
      return
    }

    try {
      const payload = {
        ...form,
        start_time: new Date(form.start_time).toISOString(),
        end_time:   new Date(form.end_time).toISOString(),
      }
      const rca = await submitRCA(id, payload)
      setResult(rca)
    } catch (e) {
      if (e instanceof APIError) {
        // Structured error with recovery hint
        const detail = e.detail ? ` — ${e.detail}` : ''
        const hint = e.recoveryHint ? `\n\n💡 ${e.recoveryHint}` : ''
        setSubmitError(`${e.message}${detail}${hint}`)
      } else if (e.response?.data?.detail) {
        // Legacy error format
        const detail = e.response.data.detail
        if (Array.isArray(detail)) {
          // Pydantic validation errors
          setSubmitError(detail.map(d => d.msg).join(' · '))
        } else {
          setSubmitError(detail)
        }
      } else {
        setSubmitError(e.message)
      }
    } finally {
      setSubmitting(false)
    }
  }

  if (loadError) return (
    <div className="page">
      <div className="error-box">{loadError}</div>
    </div>
  )

  if (!incident) return (
    <div className="page" style={{ color: 'var(--text-muted)' }}>
      <span className="spinner" /> Loading…
    </div>
  )

  // Success state
  if (result) return (
    <div className="page">
      <div className="success-box" style={{ padding: '24px', marginBottom: 24 }}>
        <div style={{ fontSize: 24, marginBottom: 8 }}>✓ Incident closed</div>
        <div style={{ fontSize: 14 }}>
          RCA submitted. MTTR:{' '}
          <strong>{result.mttr_human}</strong>
          {' '}({result.mttr_seconds.toFixed(0)} seconds)
        </div>
      </div>

      <div className="card" style={{ marginBottom: 16 }}>
        <h2 style={{ fontSize: 15, fontWeight: 600, marginBottom: 16 }}>
          RCA summary
        </h2>
        <dl style={{ display: 'grid', gridTemplateColumns: 'auto 1fr',
                     gap: '10px 24px', fontSize: 14 }}>
          {[
            ['Root cause',   result.root_cause_category],
            ['MTTR',         result.mttr_human],
            ['Fix applied',  result.fix_applied],
            ['Prevention',   result.prevention_steps],
          ].map(([k, v]) => (
            <>
              <dt key={`s-${k}`} style={{ fontWeight: 500,
                                          color: 'var(--text-muted)',
                                          whiteSpace: 'nowrap' }}>
                {k}
              </dt>
              <dd key={`sv-${k}`}>{v}</dd>
            </>
          ))}
        </dl>
      </div>

      <div style={{ display: 'flex', gap: 10 }}>
        <button className="btn-primary"
                onClick={() => navigate(`/incidents/${id}`)}>
          View incident
        </button>
        <button className="btn-secondary" onClick={() => navigate('/')}>
          Back to live feed
        </button>
      </div>
    </div>
  )

  return (
    <div className="page">
      {/* Header */}
      <div style={{ marginBottom: 24 }}>
        <button className="btn-secondary"
                style={{ fontSize: 13, marginBottom: 16 }}
                onClick={() => navigate(`/incidents/${id}`)}>
          ← Back to incident
        </button>
        <div style={{ display: 'flex', alignItems: 'center',
                      gap: 10, marginBottom: 6 }}>
          <PriorityBadge priority={incident.priority} />
          <StatusBadge status={incident.status} />
        </div>
        <h1 style={{ fontSize: 20, fontWeight: 600 }}>
          Submit RCA — {incident.component_id}
        </h1>
        <p style={{ fontSize: 13, color: 'var(--text-muted)', marginTop: 4 }}>
          All fields are required. Submitting this form will close the incident.
        </p>
      </div>

      {submitError && (
        <div className="error-box" style={{
          borderLeft: '4px solid var(--p0-bg)',
          padding: '12px 16px',
          marginBottom: 16,
          whiteSpace: 'pre-wrap',
          fontSize: 13,
          lineHeight: 1.5,
        }}>
          {submitError}
        </div>
      )}

      <form onSubmit={handleSubmit}>
        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600,
                       marginBottom: 20 }}>Timeline</h2>

          <div className="form-row two-col">
            <div className="form-group">
              <label>Incident start time</label>
              <input
                type="datetime-local"
                value={form.start_time}
                onChange={set('start_time')}
                required
              />
            </div>
            <div className="form-group">
              <label>Incident end time</label>
              <input
                type="datetime-local"
                value={form.end_time}
                onChange={set('end_time')}
                required
              />
            </div>
          </div>

          {/* Live MTTR preview */}
          <div style={{
            background: mttrPreview ? 'var(--resolved-bg)' : 'var(--bg)',
            border: `1px solid ${mttrPreview ? '#86efac' : 'var(--border)'}`,
            borderRadius: 'var(--radius)',
            padding: '12px 16px',
            fontSize: 14,
          }}>
            <span style={{ color: 'var(--text-muted)', fontWeight: 500 }}>
              MTTR preview:{' '}
            </span>
            {mttrPreview
              ? <strong style={{ color: 'var(--resolved-text)' }}>
                  {mttrPreview}
                </strong>
              : <span style={{ color: 'var(--text-muted)' }}>
                  Select valid start and end times
                </span>
            }
          </div>
        </div>

        <div className="card" style={{ marginBottom: 16 }}>
          <h2 style={{ fontSize: 14, fontWeight: 600,
                       marginBottom: 20 }}>Root cause</h2>

          <div className="form-row">
            <div className="form-group">
              <label>Root cause category</label>
              <select
                value={form.root_cause_category}
                onChange={set('root_cause_category')}
                required
              >
                {ROOT_CAUSE_OPTIONS.map(o => (
                  <option key={o} value={o}>{o}</option>
                ))}
              </select>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Fix applied <span style={{ color: 'var(--p0-text)' }}>*</span></label>
              <textarea
                value={form.fix_applied}
                onChange={set('fix_applied')}
                placeholder="Describe the fix that resolved the incident. Minimum 10 characters."
                required
                minLength={10}
                style={{ minHeight: 110 }}
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted)',
                             marginTop: 4 }}>
                {form.fix_applied.length} / 2000 chars
              </span>
            </div>
          </div>

          <div className="form-row">
            <div className="form-group">
              <label>Prevention steps <span style={{ color: 'var(--p0-text)' }}>*</span></label>
              <textarea
                value={form.prevention_steps}
                onChange={set('prevention_steps')}
                placeholder="List the steps to prevent this incident from recurring. Minimum 10 characters."
                required
                minLength={10}
                style={{ minHeight: 110 }}
              />
              <span style={{ fontSize: 12, color: 'var(--text-muted)',
                             marginTop: 4 }}>
                {form.prevention_steps.length} / 2000 chars
              </span>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', gap: 10, justifyContent: 'flex-end' }}>
          <button
            type="button"
            className="btn-secondary"
            onClick={() => navigate(`/incidents/${id}`)}
          >
            Cancel
          </button>
          <button
            type="submit"
            className="btn-danger"
            disabled={submitting || !mttrPreview}
          >
            {submitting
              ? <><span className="spinner" />Submitting…</>
              : 'Submit RCA and close incident'
            }
          </button>
        </div>
      </form>
    </div>
  )
}
