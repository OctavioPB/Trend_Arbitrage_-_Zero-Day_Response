import React, { useState, useEffect, useCallback } from 'react';

const _REFRESH_MS = 120_000; // 2 min

function HitRateBar({ rate }) {
  const pct = Math.round(rate * 100);
  const color = pct >= 70 ? '#27B97C' : pct >= 50 ? '#F07020' : '#E03448';
  return (
    <div style={s.barWrap}>
      <div style={{ ...s.barFill, width: `${pct}%`, backgroundColor: color }} />
    </div>
  );
}

export function PerformancePanel({ authFetch }) {
  const [data, setData] = useState(null);
  const [applying, setApplying] = useState(null); // proposal id being applied
  const [error, setError] = useState(null);

  const load = useCallback(async () => {
    try {
      const res = await authFetch('/performance/summary');
      if (res && res.ok) {
        setData(await res.json());
        setError(null);
      }
    } catch (err) {
      setError('Failed to load performance data');
    }
  }, [authFetch]);

  useEffect(() => {
    load();
    const id = setInterval(load, _REFRESH_MS);
    return () => clearInterval(id);
  }, [load]);

  async function handleApply(proposalId) {
    setApplying(proposalId);
    try {
      const res = await authFetch(`/performance/apply-proposal/${proposalId}`, {
        method: 'POST',
      });
      if (res && res.ok) {
        await load();
      }
    } catch (err) {
      setError('Failed to apply proposal');
    } finally {
      setApplying(null);
    }
  }

  return (
    <div style={s.panel}>
      {/* ── Header ── */}
      <div style={s.sectionHead}>
        <div style={s.eyebrow}>
          <div style={s.eyebrowLine} />
          Performance Feedback
        </div>
        <p style={s.sectionDesc}>Golden Record outcome metrics — last 30 days.</p>
      </div>

      {error && (
        <p style={s.errorText}>{error}</p>
      )}

      {!data && !error && (
        <p style={s.emptyText}>Loading…</p>
      )}

      {data && (
        <>
          {/* ── Hit Rate ── */}
          <div style={s.card}>
            <div style={s.accentBar} />
            <div style={s.cardBody}>
              <div style={s.eyebrow}>
                <div style={s.eyebrowLine} />
                Golden Record Hit Rate
              </div>
              <div style={s.hitRateRow}>
                <span style={s.hitRateValue}>
                  {Math.round(data.hit_rate * 100)}
                  <span style={s.hitRateUnit}>%</span>
                </span>
                <span style={s.hitRateSub}>
                  {data.total_hits} / {data.total_measured} measured
                </span>
              </div>
              <HitRateBar rate={data.hit_rate} />
              <p style={s.hintText}>
                Positive outcome = CTR ≥ 1.5% in 24 h after audience sync.
              </p>
            </div>
          </div>

          {/* ── Top Clusters ── */}
          {data.avg_ctr_by_cluster.length > 0 && (
            <div style={{ ...s.card, marginTop: '12px' }}>
              <div style={s.accentBar} />
              <div style={s.cardBody}>
                <div style={s.eyebrow}>
                  <div style={s.eyebrowLine} />
                  Top Clusters by CTR
                </div>
                {data.avg_ctr_by_cluster.slice(0, 4).map((c) => (
                  <div key={c.topic_cluster} style={s.clusterRow}>
                    <span style={s.clusterName}>{c.topic_cluster}</span>
                    <span style={s.clusterCtr}>
                      {(c.avg_ctr * 100).toFixed(2)}%
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* ── Calibration Proposals ── */}
          {data.pending_proposals.length > 0 && (
            <div style={{ ...s.card, marginTop: '12px' }}>
              <div style={{ ...s.accentBar, backgroundColor: '#F07020' }} />
              <div style={s.cardBody}>
                <div style={{ ...s.eyebrow, color: '#F07020' }}>
                  <div style={{ ...s.eyebrowLine, backgroundColor: '#F07020' }} />
                  Pending Calibration
                </div>
                {data.pending_proposals.map((p) => (
                  <div key={p.id} style={s.proposalBlock}>
                    <div style={s.proposalRow}>
                      <span style={s.proposalLabel}>Suggested threshold</span>
                      <span style={s.proposalValue}>
                        {p.proposed_mpi_threshold.toFixed(3)}
                      </span>
                    </div>
                    <div style={s.proposalRow}>
                      <span style={s.proposalLabel}>Precision / Recall</span>
                      <span style={s.proposalValue}>
                        {Math.round(p.precision * 100)}% / {Math.round(p.recall * 100)}%
                      </span>
                    </div>
                    <div style={s.proposalRow}>
                      <span style={s.proposalLabel}>Samples</span>
                      <span style={s.proposalValue}>{p.sample_count}</span>
                    </div>
                    <button
                      style={{
                        ...s.applyBtn,
                        opacity: applying === p.id ? 0.6 : 1,
                        cursor: applying === p.id ? 'not-allowed' : 'pointer',
                      }}
                      onClick={() => handleApply(p.id)}
                      disabled={applying === p.id}
                    >
                      {applying === p.id ? 'Applying…' : 'Apply Weights'}
                    </button>
                    <p style={s.hintText}>
                      Applies source weights immediately. MPI threshold requires env var update.
                    </p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.total_measured === 0 && (
            <p style={s.emptyText}>
              No performance data yet.<br />
              Metrics appear after audiences are synced and the weekly calibration DAG runs.
            </p>
          )}
        </>
      )}
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  panel: {
    marginTop: '32px',
  },
  sectionHead: {
    marginBottom: '16px',
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
    marginBottom: '4px',
  },
  eyebrowLine: {
    width: '20px',
    height: '1px',
    backgroundColor: 'var(--gold)',
    flexShrink: 0,
  },
  sectionDesc: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: 'var(--mid)',
    margin: '2px 0 0',
    lineHeight: 1.5,
  },
  card: {
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    overflow: 'hidden',
  },
  accentBar: {
    height: '3px',
    backgroundColor: 'var(--gold)',
  },
  cardBody: {
    padding: '14px 16px 12px',
  },
  hitRateRow: {
    display: 'flex',
    alignItems: 'baseline',
    gap: '10px',
    margin: '8px 0 6px',
  },
  hitRateValue: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '36px',
    fontWeight: 300,
    color: 'var(--dark)',
    lineHeight: 1,
  },
  hitRateUnit: {
    fontSize: '18px',
    fontWeight: 300,
  },
  hitRateSub: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: 'var(--mid)',
  },
  barWrap: {
    height: '4px',
    backgroundColor: 'var(--primary-10)',
    borderRadius: '2px',
    overflow: 'hidden',
    margin: '8px 0 6px',
  },
  barFill: {
    height: '100%',
    borderRadius: '2px',
    transition: 'width 0.6s ease',
  },
  clusterRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    padding: '5px 0',
    borderBottom: '1px solid var(--primary-10)',
  },
  clusterName: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: 'var(--dark)',
    maxWidth: '70%',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  clusterCtr: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '14px',
    fontWeight: 400,
    color: 'var(--dark)',
  },
  proposalBlock: {
    marginTop: '8px',
  },
  proposalRow: {
    display: 'flex',
    justifyContent: 'space-between',
    padding: '4px 0',
  },
  proposalLabel: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    color: 'var(--mid)',
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
  },
  proposalValue: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '13px',
    fontWeight: 400,
    color: 'var(--dark)',
  },
  applyBtn: {
    width: '100%',
    marginTop: '10px',
    padding: '8px',
    backgroundColor: '#003366',
    color: '#fff',
    border: 'none',
    borderRadius: '6px',
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    letterSpacing: '2px',
    textTransform: 'uppercase',
    cursor: 'pointer',
  },
  hintText: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    color: 'var(--mid)',
    margin: '6px 0 0',
    lineHeight: 1.5,
  },
  emptyText: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: 'var(--mid)',
    textAlign: 'center',
    lineHeight: 1.7,
    margin: '8px 0 0',
  },
  errorText: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: '#E03448',
    margin: '4px 0',
  },
};
