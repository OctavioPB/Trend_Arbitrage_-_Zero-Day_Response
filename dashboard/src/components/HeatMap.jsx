import React, { useMemo } from 'react';

// Viridis colormap — 10 stops [R, G, B]
const VIRIDIS = [
  [68, 1, 84],
  [72, 40, 120],
  [62, 73, 137],
  [49, 104, 142],
  [38, 130, 142],
  [31, 158, 137],
  [53, 183, 121],
  [109, 205, 89],
  [180, 222, 44],
  [253, 231, 37],
];

function scoreToRgb(score) {
  const s = Math.max(0, Math.min(1, score));
  const idx = Math.min(Math.floor(s * 9), 8);
  const t = s * 9 - idx;
  const [r1, g1, b1] = VIRIDIS[idx];
  const [r2, g2, b2] = VIRIDIS[idx + 1];
  return `rgb(${Math.round(r1 + (r2 - r1) * t)},${Math.round(g1 + (g2 - g1) * t)},${Math.round(b1 + (b2 - b1) * t)})`;
}

function formatBucket(isoStr) {
  const d = new Date(isoStr);
  return `${String(d.getUTCHours()).padStart(2, '0')}:${String(d.getUTCMinutes()).padStart(2, '0')}`;
}

export function HeatMap({ cells = [], topic_clusters = [], time_buckets = [] }) {
  // Build lookup: cluster → bucket_iso → { score, signal_count }
  const lookup = useMemo(() => {
    const map = {};
    cells.forEach(({ topic_cluster, time_bucket, score, signal_count }) => {
      if (!map[topic_cluster]) map[topic_cluster] = {};
      map[topic_cluster][time_bucket] = { score, signal_count };
    });
    return map;
  }, [cells]);

  if (!topic_clusters.length || !time_buckets.length) {
    return (
      <div style={styles.emptyState}>
        <p style={{ fontFamily: 'var(--fb)', fontSize: '14px', color: 'var(--mid)', margin: 0 }}>
          No signal data in the current window.
        </p>
      </div>
    );
  }

  return (
    <div>
      <div style={{ overflowX: 'auto' }}>
        <table style={styles.table}>
          <thead>
            <tr>
              <th style={styles.cornerCell}>TOPIC CLUSTER</th>
              {time_buckets.map((tb) => (
                <th key={tb} style={styles.headerCell}>{formatBucket(tb)}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {topic_clusters.map((cluster) => (
              <tr key={cluster}>
                <td style={styles.rowLabel}>{cluster}</td>
                {time_buckets.map((tb) => {
                  const cell = lookup[cluster]?.[tb];
                  return (
                    <td
                      key={tb}
                      title={
                        cell
                          ? `${cluster} · ${formatBucket(tb)} · score ${cell.score.toFixed(3)} · ${cell.signal_count} signals`
                          : 'No data'
                      }
                      style={{
                        ...styles.cell,
                        backgroundColor: cell ? scoreToRgb(cell.score) : '#E8EDF2',
                        opacity: cell ? 1 : 0.35,
                      }}
                    >
                      {cell && cell.signal_count > 0 && (
                        <span style={styles.cellCount}>{cell.signal_count}</span>
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Colormap legend */}
      <div style={styles.legend}>
        <span style={styles.legendLabel}>Low</span>
        <div style={styles.legendBar}>
          {Array.from({ length: 24 }, (_, i) => (
            <div
              key={i}
              style={{ flex: 1, height: '100%', backgroundColor: scoreToRgb(i / 23) }}
            />
          ))}
        </div>
        <span style={styles.legendLabel}>High MPI</span>
      </div>
    </div>
  );
}

const styles = {
  emptyState: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: '160px',
    backgroundColor: 'var(--light)',
    borderRadius: '8px',
    border: '1px dashed var(--primary-30)',
  },
  table: {
    borderCollapse: 'separate',
    borderSpacing: '2px',
    width: '100%',
    fontFamily: 'var(--fb)',
  },
  cornerCell: {
    padding: '6px 12px 6px 0',
    fontSize: '9px',
    fontWeight: 600,
    letterSpacing: '2px',
    textTransform: 'uppercase',
    color: 'var(--mid)',
    textAlign: 'left',
    background: 'transparent',
    borderBottom: '1px solid var(--primary-10)',
    minWidth: '160px',
    whiteSpace: 'nowrap',
  },
  headerCell: {
    padding: '4px 2px',
    fontSize: '9px',
    fontWeight: 500,
    color: 'var(--mid)',
    textAlign: 'center',
    letterSpacing: '0.5px',
    minWidth: '40px',
    whiteSpace: 'nowrap',
  },
  rowLabel: {
    padding: '3px 12px 3px 0',
    fontSize: '11px',
    fontWeight: 500,
    color: 'var(--dark)',
    fontFamily: 'var(--fb)',
    whiteSpace: 'nowrap',
    borderRight: '1px solid var(--primary-10)',
  },
  cell: {
    width: '40px',
    height: '28px',
    borderRadius: '3px',
    cursor: 'default',
    textAlign: 'center',
    verticalAlign: 'middle',
  },
  cellCount: {
    fontSize: '8px',
    color: 'rgba(255,255,255,0.9)',
    fontWeight: 700,
    fontFamily: 'var(--fb)',
    textShadow: '0 1px 2px rgba(0,0,0,0.5)',
    pointerEvents: 'none',
  },
  legend: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
    marginTop: '14px',
  },
  legendBar: {
    display: 'flex',
    width: '140px',
    height: '8px',
    borderRadius: '4px',
    overflow: 'hidden',
    flexShrink: 0,
  },
  legendLabel: {
    fontSize: '9px',
    fontFamily: 'var(--fb)',
    color: 'var(--mid)',
    letterSpacing: '1.5px',
    textTransform: 'uppercase',
    whiteSpace: 'nowrap',
  },
};
