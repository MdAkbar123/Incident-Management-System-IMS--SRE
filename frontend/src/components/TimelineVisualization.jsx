import { useState, useEffect } from 'react'
import styles from './TimelineVisualization.module.css'

/**
 * TimelineVisualization Component
 * ================================
 * Displays a bar chart showing signal arrival pattern over time.
 * Helps visualize debounce compression (200 signals → 1 work item).
 */

export default function TimelineVisualization({ timelineData }) {
  const [chartData, setChartData] = useState(null)

  useEffect(() => {
    if (!timelineData || !timelineData.events) return

    // Group signal_received events by 100ms buckets
    const signalEvents = timelineData.events.filter(
      e => e.event_type === 'signal_received'
    )

    if (signalEvents.length === 0) {
      setChartData(null)
      return
    }

    const firstTime = new Date(signalEvents[0].timestamp).getTime()
    const bucketSize = 100 // 100ms buckets

    const buckets = {}
    signalEvents.forEach(event => {
      const ts = new Date(event.timestamp).getTime()
      const bucket = Math.floor((ts - firstTime) / bucketSize) * bucketSize
      buckets[bucket] = (buckets[bucket] || 0) + (event.data?.count || 1)
    })

    const sortedBuckets = Object.entries(buckets)
      .sort((a, b) => parseInt(a[0]) - parseInt(b[0]))
      .map(([bucket, count]) => ({
        time: Math.floor(parseInt(bucket) / 1000 * 10) / 10, // Convert to seconds
        count: count,
      }))

    const totalSignals = timelineData.total_signals || 0
    const maxCount = Math.max(...sortedBuckets.map(b => b.count), 1)

    setChartData({
      buckets: sortedBuckets,
      totalSignals,
      maxCount,
      durationMs: timelineData.duration_ms,
    })
  }, [timelineData])

  if (!chartData) {
    return (
      <div className={styles.container}>
        <p style={{ color: 'var(--text-muted)' }}>No signal timeline data</p>
      </div>
    )
  }

  const { buckets, totalSignals, maxCount, durationMs } = chartData

  return (
    <div className={styles.container}>
      <div className={styles.header}>
        <h3>Signal Timeline</h3>
        <p className={styles.subtitle}>
          Shows signal arrival pattern over {(durationMs / 1000).toFixed(2)}s
        </p>
      </div>

      {/* Stats row */}
      <div className={styles.statsRow}>
        <div className={styles.stat}>
          <span className={styles.label}>Total Signals</span>
          <span className={styles.value}>{totalSignals}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Batches</span>
          <span className={styles.value}>{buckets.length}</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Duration</span>
          <span className={styles.value}>{(durationMs / 1000).toFixed(2)}s</span>
        </div>
        <div className={styles.stat}>
          <span className={styles.label}>Peak Rate</span>
          <span className={styles.value}>{maxCount}/batch</span>
        </div>
      </div>

      {/* Bar chart */}
      <div className={styles.chartContainer}>
        <div className={styles.yAxis}>
          <div className={styles.yLabel}>{maxCount}</div>
          <div className={styles.yLabel}>{Math.floor(maxCount / 2)}</div>
          <div className={styles.yLabel}>0</div>
        </div>

        <div className={styles.chartBars}>
          {buckets.map((bucket, idx) => {
            const height = (bucket.count / maxCount) * 100
            return (
              <div key={idx} className={styles.barWrapper}>
                <div
                  className={styles.bar}
                  style={{
                    height: `${height}%`,
                    animation: `slideUp 0.3s ease-out ${idx * 20}ms both`,
                  }}
                  title={`${bucket.count} signals at ${bucket.time}s`}
                >
                  {height > 15 && (
                    <span className={styles.barLabel}>{bucket.count}</span>
                  )}
                </div>
                <div className={styles.barTime}>
                  {bucket.time.toFixed(1)}s
                </div>
              </div>
            )
          })}
        </div>
      </div>

      {/* Annotations */}
      <div className={styles.annotations}>
        <div className={styles.annotation}>
          <span className={styles.annotationLabel}>Debounce Window:</span>
          <span className={styles.annotationValue}>10s</span>
        </div>
        <div className={styles.annotation}>
          <span className={styles.annotationLabel}>Result:</span>
          <span className={styles.annotationValue}>1 work item created</span>
        </div>
        <div className={styles.annotation}>
          <span className={styles.annotationLabel}>Compression:</span>
          <span className={styles.annotationValue}>
            {totalSignals}:1 ratio
          </span>
        </div>
      </div>

      {/* Key insight */}
      <div className={styles.insight}>
        <strong>Concurrency Proof:</strong> System processed {totalSignals} concurrent
        signals in {(durationMs / 1000).toFixed(2)} seconds using async workers + Redis debounce.
      </div>

      <style>{`
        @keyframes slideUp {
          from {
            height: 0;
            opacity: 0;
          }
          to {
            height: var(--target-height);
            opacity: 1;
          }
        }
      `}</style>
    </div>
  )
}
