import { useState, useEffect } from 'react'
import styles from './IncidentRelationships.module.css'
import { Link } from 'react-router-dom'

/**
 * IncidentRelationships Component
 * ================================
 * Displays root causes and cascaded incidents for a given incident.
 * Shows detection method and confidence scores.
 */

export default function IncidentRelationships({ incidentId }) {
  const [relationships, setRelationships] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!incidentId) return

    setLoading(true)
    setError(null)

    fetch(`/api/incidents/${incidentId}/related`)
      .then(r => r.json())
      .then(setRelationships)
      .catch(e => {
        console.error('Failed to fetch relationships:', e)
        setError(e.message)
      })
      .finally(() => setLoading(false))
  }, [incidentId])

  if (loading) {
    return (
      <div className={styles.container}>
        <span className="spinner" /> Loading relationships...
      </div>
    )
  }

  if (error) {
    return (
      <div className={styles.container}>
        <p style={{ color: 'var(--text-muted)' }}>
          Could not load relationships
        </p>
      </div>
    )
  }

  if (
    !relationships ||
    (relationships.root_causes.length === 0 &&
      relationships.cascaded_incidents.length === 0)
  ) {
    return (
      <div className={styles.container}>
        <p style={{ color: 'var(--text-muted)' }}>
          No related incidents detected in the past 30 seconds
        </p>
      </div>
    )
  }

  return (
    <div className={styles.container}>
      <h3 className={styles.title}>Incident Relationships</h3>

      {/* Root Causes Section */}
      {relationships.root_causes.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>
            🔴 Root Cause{relationships.root_causes.length > 1 ? 's' : ''}
          </h4>
          <p className={styles.sectionDescription}>
            Incident{relationships.root_causes.length > 1 ? 's' : ''} that likely triggered this one
          </p>
          <div className={styles.relationshipsList}>
            {relationships.root_causes.map(rel => (
              <RelationshipCard key={rel.id} relationship={rel} />
            ))}
          </div>
        </div>
      )}

      {/* Cascaded Incidents Section */}
      {relationships.cascaded_incidents.length > 0 && (
        <div className={styles.section}>
          <h4 className={styles.sectionTitle}>
            ➡️ Cascaded Impact
          </h4>
          <p className={styles.sectionDescription}>
            Incident{relationships.cascaded_incidents.length > 1 ? 's' : ''} triggered by this one
          </p>
          <div className={styles.relationshipsList}>
            {relationships.cascaded_incidents.map(rel => (
              <RelationshipCard key={rel.id} relationship={rel} />
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

function RelationshipCard({ relationship }) {
  const confidence = (relationship.confidence * 100).toFixed(0)
  const otherIncidentId =
    relationship.relationship_type === 'ROOT_CAUSE'
      ? relationship.source_incident_id
      : relationship.target_incident_id

  return (
    <Link to={`/incidents/${otherIncidentId}`} className={styles.card}>
      <div className={styles.cardContent}>
        <div className={styles.cardHeader}>
          <span className={styles.incidentId}>{otherIncidentId}</span>
          <ConfidenceBadge confidence={relationship.confidence} />
        </div>

        <p className={styles.reason}>{relationship.reason}</p>

        <div className={styles.meta}>
          <span className={styles.method}>
            {getMethodLabel(relationship.detection_method)}
          </span>
          <span className={styles.time}>
            {formatRelativeTime(relationship.created_at)}
          </span>
        </div>
      </div>
      <div className={styles.arrow}>→</div>
    </Link>
  )
}

function ConfidenceBadge({ confidence }) {
  const percentage = (confidence * 100).toFixed(0)
  let color = 'low'
  if (confidence >= 0.8) color = 'high'
  else if (confidence >= 0.6) color = 'medium'

  return (
    <span className={`${styles.confidence} ${styles[`confidence-${color}`]}`}>
      {percentage}%
    </span>
  )
}

function getMethodLabel(method) {
  const labels = {
    dependency_graph: '🔗 Dependency',
    temporal: '⏱️ Temporal',
    semantic: '📊 Pattern',
  }
  return labels[method] || method
}

function formatRelativeTime(isoDate) {
  const date = new Date(isoDate)
  const now = new Date()
  const diff = Math.floor((now - date) / 1000)

  if (diff < 60) return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}
