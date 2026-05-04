import React from 'react';

const W = 120;
const H = 72;
const CX = 60;
const CY = 62;  // center sits near the bottom so the top half arc is fully visible
const R = 46;
const SW = 7;   // stroke width

// Converts 0-1 score to an (x, y) point on the semicircle.
// 0 = left end, 1 = right end, 0.5 = top.
function scoreToPoint(score) {
  const angle = Math.PI * (1 - score); // π → 0 as score 0 → 1
  return {
    x: CX + R * Math.cos(angle),
    y: CY - R * Math.sin(angle),     // minus because SVG y goes down
  };
}

function gaugeColor(score) {
  if (score >= 0.72) return '#E03448';
  if (score >= 0.50) return '#F07020';
  return '#27B97C';
}

export function MpiGauge({ topic_cluster, score = 0, signal_count = 0 }) {
  const start = scoreToPoint(0);   // left  (CX-R, CY)
  const end   = scoreToPoint(1);   // right (CX+R, CY)
  const fill  = scoreToPoint(Math.min(score, 0.999)); // avoid degenerate arc at score=1
  const color = gaugeColor(score);

  // Track: full semicircle left → right through the top (sweep=1 = clockwise in SVG)
  const track = `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${R} ${R} 0 0 1 ${end.x.toFixed(2)} ${end.y.toFixed(2)}`;

  // Fill: left → fill point (same arc direction, always short arc — fill never exceeds 180°)
  const fillPath = score > 0.005
    ? `M ${start.x.toFixed(2)} ${start.y.toFixed(2)} A ${R} ${R} 0 0 1 ${fill.x.toFixed(2)} ${fill.y.toFixed(2)}`
    : null;

  return (
    <div style={s.card}>
      <div style={s.svgWrap}>
        <svg
          width={W}
          height={H}
          viewBox={`0 0 ${W} ${H}`}
          style={{ display: 'block', overflow: 'hidden' }}
        >
          {/* Background track */}
          <path d={track} fill="none" stroke="rgba(0,51,102,0.10)" strokeWidth={SW} strokeLinecap="round" />

          {/* Fill arc */}
          {fillPath && (
            <path d={fillPath} fill="none" stroke={color} strokeWidth={SW} strokeLinecap="round" />
          )}

          {/* Score */}
          <text x={CX} y={CY - 12} textAnchor="middle" dominantBaseline="auto"
            style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '18px', fontWeight: 300, fill: '#0a1628' }}>
            {score.toFixed(2)}
          </text>

          {/* Label */}
          <text x={CX} y={CY + 4} textAnchor="middle" dominantBaseline="auto"
            style={{ fontFamily: 'system-ui, sans-serif', fontSize: '8px', fill: '#64748b', letterSpacing: '1.5px' }}>
            MPI
          </text>
        </svg>
      </div>

      <div style={s.cluster}>{topic_cluster}</div>
      <div style={s.count}>{signal_count} signals</div>
    </div>
  );
}

const s = {
  card: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    backgroundColor: '#ffffff',
    borderRadius: '12px',
    padding: '14px 16px 12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    borderTop: '3px solid #c9a84c',
    minWidth: '130px',
    maxWidth: '155px',
    overflow: 'hidden',   // clips any stroke that barely escapes the SVG
  },
  svgWrap: {
    overflow: 'hidden',
    borderRadius: '4px',
    lineHeight: 0,
  },
  cluster: {
    fontFamily: 'system-ui, sans-serif',
    fontSize: '11px',
    fontWeight: 600,
    color: '#0a1628',
    textAlign: 'center',
    marginTop: '4px',
    maxWidth: '130px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  count: {
    fontFamily: 'system-ui, sans-serif',
    fontSize: '10px',
    color: '#64748b',
    marginTop: '2px',
  },
};
