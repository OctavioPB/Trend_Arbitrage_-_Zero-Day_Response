import React, { useState, useEffect } from 'react';

function formatCountdown(seconds) {
  if (seconds <= 0) return 'Expired';
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}

function mpiBadge(score) {
  if (score >= 0.72) return { bg: '#FDEAEA', text: '#7A1020', dot: '#E03448', label: 'HIGH PRESSURE' };
  if (score >= 0.5)  return { bg: '#FEF0E6', text: '#7A3800', dot: '#F07020', label: 'MODERATE' };
  return { bg: '#E0F7EF', text: '#0D5C3A', dot: '#27B97C', label: 'LOW' };
}

export function TrendCard({ record }) {
  const [ttl, setTtl] = useState(record.ttl_seconds ?? 0);

  // Reset TTL when a new record arrives; tick down every second
  useEffect(() => {
    setTtl(record.ttl_seconds ?? 0);
    const timer = setInterval(() => setTtl((t) => Math.max(0, t - 1)), 1000);
    return () => clearInterval(timer);
  }, [record.id, record.ttl_seconds]);

  const badge = mpiBadge(record.mpi_score);
  const isExpiringSoon = ttl > 0 && ttl < 900; // < 15 min

  return (
    <div style={styles.card}>
      {/* Gold top accent bar */}
      <div style={styles.accentBar} />

      <div style={styles.body}>
        {/* Eyebrow */}
        <div style={styles.eyebrow}>
          <div style={styles.eyebrowLine} />
          <span>Active Segment</span>
        </div>

        {/* Topic cluster — Fraunces italic on keyword */}
        <h3 style={styles.topic}>
          <em style={{ fontStyle: 'italic', color: 'var(--gold)' }}>
            {record.topic_cluster}
          </em>
        </h3>

        {/* MPI score badge + signal count */}
        <div style={styles.metaRow}>
          <span
            style={{
              ...styles.badge,
              backgroundColor: badge.bg,
              color: badge.text,
            }}
          >
            <span style={{ ...styles.dot, backgroundColor: badge.dot }} />
            {record.mpi_score.toFixed(3)} — {badge.label}
          </span>
        </div>
        <div style={styles.signalLine}>
          {record.signal_count} signals · {record.audience_proxy?.subreddits?.join(', ') ?? ''}
        </div>

        {/* Recommended action */}
        {record.recommended_action && (
          <div style={styles.actionBlock}>
            <p style={styles.actionText}>{record.recommended_action}</p>
          </div>
        )}

        {/* TTL countdown */}
        <div style={styles.ttlRow}>
          <span style={styles.ttlLabel}>EXPIRES IN</span>
          <span
            style={{
              ...styles.ttlValue,
              color: isExpiringSoon ? '#E03448' : 'var(--dark)',
            }}
          >
            {formatCountdown(ttl)}
          </span>
        </div>
      </div>
    </div>
  );
}

const styles = {
  card: {
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    overflow: 'hidden',
    marginBottom: '16px',
  },
  accentBar: {
    height: '3px',
    backgroundColor: 'var(--gold)',
  },
  body: {
    padding: '16px 20px 14px',
  },
  eyebrow: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '8px',
    fontSize: '9px',
    fontFamily: 'var(--fb)',
    fontWeight: 500,
    letterSpacing: '4px',
    textTransform: 'uppercase',
    color: 'var(--gold)',
    marginBottom: '6px',
  },
  eyebrowLine: {
    width: '20px',
    height: '1px',
    backgroundColor: 'var(--gold)',
    flexShrink: 0,
  },
  topic: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '18px',
    fontWeight: 400,
    color: 'var(--dark)',
    margin: '0 0 10px 0',
    lineHeight: 1.2,
  },
  metaRow: {
    marginBottom: '6px',
  },
  badge: {
    display: 'inline-flex',
    alignItems: 'center',
    gap: '6px',
    padding: '4px 10px',
    borderRadius: '20px',
    fontSize: '10px',
    fontFamily: 'var(--fb)',
    fontWeight: 500,
    letterSpacing: '0.5px',
  },
  dot: {
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    flexShrink: 0,
  },
  signalLine: {
    fontSize: '11px',
    fontFamily: 'var(--fb)',
    color: 'var(--mid)',
    marginBottom: '10px',
  },
  actionBlock: {
    borderLeft: '3px solid var(--gold)',
    paddingLeft: '10px',
    backgroundColor: 'var(--primary-10)',
    borderRadius: '0 4px 4px 0',
    padding: '8px 10px',
    marginBottom: '12px',
  },
  actionText: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: 'var(--dark)',
    lineHeight: 1.5,
    margin: 0,
  },
  ttlRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingTop: '10px',
    borderTop: '1px solid var(--primary-10)',
  },
  ttlLabel: {
    fontSize: '9px',
    fontFamily: 'var(--fb)',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: 'var(--mid)',
  },
  ttlValue: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '15px',
    fontWeight: 400,
  },
};
