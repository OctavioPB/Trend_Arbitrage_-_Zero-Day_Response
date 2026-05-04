import React, { useState } from 'react';

// ── Urgency pill ──────────────────────────────────────────────────────────────

function UrgencyBadge({ level }) {
  const color =
    level === 'high'   ? { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' } :
    level === 'medium' ? { bg: '#fff7ed', text: '#ea580c', border: '#fed7aa' } :
                         { bg: '#f0fdf4', text: '#16a34a', border: '#bbf7d0' };
  return (
    <span style={{
      fontSize: '9px', fontFamily: 'var(--fb)', fontWeight: 600,
      letterSpacing: '1.5px', textTransform: 'uppercase',
      padding: '2px 7px', borderRadius: '10px',
      backgroundColor: color.bg, color: color.text,
      border: `1px solid ${color.border}`,
    }}>
      {level}
    </span>
  );
}

// ── MPI bar ───────────────────────────────────────────────────────────────────

function MpiBar({ score, threshold = 0.72 }) {
  const pct = Math.round(score * 100);
  const color = score >= 0.72 ? '#E03448' : score >= 0.50 ? '#F07020' : '#27B97C';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
      <div style={{ flex: 1, height: '6px', backgroundColor: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${pct}%`, height: '100%', backgroundColor: color, borderRadius: '3px', transition: 'width 0.6s ease' }} />
      </div>
      <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '15px', fontWeight: 300, color, minWidth: '36px', textAlign: 'right' }}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}

// ── Cluster result card ───────────────────────────────────────────────────────

function ClusterCard({ cluster }) {
  return (
    <div style={cs.clusterCard}>
      <div style={{ ...cs.clusterAccent, backgroundColor: cluster.golden_record_created ? '#E03448' : '#64748b' }} />
      <div style={{ padding: '16px' }}>
        <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '10px' }}>
          <div>
            <div style={cs.clusterName}>{cluster.name}</div>
            <div style={{ marginTop: '4px' }}>
              <UrgencyBadge level={cluster.urgency} />
            </div>
          </div>
          {cluster.golden_record_created && (
            <span style={cs.goldenBadge}>Golden Record</span>
          )}
        </div>
        <MpiBar score={cluster.mpi_score} />
        <div style={cs.clusterMeta}>
          <span>{cluster.signals_created} signals inserted</span>
        </div>
      </div>
    </div>
  );
}

// ── Log entry ─────────────────────────────────────────────────────────────────

function LogEntry({ entry }) {
  const icon = entry.type === 'success' ? '✓' : entry.type === 'error' ? '✗' : '·';
  const color = entry.type === 'success' ? '#27B97C' : entry.type === 'error' ? '#E03448' : '#64748b';
  return (
    <div style={{ display: 'flex', gap: '10px', padding: '6px 0', borderBottom: '1px solid #f1f5f9', alignItems: 'flex-start' }}>
      <span style={{ fontFamily: 'monospace', fontSize: '12px', color, flexShrink: 0, marginTop: '1px' }}>{icon}</span>
      <span style={{ fontFamily: 'monospace', fontSize: '11px', color: '#64748b', flexShrink: 0 }}>{entry.time}</span>
      <span style={{ fontFamily: 'var(--fb)', fontSize: '12px', color: '#0a1628' }}>{entry.message}</span>
    </div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function DemoPage({ authFetch }) {
  const [seedResult, setSeedResult] = useState(null);
  const [seedLoading, setSeedLoading] = useState(false);
  const [resetLoading, setResetLoading] = useState(false);
  const [resetConfirm, setResetConfirm] = useState(false);
  const [log, setLog] = useState([]);

  function addLog(type, message) {
    const time = new Date().toLocaleTimeString('en-US', { hour12: false });
    setLog(prev => [{ type, message, time, id: Date.now() + Math.random() }, ...prev].slice(0, 30));
  }

  async function handleSeed() {
    setSeedLoading(true);
    addLog('info', 'Seeding synthetic demo data…');
    try {
      const res = await authFetch('/demo/seed', { method: 'POST' });
      if (!res || !res.ok) {
        const err = res ? await res.text() : 'Network error';
        addLog('error', `Seed failed: ${err}`);
        return;
      }
      const data = await res.json();
      setSeedResult(data);
      addLog('success', `Seeded ${data.signals_total} signals across ${data.clusters.length} clusters`);
      addLog('success', `Created ${data.golden_records_total} golden records (MPI ≥ ${data.mpi_threshold})`);
      data.clusters.forEach(c => {
        const tag = c.golden_record_created ? ' → Golden Record' : '';
        addLog('info', `  ${c.name}: ${c.signals_created} signals, MPI ${c.mpi_score.toFixed(2)}${tag}`);
      });
    } catch (err) {
      addLog('error', `Seed failed: ${err.message}`);
    } finally {
      setSeedLoading(false);
    }
  }

  async function handleReset() {
    if (!resetConfirm) {
      setResetConfirm(true);
      return;
    }
    setResetConfirm(false);
    setResetLoading(true);
    addLog('info', 'Clearing database…');
    try {
      const res = await authFetch('/demo/reset', { method: 'DELETE' });
      if (!res || !res.ok) {
        const err = res ? await res.text() : 'Network error';
        addLog('error', `Reset failed: ${err}`);
        return;
      }
      const data = await res.json();
      setSeedResult(null);
      addLog('success', `Deleted ${data.signals_deleted} signals and ${data.golden_records_deleted} golden records`);
    } catch (err) {
      addLog('error', `Reset failed: ${err.message}`);
    } finally {
      setResetLoading(false);
    }
  }

  return (
    <div style={s.page}>

      {/* Page header */}
      <header style={s.header}>
        <div style={s.headerInner}>
          <div style={s.eyebrow}>
            <div style={s.eyebrowLine} />
            Demo Control
          </div>
          <h1 style={s.title}>Admin Panel</h1>
          <p style={s.subtitle}>
            Seed synthetic market signals and golden records to showcase the pipeline end-to-end.
            Reset the database to start from a clean slate.
          </p>
        </div>
      </header>

      <div style={s.body}>

        {/* ── Action cards ── */}
        <div style={s.actionRow}>

          {/* Seed card */}
          <div style={s.actionCard}>
            <div style={{ ...s.actionAccent, backgroundColor: '#27B97C' }} />
            <div style={s.actionBody}>
              <div style={s.actionIcon}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#27B97C" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
                </svg>
              </div>
              <h2 style={s.actionTitle}>Generate Demo Data</h2>
              <p style={s.actionDesc}>
                Inserts <strong>145 synthetic signals</strong> across 5 topic clusters into{' '}
                <code style={s.code}>enriched_signals</code>, runs MPI calculation, and creates{' '}
                <strong>3 golden records</strong> for clusters above the 0.72 threshold.
              </p>

              <div style={s.clusterPreview}>
                {[
                  { name: 'ai-chips',            mpi: 0.87, signals: 42, gr: true  },
                  { name: 'generative-ai-tools', mpi: 0.81, signals: 35, gr: true  },
                  { name: 'llm-regulation',      mpi: 0.74, signals: 28, gr: true  },
                  { name: 'open-source-models',  mpi: 0.68, signals: 22, gr: false },
                  { name: 'autonomous-vehicles', mpi: 0.61, signals: 18, gr: false },
                ].map(c => (
                  <div key={c.name} style={s.previewRow}>
                    <span style={s.previewDot(c.gr)} />
                    <span style={s.previewName}>{c.name}</span>
                    <span style={s.previewCount}>{c.signals} signals</span>
                    <span style={{ ...s.previewMpi, color: c.mpi >= 0.72 ? '#E03448' : '#64748b' }}>
                      {c.mpi.toFixed(2)}
                    </span>
                  </div>
                ))}
              </div>

              <button
                style={{ ...s.btn, ...s.btnGreen, ...(seedLoading ? s.btnDisabled : {}) }}
                onClick={handleSeed}
                disabled={seedLoading}
              >
                {seedLoading ? (
                  <span style={s.btnSpinner} />
                ) : (
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <line x1="12" y1="5" x2="12" y2="19" /><line x1="5" y1="12" x2="19" y2="12" />
                  </svg>
                )}
                {seedLoading ? 'Seeding…' : 'Seed Demo Data'}
              </button>
            </div>
          </div>

          {/* Reset card */}
          <div style={s.actionCard}>
            <div style={{ ...s.actionAccent, backgroundColor: '#E03448' }} />
            <div style={s.actionBody}>
              <div style={s.actionIcon}>
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#E03448" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="3 6 5 6 21 6" />
                  <path d="M19 6l-1 14H6L5 6" />
                  <path d="M10 11v6" /><path d="M14 11v6" />
                  <path d="M9 6V4h6v2" />
                </svg>
              </div>
              <h2 style={s.actionTitle}>Clear Database</h2>
              <p style={s.actionDesc}>
                Deletes all rows from <code style={s.code}>enriched_signals</code> and{' '}
                <code style={s.code}>golden_records</code>. The heat map and segment sidebar
                will go empty immediately after the next WebSocket push.
              </p>

              <div style={s.warningBox}>
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#92400e" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: '1px' }}>
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" /><line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
                <span style={s.warningText}>This action cannot be undone. All signal history and golden records will be permanently deleted.</span>
              </div>

              {resetConfirm ? (
                <div style={{ display: 'flex', gap: '10px', marginTop: '20px' }}>
                  <button
                    style={{ ...s.btn, ...s.btnRed, flex: 1, ...(resetLoading ? s.btnDisabled : {}) }}
                    onClick={handleReset}
                    disabled={resetLoading}
                  >
                    {resetLoading ? <span style={s.btnSpinner} /> : null}
                    {resetLoading ? 'Deleting…' : 'Yes, delete everything'}
                  </button>
                  <button
                    style={{ ...s.btn, ...s.btnGhost }}
                    onClick={() => setResetConfirm(false)}
                    disabled={resetLoading}
                  >
                    Cancel
                  </button>
                </div>
              ) : (
                <button
                  style={{ ...s.btn, ...s.btnRed, marginTop: '20px', ...(resetLoading ? s.btnDisabled : {}) }}
                  onClick={handleReset}
                  disabled={resetLoading}
                >
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <polyline points="3 6 5 6 21 6" />
                    <path d="M19 6l-1 14H6L5 6" />
                  </svg>
                  Clear Database
                </button>
              )}
            </div>
          </div>
        </div>

        {/* ── Cluster results ── */}
        {seedResult && (
          <div style={s.resultsSection}>
            <div style={s.sectionHead}>
              <div style={s.eyebrow}>
                <div style={s.eyebrowLine} />
                Seed Results
              </div>
              <p style={s.sectionDesc}>
                {seedResult.signals_total} signals · {seedResult.golden_records_total} golden records
                · seeded at {new Date(seedResult.seeded_at).toLocaleTimeString('en-US', { hour12: false })}
              </p>
            </div>

            <div style={s.clusterGrid}>
              {seedResult.clusters
                .slice()
                .sort((a, b) => b.mpi_score - a.mpi_score)
                .map(c => <ClusterCard key={c.name} cluster={c} />)}
            </div>

            <div style={s.note}>
              The dashboard heat map and gauges will reflect this data on the next WebSocket push
              (within 60 s). Switch back to the main view to see the updated heat map.
            </div>
          </div>
        )}

        {/* ── Activity log ── */}
        {log.length > 0 && (
          <div style={s.logSection}>
            <div style={s.sectionHead}>
              <div style={s.eyebrow}>
                <div style={s.eyebrowLine} />
                Activity Log
              </div>
            </div>
            <div style={s.logBox}>
              {log.map(e => <LogEntry key={e.id} entry={e} />)}
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  page: {
    minHeight: '100vh',
    backgroundColor: 'var(--light)',
  },
  header: {
    backgroundColor: 'var(--primary)',
    backgroundImage: `
      linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
    `,
    backgroundSize: '48px 48px',
    padding: '24px 48px',
  },
  headerInner: {
    maxWidth: '1300px',
    margin: '0 auto',
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
    color: 'var(--gold-light)',
    marginBottom: '8px',
  },
  eyebrowLine: {
    width: '24px',
    height: '1px',
    backgroundColor: 'var(--gold-light)',
    flexShrink: 0,
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '28px',
    fontWeight: 300,
    color: '#ffffff',
    margin: '0 0 8px',
    lineHeight: 1.1,
  },
  subtitle: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: 'rgba(255,255,255,0.5)',
    margin: 0,
    lineHeight: 1.6,
    maxWidth: '560px',
  },
  body: {
    maxWidth: '1300px',
    margin: '0 auto',
    padding: '40px 48px 80px',
  },
  actionRow: {
    display: 'grid',
    gridTemplateColumns: '1fr 1fr',
    gap: '24px',
  },
  actionCard: {
    backgroundColor: '#ffffff',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    overflow: 'hidden',
  },
  actionAccent: {
    height: '3px',
  },
  actionBody: {
    padding: '28px',
  },
  actionIcon: {
    width: '44px',
    height: '44px',
    borderRadius: '10px',
    backgroundColor: '#f8fafc',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: '16px',
  },
  actionTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '20px',
    fontWeight: 300,
    color: '#0a1628',
    margin: '0 0 10px',
  },
  actionDesc: {
    fontFamily: 'var(--fb)',
    fontSize: '13px',
    color: '#475569',
    lineHeight: 1.65,
    margin: '0 0 20px',
  },
  code: {
    fontFamily: 'monospace',
    fontSize: '11px',
    backgroundColor: '#f1f5f9',
    color: '#0a1628',
    padding: '1px 5px',
    borderRadius: '4px',
  },
  clusterPreview: {
    backgroundColor: '#f8fafc',
    borderRadius: '8px',
    padding: '12px 14px',
    marginBottom: '20px',
  },
  previewRow: {
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    padding: '4px 0',
  },
  previewDot: (golden) => ({
    width: '6px',
    height: '6px',
    borderRadius: '50%',
    backgroundColor: golden ? '#E03448' : '#cbd5e1',
    flexShrink: 0,
  }),
  previewName: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: '#0a1628',
    flex: 1,
  },
  previewCount: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    color: '#94a3b8',
  },
  previewMpi: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '13px',
    fontWeight: 300,
    minWidth: '30px',
    textAlign: 'right',
  },
  warningBox: {
    display: 'flex',
    alignItems: 'flex-start',
    gap: '8px',
    backgroundColor: '#fffbeb',
    border: '1px solid #fde68a',
    borderRadius: '8px',
    padding: '12px 14px',
    marginBottom: '4px',
  },
  warningText: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: '#92400e',
    lineHeight: 1.5,
  },
  btn: {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '7px',
    padding: '10px 20px',
    borderRadius: '8px',
    fontSize: '12px',
    fontFamily: 'var(--fb)',
    fontWeight: 500,
    letterSpacing: '0.5px',
    cursor: 'pointer',
    border: 'none',
    width: '100%',
    transition: 'opacity 0.15s',
  },
  btnGreen: {
    backgroundColor: '#27B97C',
    color: '#ffffff',
  },
  btnRed: {
    backgroundColor: '#E03448',
    color: '#ffffff',
  },
  btnGhost: {
    backgroundColor: '#f1f5f9',
    color: '#475569',
    border: '1px solid #e2e8f0',
  },
  btnDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  btnSpinner: {
    display: 'inline-block',
    width: '12px',
    height: '12px',
    border: '2px solid rgba(255,255,255,0.3)',
    borderTopColor: '#ffffff',
    borderRadius: '50%',
    animation: 'spin 0.7s linear infinite',
  },
  resultsSection: {
    marginTop: '40px',
  },
  sectionHead: {
    marginBottom: '16px',
  },
  sectionDesc: {
    fontFamily: 'var(--fb)',
    fontSize: '13px',
    color: '#64748b',
    margin: 0,
    lineHeight: 1.5,
  },
  clusterGrid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
    gap: '16px',
  },
  logSection: {
    marginTop: '40px',
  },
  logBox: {
    backgroundColor: '#ffffff',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    padding: '16px 20px',
    maxHeight: '280px',
    overflowY: 'auto',
  },
  note: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: '#94a3b8',
    marginTop: '16px',
    lineHeight: 1.6,
  },
};

// cluster result card styles
const cs = {
  clusterCard: {
    backgroundColor: '#ffffff',
    borderRadius: '10px',
    boxShadow: '0 1px 3px rgba(0,51,102,0.07)',
    overflow: 'hidden',
  },
  clusterAccent: {
    height: '3px',
  },
  clusterName: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    fontWeight: 600,
    color: '#0a1628',
    letterSpacing: '0.3px',
  },
  clusterMeta: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    color: '#94a3b8',
    marginTop: '6px',
  },
  goldenBadge: {
    fontSize: '8px',
    fontFamily: 'var(--fb)',
    fontWeight: 600,
    letterSpacing: '1.5px',
    textTransform: 'uppercase',
    backgroundColor: '#fef2f2',
    color: '#E03448',
    border: '1px solid #fecaca',
    padding: '2px 7px',
    borderRadius: '10px',
    flexShrink: 0,
  },
};
