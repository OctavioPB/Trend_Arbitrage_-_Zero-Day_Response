import React from 'react';

const CX = 60;
const CY = 55;
const R = 42;

function toRad(deg) {
  return (deg * Math.PI) / 180;
}

function polarToCart(angleDeg) {
  return {
    x: CX + R * Math.cos(toRad(angleDeg)),
    y: CY + R * Math.sin(toRad(angleDeg)),
  };
}

// Arc path going counterclockwise (sweep=0) from startDeg to endDeg
function arcPath(startDeg, endDeg) {
  const p1 = polarToCart(startDeg);
  const p2 = polarToCart(endDeg);
  const span = endDeg - startDeg;
  const largeArc = Math.abs(span) > 180 ? 1 : 0;
  return `M ${p1.x.toFixed(2)} ${p1.y.toFixed(2)} A ${R} ${R} 0 ${largeArc} 0 ${p2.x.toFixed(2)} ${p2.y.toFixed(2)}`;
}

function gaugeColor(score) {
  if (score >= 0.72) return '#E03448';
  if (score >= 0.5) return '#F07020';
  return '#27B97C';
}

export function MpiGauge({ topic_cluster, score = 0, signal_count = 0 }) {
  const fillDeg = -180 + score * 180;
  const color = gaugeColor(score);
  const showFill = score > 0.005;

  return (
    <div style={styles.container}>
      <svg width="120" height="75" viewBox="0 0 120 75" overflow="visible">
        {/* Background track */}
        <path
          d={arcPath(-180, 0)}
          fill="none"
          stroke="var(--primary-10)"
          strokeWidth="7"
          strokeLinecap="round"
        />
        {/* Fill arc */}
        {showFill && (
          <path
            d={arcPath(-180, fillDeg)}
            fill="none"
            stroke={color}
            strokeWidth="7"
            strokeLinecap="round"
          />
        )}
        {/* Score value */}
        <text
          x={CX}
          y={CY - 5}
          textAnchor="middle"
          dominantBaseline="auto"
          style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: '17px',
            fontWeight: 300,
            fill: 'var(--dark)',
          }}
        >
          {score.toFixed(2)}
        </text>
        {/* MPI label */}
        <text
          x={CX}
          y={CY + 11}
          textAnchor="middle"
          dominantBaseline="auto"
          style={{
            fontFamily: "'Plus Jakarta Sans', sans-serif",
            fontSize: '8px',
            fill: 'var(--mid)',
            letterSpacing: '1.5px',
          }}
        >
          MPI
        </text>
      </svg>

      <div style={styles.cluster}>{topic_cluster}</div>
      <div style={styles.count}>{signal_count} signals</div>
    </div>
  );
}

const styles = {
  container: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    padding: '16px 20px 14px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    borderTop: '3px solid var(--gold)',
    minWidth: '120px',
    maxWidth: '150px',
  },
  cluster: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    fontWeight: 600,
    color: 'var(--dark)',
    textAlign: 'center',
    marginTop: '2px',
    maxWidth: '130px',
    overflow: 'hidden',
    textOverflow: 'ellipsis',
    whiteSpace: 'nowrap',
  },
  count: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    color: 'var(--mid)',
    marginTop: '3px',
  },
};
