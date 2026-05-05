import React, { useState } from 'react';

// ─────────────────────────────────────────────────────────────────────────────
// Business View — SVG Diagrams
// ─────────────────────────────────────────────────────────────────────────────

function TrendCurveDiagram() {
  const W = 660, H = 270;
  const xDetect = 195, xPeak = 345, xCompete = 445;
  const yDetect = 210, yPeak = 66, yCompete = 138, BASE = 242;
  const curve = `M 40,232 C 100,232 160,220 ${xDetect},${yDetect} C 225,202 245,185 270,162 C 290,142 310,108 332,84 C 340,72 342,64 ${xPeak},${yPeak} C 350,68 356,68 365,74 C 380,84 405,110 ${xCompete},${yCompete} C 465,156 500,182 545,206 C 558,213 566,218 580,222`;
  const windowFill = `M ${xDetect},${yDetect} C 225,202 245,185 270,162 C 290,142 310,108 332,84 C 340,72 342,64 ${xPeak},${yPeak} L ${xPeak},${BASE} L ${xDetect},${BASE} Z`;
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: W, display: 'block' }}>
      <defs>
        <linearGradient id="wGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="#C8982A" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#C8982A" stopOpacity="0.04" />
        </linearGradient>
      </defs>
      {[80, 130, 180, BASE].map(y => <line key={y} x1={36} y1={y} x2={590} y2={y} stroke="#f1f5f9" strokeWidth="1" />)}
      <line x1={36} y1={BASE} x2={590} y2={BASE} stroke="#e2e8f0" strokeWidth="1.5" />
      <path d={windowFill} fill="url(#wGrad)" />
      <line x1={xDetect} y1={58} x2={xDetect} y2={BASE} stroke="#003366" strokeWidth="1.5" strokeDasharray="5,4" />
      <line x1={xPeak}   y1={58} x2={xPeak}   y2={BASE} stroke="#C8982A" strokeWidth="1.5" strokeDasharray="5,4" />
      <line x1={xCompete} y1={118} x2={xCompete} y2={BASE} stroke="#94a3b8" strokeWidth="1.5" strokeDasharray="4,4" />
      <path d={curve} fill="none" stroke="#003366" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx={xDetect}  cy={yDetect}  r={6} fill="#003366" stroke="#fff" strokeWidth="2.5" />
      <circle cx={xPeak}    cy={yPeak}    r={7} fill="#C8982A" stroke="#fff" strokeWidth="2.5" />
      <circle cx={xCompete} cy={yCompete} r={6} fill="#94a3b8" stroke="#fff" strokeWidth="2.5" />
      <rect x={20} y={20} width={130} height={34} rx={5} fill="#003366" />
      <text x={85} y={32} textAnchor="middle" fill="#E8C46A" style={{ fontSize: '8px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>SYSTEM DETECTS</text>
      <text x={85} y={46} textAnchor="middle" fill="rgba(255,255,255,0.75)" style={{ fontSize: '9px', fontFamily: 'system-ui' }}>Early rise — &lt; 10 minutes</text>
      <line x1={150} y1={37} x2={xDetect - 8} y2={yDetect - 4} stroke="#003366" strokeWidth="1" strokeDasharray="3,3" />
      <rect x={xPeak - 55} y={20} width={110} height={34} rx={5} fill="#C8982A" />
      <text x={xPeak} y={32} textAnchor="middle" fill="#fff" style={{ fontSize: '8px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>TREND PEAK</text>
      <text x={xPeak} y={46} textAnchor="middle" fill="rgba(255,255,255,0.9)" style={{ fontSize: '9px', fontFamily: 'system-ui' }}>Highest MPI score</text>
      <line x1={xPeak} y1={54} x2={xPeak} y2={yPeak - 10} stroke="#C8982A" strokeWidth="1" />
      <rect x={xCompete - 2} y={100} width={130} height={34} rx={5} fill="#f1f5f9" stroke="#e2e8f0" />
      <text x={xCompete + 63} y={112} textAnchor="middle" fill="#64748b" style={{ fontSize: '8px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>COMPETITORS REACT</text>
      <text x={xCompete + 63} y={126} textAnchor="middle" fill="#94a3b8" style={{ fontSize: '9px', fontFamily: 'system-ui' }}>Trend already declining</text>
      <text x={(xDetect + xPeak) / 2} y={BASE - 14} textAnchor="middle" fill="#C8982A" style={{ fontSize: '9px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '2px' }}>◀── ACTIONABLE WINDOW ──▶</text>
      <text x={(xDetect + xPeak) / 2} y={BASE - 2} textAnchor="middle" fill="#C8982A" style={{ fontSize: '8.5px', fontFamily: 'system-ui' }}>15–60 min ahead of the market</text>
      <text x={14} y={H / 2} textAnchor="middle" fill="#94a3b8" style={{ fontSize: '8.5px', fontFamily: 'system-ui', letterSpacing: '1px' }} transform={`rotate(-90,14,${H / 2})`}>SIGNAL INTENSITY</text>
      <text x={590} y={BASE + 14} fill="#94a3b8" style={{ fontSize: '8.5px', fontFamily: 'system-ui', letterSpacing: '1px' }}>TIME →</text>
    </svg>
  );
}

function BeforeAfterDiagram() {
  const rows = [
    { label: 'WITHOUT', labelColor: '#64748b', labelBg: '#f1f5f9',
      steps: [{ text: 'Trend\nEmerges', time: null }, { text: 'Weekly\nReport', time: '24–48 h' }, { text: 'Team\nMeeting', time: '+ 2 days' }, { text: 'Campaign\nBrief', time: '+ 3 days' }, { text: 'Launch\n(too late)', time: '+ days', late: true }] },
    { label: 'WITH THIS\nSYSTEM', labelColor: '#E8C46A', labelBg: '#003366',
      steps: [{ text: 'Trend\nEmerges', time: null }, { text: 'AI\nClassifies', time: '< 5 min' }, { text: 'MPI\nScored', time: '< 5 min' }, { text: 'Audience\nReady', time: 'auto' }, { text: 'Launch\n(first)', time: '< 10 min', first: true }] },
  ];
  const BW = 96, BH = 56, GAP = 32, LABEL_W = 80, PAD = 14, ROW_H = BH + 20;
  const stepStart = LABEL_W + PAD * 2;
  const totalH = rows.length * ROW_H + PAD * 2 + 30;
  return (
    <svg viewBox={`0 0 680 ${totalH}`} style={{ width: '100%', maxWidth: 680, display: 'block' }}>
      {rows.map((row, ri) => {
        const rowY = PAD + ri * (ROW_H + 24);
        return (
          <g key={ri}>
            <rect x={0} y={rowY} width={LABEL_W} height={BH} rx={8} fill={row.labelBg} />
            {row.label.split('\n').map((line, li) => <text key={li} x={LABEL_W / 2} y={rowY + 20 + li * 16} textAnchor="middle" fill={row.labelColor} style={{ fontSize: '9px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1px' }}>{line}</text>)}
            {row.steps.map((step, si) => {
              const bx = stepStart + si * (BW + GAP);
              const isLast = si === row.steps.length - 1;
              const fillColor = step.first ? '#003366' : step.late ? '#f1f5f9' : ri === 1 ? '#1A4D80' : '#f8fafc';
              const textColor = step.first ? '#E8C46A' : step.late ? '#94a3b8' : ri === 1 ? '#ffffff' : '#475569';
              const borderColor = step.first ? '#C8982A' : step.late ? '#e2e8f0' : ri === 1 ? '#C8982A' : '#e2e8f0';
              return (
                <g key={si}>
                  <rect x={bx} y={rowY} width={BW} height={BH} rx={7} fill={fillColor} stroke={borderColor} strokeWidth={step.first ? 2 : 1.5} />
                  {step.text.split('\n').map((line, li) => <text key={li} x={bx + BW / 2} y={rowY + 20 + li * 16} textAnchor="middle" fill={textColor} style={{ fontSize: '11px', fontWeight: step.first ? 700 : 500, fontFamily: 'system-ui' }}>{line}</text>)}
                  {!isLast && (
                    <>
                      <line x1={bx + BW + 2} y1={rowY + BH / 2} x2={bx + BW + GAP - 8} y2={rowY + BH / 2} stroke={ri === 1 ? '#C8982A' : '#cbd5e1'} strokeWidth="1.5" />
                      <polygon points={`${bx + BW + GAP - 8},${rowY + BH / 2 - 5} ${bx + BW + GAP - 8},${rowY + BH / 2 + 5} ${bx + BW + GAP},${rowY + BH / 2}`} fill={ri === 1 ? '#C8982A' : '#cbd5e1'} />
                      {row.steps[si + 1].time && <text x={bx + BW + GAP / 2} y={rowY - 6} textAnchor="middle" fill={ri === 1 ? '#C8982A' : '#94a3b8'} style={{ fontSize: '9px', fontFamily: 'monospace', fontWeight: ri === 1 ? 700 : 400 }}>{row.steps[si + 1].time}</text>}
                    </>
                  )}
                </g>
              );
            })}
          </g>
        );
      })}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Engineering View — SVG Diagrams
// ─────────────────────────────────────────────────────────────────────────────

function ArchitectureDiagram() {
  const W = 780, H = 230;
  const BASE_Y = 14, ZONE_H = H - 28, MID_Y = BASE_Y + ZONE_H / 2;
  const zones = [
    { label: 'INGESTION',    x: 8,   w: 110, lines: ['Reddit · Twitter/X', 'Web Scrapers', 'RSS Feeds'], dark: true },
    { label: 'KAFKA',        x: 134, w: 86,  lines: ['Apache Kafka', 'raw_signals', 'ordered log'], dark: false },
    { label: 'SEMANTIC ETL', x: 236, w: 116, lines: ['Apache Airflow', 'Claude AI (sonnet)', 'DAG: 5-min cycle'], dark: false },
    { label: 'STORAGE',      x: 368, w: 114, lines: ['PostgreSQL', 'enriched_signals', 'golden_records', 'Redis cache'], dark: true },
    { label: 'API',          x: 498, w: 86,  lines: ['FastAPI', 'REST + WebSocket', 'JWT · API keys'], dark: false },
    { label: 'DASHBOARD',    x: 600, w: 172, lines: ['React + Vite', 'Heat Map · Gauges', 'WS push every 60 s'], dark: true },
  ];
  const arrowLabels = ['JSON events', 'raw_signals', 'enriched_signals', 'SQL queries', 'REST + WS'];
  return (
    <svg viewBox={`0 0 ${W} ${H}`} style={{ width: '100%', maxWidth: W, display: 'block' }}>
      {zones.map((zone, i) => {
        const fill = zone.dark ? '#003366' : '#1A4D80';
        const rx = zone.x + zone.w;
        const nx = i < zones.length - 1 ? zones[i + 1].x : null;
        return (
          <g key={i}>
            <rect x={zone.x} y={BASE_Y} width={zone.w} height={ZONE_H} rx={8} fill={fill} stroke="#C8982A" strokeWidth="1.5" />
            <text x={zone.x + zone.w / 2} y={BASE_Y + 18} textAnchor="middle" fill="#E8C46A" style={{ fontSize: '8px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>{zone.label}</text>
            <line x1={zone.x + 8} y1={BASE_Y + 26} x2={zone.x + zone.w - 8} y2={BASE_Y + 26} stroke="rgba(201,168,76,0.3)" strokeWidth="1" />
            {zone.lines.map((line, li) => (
              <text key={li} x={zone.x + zone.w / 2} y={BASE_Y + 46 + li * 22} textAnchor="middle"
                fill={li === 0 ? '#ffffff' : 'rgba(255,255,255,0.55)'}
                style={{ fontSize: li === 0 ? '11.5px' : '9.5px', fontWeight: li === 0 ? 600 : 400, fontFamily: 'system-ui' }}>
                {line}
              </text>
            ))}
            {nx && (
              <>
                <line x1={rx + 2} y1={MID_Y} x2={nx - 9} y2={MID_Y} stroke="#C8982A" strokeWidth="1.5" />
                <polygon points={`${nx - 9},${MID_Y - 5} ${nx - 9},${MID_Y + 5} ${nx - 1},${MID_Y}`} fill="#C8982A" />
                <text x={(rx + nx) / 2} y={MID_Y - 9} textAnchor="middle" fill="#C8982A" style={{ fontSize: '7.5px', fontFamily: 'monospace' }}>{arrowLabels[i]}</text>
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

function MpiFormulaDiagram() {
  const W = 540;
  const components = [
    { label: 'Volume Score',    weight: '× 0.40', barW: 0.82, note: 'signals_in_window ÷ baseline_avg' },
    { label: 'Velocity Score',  weight: '× 0.35', barW: 0.68, note: '(last 15 min ÷ prev 15 min) − 1, normalised 0–1' },
    { label: 'Sentiment Score', weight: '× 0.25', barW: 0.91, note: 'proportion of positive signals in rolling window' },
  ];
  const ROW = 56, PAD = 16, LABEL_W = 140, WEIGHT_W = 52, BAR_X = LABEL_W + 12, BAR_AREA = W - BAR_X - WEIGHT_W - PAD * 2 - 12, totalH = PAD + components.length * ROW + 64;
  return (
    <svg viewBox={`0 0 ${W} ${totalH}`} style={{ width: '100%', maxWidth: 540, display: 'block' }}>
      <text x={PAD} y={PAD + 14} fill="#0a1628" style={{ fontSize: '11px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1px' }}>MPI SCORE  =  Weighted Sum  (0.0 – 1.0)</text>
      {components.map((c, i) => {
        const y = PAD + 28 + i * ROW;
        return (
          <g key={i}>
            <rect x={PAD} y={y} width={W - PAD * 2} height={ROW - 6} rx={6} fill={i % 2 === 0 ? '#f8fafc' : '#f1f5f9'} />
            <text x={PAD + 10} y={y + 22} fill="#0a1628" style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'system-ui' }}>{c.label}</text>
            <text x={PAD + 10} y={y + 38} fill="#94a3b8" style={{ fontSize: '9.5px', fontFamily: 'system-ui' }}>{c.note}</text>
            <rect x={BAR_X + PAD} y={y + 18} width={BAR_AREA} height={8} rx={4} fill="#e2e8f0" />
            <rect x={BAR_X + PAD} y={y + 18} width={BAR_AREA * c.barW} height={8} rx={4} fill="#C8982A" />
            <text x={W - PAD - WEIGHT_W + 4} y={y + 27} fill="#003366" style={{ fontSize: '12px', fontWeight: 700, fontFamily: 'monospace' }}>{c.weight}</text>
          </g>
        );
      })}
      <line x1={PAD} y1={totalH - 30} x2={W - PAD} y2={totalH - 30} stroke="#e2e8f0" strokeWidth="1" />
      <text x={PAD} y={totalH - 10} fill="#003366" style={{ fontSize: '11.5px', fontFamily: 'system-ui' }}>When MPI ≥ 0.72 →</text>
      <text x={PAD + 118} y={totalH - 10} fill="#E03448" style={{ fontSize: '11.5px', fontWeight: 700, fontFamily: 'system-ui' }}>Golden Record triggered — audience segment ready for activation</text>
    </svg>
  );
}

function DataSchemaDiagram() {
  const W = 640, ROW_H = 22, HDR_H = 36;
  const t1Cols = [
    { name: 'event_id',        type: 'UUID',           pk: true },
    { name: 'source',          type: 'TEXT' },
    { name: 'collected_at',    type: 'TIMESTAMPTZ' },
    { name: 'category',        type: "TEXT  'opportunity' | 'threat' | 'noise'" },
    { name: 'confidence',      type: 'NUMERIC(4,3)' },
    { name: 'topic_tags',      type: 'TEXT[]',         hi: true },
    { name: 'sentiment',       type: 'TEXT' },
    { name: 'urgency',         type: 'TEXT' },
    { name: 'engagement_score',type: 'NUMERIC' },
    { name: 'raw_text',        type: 'TEXT' },
  ];
  const t2Cols = [
    { name: 'id',                type: 'UUID',           pk: true },
    { name: 'topic_cluster',     type: 'TEXT',           hi: true },
    { name: 'mpi_score',         type: 'NUMERIC(4,3)' },
    { name: 'signal_count',      type: 'INT' },
    { name: 'audience_proxy',    type: 'JSONB' },
    { name: 'recommended_action',type: 'TEXT' },
    { name: 'expires_at',        type: 'TIMESTAMPTZ' },
  ];
  const T1X = 10, T1W = 295, T2X = 335, T2W = 295;
  const t1H = HDR_H + t1Cols.length * ROW_H;
  const t2H = HDR_H + t2Cols.length * ROW_H;
  const totalH = Math.max(t1H, t2H) + 40;

  function Table({ x, w, name, cols, ht }) {
    return (
      <g>
        {/* Header */}
        <rect x={x} y={10} width={w} height={HDR_H} rx={6} fill="#003366" />
        <text x={x + w / 2} y={10 + 15} textAnchor="middle" fill="#E8C46A" style={{ fontSize: '9px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>TABLE</text>
        <text x={x + w / 2} y={10 + 28} textAnchor="middle" fill="#ffffff" style={{ fontSize: '12.5px', fontWeight: 600, fontFamily: 'monospace' }}>{name}</text>
        {/* Body */}
        <rect x={x} y={10 + HDR_H} width={w} height={ht - HDR_H} rx={0} fill="#f8fafc" stroke="#e2e8f0" strokeWidth="1" />
        {/* Bottom corners */}
        <rect x={x} y={10 + ht - 6} width={w} height={6} rx={0} fill="#f8fafc" />
        <rect x={x} y={10 + ht - 8} width={w} height={8} rx={6} fill="#f8fafc" stroke="#e2e8f0" strokeWidth="1" />
        {cols.map((col, ci) => {
          const cy = 10 + HDR_H + ci * ROW_H;
          const isEven = ci % 2 === 0;
          return (
            <g key={ci}>
              <rect x={x} y={cy} width={w} height={ROW_H} fill={col.hi ? '#fffbeb' : isEven ? '#f8fafc' : '#f1f5f9'} />
              {col.hi && <rect x={x} y={cy} width={3} height={ROW_H} fill="#C8982A" />}
              {col.pk && <text x={x + 10} y={cy + 15} fill="#C8982A" style={{ fontSize: '8px', fontWeight: 700, fontFamily: 'monospace' }}>PK</text>}
              <text x={x + (col.pk ? 28 : 12)} y={cy + 15} fill="#003366" style={{ fontSize: '11px', fontWeight: 600, fontFamily: 'monospace' }}>{col.name}</text>
              <text x={x + w - 8} y={cy + 15} textAnchor="end" fill="#94a3b8" style={{ fontSize: '9.5px', fontFamily: 'monospace' }}>{col.type}</text>
              {ci < cols.length - 1 && <line x1={x + 6} y1={cy + ROW_H} x2={x + w - 6} y2={cy + ROW_H} stroke="#e8edf4" strokeWidth="1" />}
            </g>
          );
        })}
      </g>
    );
  }

  // Highlighted row y for relationship arrow
  const t1HiY = 10 + HDR_H + 5 * ROW_H + ROW_H / 2; // topic_tags row (index 5)
  const t2HiY = 10 + HDR_H + 1 * ROW_H + ROW_H / 2; // topic_cluster row (index 1)
  const midX = (T1X + T1W + T2X) / 2;

  return (
    <svg viewBox={`0 0 ${W} ${totalH}`} style={{ width: '100%', maxWidth: W, display: 'block' }}>
      <Table x={T1X} w={T1W} name="enriched_signals" cols={t1Cols} ht={t1H} />
      <Table x={T2X} w={T2W} name="golden_records"   cols={t2Cols} ht={t2H} />

      {/* Relationship arrow */}
      <path d={`M ${T1X + T1W} ${t1HiY} C ${T1X + T1W + 20} ${t1HiY} ${T2X - 20} ${t2HiY} ${T2X} ${t2HiY}`}
        fill="none" stroke="#C8982A" strokeWidth="1.5" strokeDasharray="4,3" />
      <polygon points={`${T2X - 1},${t2HiY - 5} ${T2X - 1},${t2HiY + 5} ${T2X + 8},${t2HiY}`} fill="#C8982A" />

      {/* Relationship label */}
      <rect x={midX - 68} y={(t1HiY + t2HiY) / 2 - 12} width={136} height={22} rx={4} fill="#fffbeb" stroke="#C8982A" strokeWidth="1" />
      <text x={midX} y={(t1HiY + t2HiY) / 2 + 3} textAnchor="middle" fill="#92400e" style={{ fontSize: '9px', fontFamily: 'monospace', fontWeight: 600 }}>
        topic_tags[1] → topic_cluster
      </text>
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Business View (unchanged)
// ─────────────────────────────────────────────────────────────────────────────

function BusinessView() {
  const pillars = [
    { num: '01', title: 'Continuous Market Surveillance', summary: 'The system never sleeps, never misses a post, and never ignores a competitor move.', detail: 'Thousands of social media posts, news articles, competitor pages, and RSS feeds are ingested and evaluated every few minutes — 24 hours a day. A human analyst team working full-time cannot monitor this volume, and even if they could, they would miss the subtle early-stage signals that precede a trend becoming obvious. The system sees the first 10 Reddit threads before the story reaches a journalist.' },
    { num: '02', title: 'AI That Separates Signal From Noise', summary: 'Not every mention of a keyword is an opportunity. The AI distinguishes between trend and chatter.', detail: 'Every collected item is evaluated by Claude AI, which classifies it as an opportunity, a threat, or noise — and explains why. It assigns a confidence score, extracts topic tags, determines sentiment, and flags urgency. A spike in mentions of a competitor\'s product name could be excitement about a launch (opportunity) or backlash about a failure (threat). The system tells you which.' },
    { num: '03', title: 'Scored and Prioritized Opportunities', summary: 'The Market Pressure Index tells your team exactly which clusters deserve immediate attention.', detail: 'Each topic cluster receives a Market Pressure Index (MPI) score between 0 and 1, calculated every 5 minutes. The score combines three dimensions: how many signals are arriving (volume), how fast that number is growing (velocity), and whether the conversation is positive or negative (sentiment). Clusters above 0.72 are flagged as high-pressure. Teams focus on the top signals — not everything at once.' },
    { num: '04', title: 'Audience Segments, Not Just Alerts', summary: 'When a threshold is crossed, the system delivers a ready-to-use audience segment — not just a notification.', detail: 'Most intelligence tools tell you something is happening and leave the work to you. This system generates a Golden Record: a package containing the source communities where the trend is originating (subreddits, Twitter accounts, site sections), the signal count, the urgency level, and a recommended action statement. The media-buying team receives an audience definition they can activate immediately — no research, no segmentation work, no delay.' },
  ];
  const scenarios = [
    { tag: 'Competitive Intelligence', title: 'A competitor launches a product', before: 'Your team sees the press release two days later in a newsletter digest.', after: 'The system detects the social spike within 8 minutes of the first product posts. A counter-messaging audience segment — built from the communities discussing it — is ready before the competitor\'s press coverage begins.' },
    { tag: 'Cultural Moment', title: 'An unexpected trend creates demand', before: 'The team sees it trending on social on Tuesday. The brief is ready Thursday. The campaign launches the following week.', after: 'The system detects the velocity spike in the early hours of the trend, before mainstream coverage. The audience is already segmented by the time the morning standup happens.' },
    { tag: 'Regulatory Signal', title: 'A regulator publishes a new rule', before: 'Legal flags it in a weekly compliance review. Marketing learns about it two weeks later.', after: 'The system classifies the regulation announcement as a threat signal with high urgency and surfaces it in the dashboard within minutes. The marketing team knows before the industry press picks it up.' },
    { tag: 'Emerging Keywords', title: 'A new term enters your category', before: 'The paid media team discovers it when CPC on the new keyword has already risen 4×.', after: 'The system detects the emerging terminology cluster 48–72 hours before competitors. The paid team bids on it while inventory is abundant and quality scores are fresh.' },
  ];
  const roles = [
    { role: 'CMO & Marketing Director',
      icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>,
      benefits: ['Real-time view of market pressure across all tracked topic clusters', 'Early warning system for competitive moves and regulatory changes', 'Quantified urgency scores — allocate team attention where it matters most', 'Confidence to act faster than competitors without increasing analytical headcount'] },
    { role: 'Campaign & Brand Manager',
      icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/></svg>,
      benefits: ['Pre-built audience segments delivered the moment a threshold is crossed', 'Recommended action statement removes the first step of brief writing', 'Sentiment breakdown tells you whether the response should be opportunistic or defensive', 'Historical signal data to support post-campaign attribution and timing decisions'] },
    { role: 'Paid Media Specialist',
      icon: <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round"><line x1="12" y1="1" x2="12" y2="23"/><path d="M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6"/></svg>,
      benefits: ['Act on emerging keywords 15–60 minutes before competitors detect the trend', 'Lower CPC: early bids on unsaturated inventory before auction pressure builds', 'Source communities in the Golden Record map directly to targeting parameters', 'Velocity score indicates how fast to move — high velocity means the window is short'] },
  ];

  return (
    <div style={bv.root}>
      <section style={bv.impactBanner}>
        <div style={bv.impactInner}>
          <div style={bv.impactLabel}>THE CORE PROBLEM</div>
          <h2 style={bv.impactHeadline}>By the time your team sees a trend, the window has already opened. Competitors are already bidding.</h2>
          <p style={bv.impactSub}>Marketing teams run on reports, meetings, and briefs. Each step adds delay. This system eliminates the delay by automating everything between signal detection and audience activation.</p>
          <div style={bv.statRow}>
            {[{ value: '48 h', label: 'Average lag from trend emergence to campaign launch — industry benchmark' }, { value: '< 10 min', label: 'Time from signal detection to audience segment ready — this system' }, { value: '15–60 min', label: 'Typical head start over competitors reacting to the same event' }].map(s => (
              <div key={s.value} style={bv.stat}><div style={bv.statValue}>{s.value}</div><div style={bv.statLabel}>{s.label}</div></div>
            ))}
          </div>
        </div>
      </section>

      <section style={bv.section}>
        <Eyebrow light={false}>Why Timing Is Everything</Eyebrow>
        <SectionTitle>The trend lifecycle — and where this system acts</SectionTitle>
        <p style={bv.body}>Every trend follows a similar arc: a quiet early-rise phase, a rapid acceleration toward a peak, and a gradual decline. The commercial value of a trend-based campaign is highest during the early-rise phase — before competitors notice, before CPC costs spike, and while audience attention is still fresh.</p>
        <div style={bv.diagramCard}><TrendCurveDiagram /></div>
        <div style={bv.trendNotes}>
          {[{ dot: '#003366', text: 'This system detects the rising edge within minutes of the first meaningful signal cluster forming.' }, { dot: '#C8982A', text: 'The trend peaks — this is when industry press and competitor monitoring tools typically fire.' }, { dot: '#94a3b8', text: 'Most brands react here, when the peak has passed and auction pressure is highest.' }].map((n, i) => (
            <div key={i} style={bv.trendNote}><div style={{ ...bv.trendDot, backgroundColor: n.dot }} /><span style={bv.trendNoteText}>{n.text}</span></div>
          ))}
        </div>
      </section>

      <section style={bv.section}>
        <Eyebrow light={false}>What the System Delivers</Eyebrow>
        <SectionTitle>Four pillars that turn market noise into marketing advantage</SectionTitle>
        <div style={bv.pillarGrid}>
          {pillars.map(p => (
            <div key={p.num} style={bv.pillar}>
              <div style={bv.pillarNum}>{p.num}</div>
              <div style={bv.pillarAccent} />
              <h3 style={bv.pillarTitle}>{p.title}</h3>
              <p style={bv.pillarSummary}>{p.summary}</p>
              <p style={bv.pillarDetail}>{p.detail}</p>
            </div>
          ))}
        </div>
      </section>

      <section style={bv.section}>
        <Eyebrow light={false}>Speed Comparison</Eyebrow>
        <SectionTitle>Traditional campaign reaction vs. automated response</SectionTitle>
        <p style={bv.body}>The comparison below shows the same trigger event — a market signal emerges — handled by a traditional process and by this system. The top row is the common industry reality. The bottom row is what this platform delivers.</p>
        <div style={bv.diagramCard}><BeforeAfterDiagram /></div>
        <p style={bv.captionText}>In the traditional workflow, the campaign often launches after the trend has already peaked. With this system, the audience segment is ready before a competitor's first meeting has started.</p>
      </section>

      <section style={bv.section}>
        <Eyebrow light={false}>Real Marketing Scenarios</Eyebrow>
        <SectionTitle>What this looks like in practice</SectionTitle>
        <div style={bv.scenarioGrid}>
          {scenarios.map(sc => (
            <div key={sc.tag} style={bv.scenarioCard}>
              <div style={bv.scenarioTag}>{sc.tag}</div>
              <h3 style={bv.scenarioTitle}>{sc.title}</h3>
              <div style={bv.scenarioBefore}><div style={bv.scenarioRowLabel(false)}>Without</div><p style={bv.scenarioText}>{sc.before}</p></div>
              <div style={bv.scenarioAfter}><div style={bv.scenarioRowLabel(true)}>With System</div><p style={bv.scenarioText}>{sc.after}</p></div>
            </div>
          ))}
        </div>
      </section>

      <section style={bv.section}>
        <Eyebrow light={false}>For Your Marketing Team</Eyebrow>
        <SectionTitle>How different roles benefit from the platform</SectionTitle>
        <div style={bv.roleGrid}>
          {roles.map(r => (
            <div key={r.role} style={bv.roleCard}>
              <div style={bv.roleHeader}><div style={bv.roleIcon}>{r.icon}</div><h3 style={bv.roleTitle}>{r.role}</h3></div>
              <ul style={bv.roleList}>{r.benefits.map((b, i) => <li key={i} style={bv.roleItem}><div style={bv.roleDot} /><span style={bv.roleText}>{b}</span></li>)}</ul>
            </div>
          ))}
        </div>
      </section>

      <section style={{ ...bv.section, marginBottom: 0 }}>
        <Eyebrow light={false}>Integration Points</Eyebrow>
        <SectionTitle>Where this connects in your marketing stack</SectionTitle>
        <div style={bv.integGrid}>
          {[{ name: 'Paid Media Platforms', detail: 'Google Ads, Meta Ads — Golden Record event stream consumed for keyword bids and audience targeting activation.' }, { name: 'Marketing Automation', detail: 'Audience proxy attributes (topic tags, urgency, sources) map to audience definitions for email, push, and in-product messaging.' }, { name: 'CRM & DMP Systems', detail: 'Topic cluster scores enrich customer segments, allowing personalization engines to serve trend-aligned content at the right moment.' }, { name: 'Internal Alerting', detail: 'Slack, PagerDuty, or any webhook — the alerts endpoint notifies the right person the moment an MPI threshold is crossed.' }, { name: 'Business Intelligence', detail: 'The enriched_signals table is a queryable audit trail. Any BI tool connected to PostgreSQL can analyze historical signal volume and sentiment trends.' }, { name: 'Content & Creative Tools', detail: 'Recommended action statements in Golden Records feed directly into content brief workflows and creative request systems.' }].map(intg => (
            <div key={intg.name} style={bv.integCard}><div style={bv.integDot} /><div><div style={bv.integName}>{intg.name}</div><div style={bv.integDetail}>{intg.detail}</div></div></div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Engineering View
// ─────────────────────────────────────────────────────────────────────────────

function EngineeringView() {
  const stages = [
    { num: '01', title: 'Ingestion Layer', tool: 'Apache Kafka', why: 'Kafka decouples the rate at which data arrives from the rate at which it can be processed. Social media produces traffic in spikes — a viral post can generate thousands of related signals in seconds. A direct consumer would either overwhelm the processing logic or require over-provisioned infrastructure at all times. Kafka absorbs bursts into a persistent, ordered log. The ETL consumer reads at its own cadence with zero signal loss.',
      how: 'Three producers run as independent services: a Reddit producer polling subreddits every 90 seconds via PRAW, a Twitter filtered stream producer subscribing to real-time keyword events, and a Playwright-based scraper with randomized delays (3–8 s) to respect robots.txt. Every producer publishes JSON events to raw_signals using a consistent schema including event_id (UUID for deduplication), source, collected_at, raw_text, and engagement_score.' },
    { num: '02', title: 'Semantic ETL Layer', tool: 'Airflow + Claude AI', why: 'Airflow was chosen because enrichment is a multi-step, dependency-aware process: deduplication must precede classification, classification must precede storage. A bare cron job or a loop cannot model these dependencies, cannot retry individual failed steps, and cannot surface failures visually. Airflow\'s DAG model makes each transformation independently testable and the entire pipeline inspectable.',
      how: 'The semantic_enrichment_dag runs every 5 minutes, consuming raw_signals in batches of 20 and calling the Claude API (claude-sonnet-4-20250514) with asyncio.gather for parallel requests. Claude returns a structured JSON with five fields: category, confidence, topic_tags, sentiment, and urgency. Claude was chosen over a fine-tuned classifier because it generalises to new topic clusters without retraining — new trends are classified immediately upon emergence.' },
    { num: '03', title: 'Predictive Layer', tool: 'Market Pressure Index', why: 'A single metric — volume, velocity, or sentiment alone — produces unreliable signals. High volume with neutral sentiment is noise. A modest velocity spike with strongly positive sentiment and growing volume is a genuine opportunity. The composite MPI weights three normalized dimensions and makes the result calibratable: weights are environment variables, not hardcoded constants, so sensitivity can be adjusted without a code deployment.',
      how: 'The formula is calculated every 5 minutes over a configurable rolling window (default 60 min) per topic cluster. Volume score = signals_in_window / baseline_avg. Velocity score = (signals_last_15min / signals_prev_15min) − 1, normalized 0–1. Sentiment score = proportion of positive-classified signals. The weighted sum is capped at 1.0. When MPI ≥ 0.72 (configurable), a Golden Record row is written with audience_proxy as JSONB and a 4-hour expires_at TTL.' },
    { num: '04', title: 'Storage Layer', tool: 'PostgreSQL + Redis', why: 'PostgreSQL was chosen over a document store because the data model is relational: signals aggregate into topic clusters, clusters generate golden records, golden records reference signal counts. SQL window functions are the natural primitive for the MPI rolling calculation — no application-side aggregation loop is needed. Redis was added as a hot-path cache: the WebSocket endpoint serves N concurrent clients, but only one MPI grid computation runs per 60-second window.',
      how: 'The schema centers on enriched_signals (topic_tags as TEXT[] for efficient GROUP BY using topic_tags[1]) and golden_records (audience_proxy as JSONB for flexible schema evolution). The MPI grid SQL uses date_trunc with a modulo operation to produce 5-minute time buckets entirely in the database engine. Alembic manages all migrations — no ALTER TABLE is ever executed manually. Nine migration files cover the full schema history from initial tables to API key management.' },
    { num: '05', title: 'API Layer', tool: 'FastAPI + JWT', why: 'FastAPI was selected for three concrete reasons: native ASGI async support (required to hold thousands of WebSocket connections without blocking), automatic OpenAPI documentation generation from Pydantic models (zero documentation maintenance), and dependency-injection-based middleware composition (rate limiting, auth, and scope checking stack cleanly without nested decorators). The WebSocket endpoint must push to all connected clients simultaneously — only an async framework handles this correctly.',
      how: 'Authentication uses short-lived JWTs (HS256, 30-min expiry) for browser sessions and bcrypt-hashed API keys with 12-character prefix lookup for programmatic access. Both are accepted under Authorization: Bearer — the same middleware distinguishes them by prefix. Scope enforcement (read:signals, read:segments, write:alerts) is a dependency function injected into each route. The WebSocket closes with code 4001 on authentication failure to prevent token leakage in error messages.' },
    { num: '06', title: 'Visualization Layer', tool: 'React + Vite', why: 'React was chosen because the dashboard has significant derived state: the MPI grid drives the heat map cells, the gauge widgets, and the KPI counters simultaneously from a single data source. The unidirectional data flow model prevents synchronization bugs between these consumers. Vite provides sub-second hot-module replacement during development and produces an optimized static bundle for production without additional build configuration.',
      how: 'All dashboard state derives from two sources: the WebSocket stream (heatmap data, pushed every 60 s) and a 60-second REST poll (golden records). Losing the WebSocket does not affect the segment sidebar. The WebSocket reconnects with exponential backoff (2 s → 4 s → 8 s … cap 30 s) and authenticates via a JWT query parameter since the browser WebSocket API has no custom header support. The MPI gauge SVG arcs use sweep-flag=1 with largeArc=0 to draw the correct clockwise top-semicircle path.' },
  ];

  const decisions = [
    { num: '01', title: 'Kafka over direct API polling', why: 'Social traffic is bursty. Kafka absorbs spikes into a persistent log — the ETL processes at its own pace, no signal is lost during high-volume events, and the ingestion layer never blocks on downstream latency.' },
    { num: '02', title: 'Claude AI over fine-tuned classifiers', why: 'Zero retraining. When a new trend cluster emerges (new product, regulation, competitor move), the system classifies it immediately — no annotation pipeline, no GPU retraining cycle, no deployment.' },
    { num: '03', title: 'Composite MPI over a single metric', why: 'Volume alone, sentiment alone, or velocity alone each produce systematic false positives. The three-dimension weighted sum is interpretable, auditable, and independently tunable per deployment.' },
    { num: '04', title: 'Config-driven MPI weights', why: 'Marketing teams adjust sensitivity to match campaign cycles without engineering involvement. Weight changes take effect at the next 5-minute calculation — no code change, no deployment.' },
    { num: '05', title: 'PostgreSQL TEXT[] for topic_tags', why: 'Enables GROUP BY topic_tags[1] directly in SQL with native GIN indexing. No separate join table, no extra query complexity, no application-side grouping loop.' },
    { num: '06', title: 'WebSocket push over REST polling', why: 'The dashboard is an operational screen. REST polling creates visible stale-data windows between refresh cycles and generates server load proportional to connected client count.' },
    { num: '07', title: 'JWT + API key dual-auth in one header', why: 'Browser sessions need short-lived tokens (30 min); integrations need long-lived credentials. The same Bearer middleware handles both paths transparently — no separate auth endpoint for API keys.' },
    { num: '08', title: 'Alembic for all schema changes', why: 'Manual ALTER TABLE leaves the database in an undocumented state that breaks new environment setup and makes rollbacks impossible. Alembic migrations are versioned, reversible, and commit-tracked.' },
  ];

  const stackGroups = [
    { label: 'INGESTION + STORAGE', items: [
      { name: 'Apache Kafka',   role: 'Message buffer',      detail: 'Exactly-once semantics via event_id. Decouples ingestion rate from ETL throughput.' },
      { name: 'PostgreSQL 15',  role: 'Persistent store',    detail: 'enriched_signals, golden_records, api_keys, alert_rules. TEXT[] + JSONB for flexible schemas.' },
      { name: 'Redis',          role: 'Hot-path cache',      detail: '60-second TTL on computed MPI grids. Eliminates redundant computation for concurrent WS clients.' },
    ]},
    { label: 'PROCESSING', items: [
      { name: 'Apache Airflow', role: 'ETL orchestration',   detail: 'DAG-based scheduling with per-task retry, backfill, and visual pipeline inspection.' },
      { name: 'Claude AI',      role: 'Signal classification',detail: 'claude-sonnet-4-20250514. Zero-shot topic classification, structured JSON output, no retraining.' },
      { name: 'Alembic',        role: 'Schema migrations',   detail: 'Versioned, reversible migration chain. 9 migration files covering the full schema history.' },
    ]},
    { label: 'APPLICATION', items: [
      { name: 'FastAPI',        role: 'API + WebSocket',     detail: 'ASGI async, Pydantic validation, dependency-injected auth, OpenAPI docs at /openapi.json.' },
      { name: 'React + Vite',   role: 'Dashboard frontend',  detail: 'WS-driven heat map, SVG arc gauges, exponential-backoff reconnect, JWT query-param auth.' },
      { name: 'Docker Compose', role: 'Service orchestration',detail: 'All 9 services in one Compose file. Health checks, named volumes, profile-based startup.' },
    ]},
  ];

  return (
    <div style={ev.root}>

      {/* ── Engineering Impact Banner ──────────────────────────────────────── */}
      <section style={ev.impactBanner}>
        <div style={ev.impactInner}>
          <div style={ev.impactLabel}>ENGINEERING ARCHITECTURE</div>
          <h2 style={ev.impactHeadline}>
            Four decoupled pipeline stages, each independently scalable,
            communicating through well-defined interfaces.
          </h2>
          <p style={ev.impactSub}>
            Every architectural decision is justified by a concrete operational constraint —
            cost, throughput, correctness, or maintainability. No component was chosen for novelty.
          </p>
          <div style={ev.metricRow}>
            {[
              { value: '4',       label: 'Pipeline layers, each with an independent scaling boundary' },
              { value: '5 min',   label: 'ETL enrichment cycle — maximum signal latency end-to-end' },
              { value: '60 s',    label: 'WebSocket push cadence — dashboard always current' },
              { value: '9',       label: 'Containerized services defined in a single Compose file' },
            ].map(m => (
              <div key={m.value} style={ev.metric}>
                <div style={ev.metricValue}>{m.value}</div>
                <div style={ev.metricLabel}>{m.label}</div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── System Architecture ────────────────────────────────────────────── */}
      <section style={ev.section}>
        <Eyebrow light={false}>System Architecture</Eyebrow>
        <SectionTitle>Full component topology and data flow</SectionTitle>
        <p style={ev.body}>
          The system processes data through six component groups arranged as a left-to-right pipeline.
          Each group communicates with the next through a named interface — Kafka topics or SQL tables —
          never through direct function calls between components. This ensures that any group can be
          replaced, scaled, or restarted independently without affecting the others.
        </p>
        <div style={ev.diagramCard}>
          <ArchitectureDiagram />
        </div>
        <div style={ev.archNotes}>
          {[
            { label: 'INGESTION → KAFKA', note: 'Producers push JSON events to the raw_signals topic. Kafka persists them until the ETL consumer is ready — absorbing any ingestion burst without backpressure on the sources.' },
            { label: 'KAFKA → ETL', note: 'Airflow polls the topic in batches of 20 on a 5-minute schedule. Claude AI classifies each batch in parallel using asyncio.gather, keeping the ETL cycle well within its window.' },
            { label: 'ETL → STORAGE', note: 'Enriched rows are written to enriched_signals with ON CONFLICT DO NOTHING for idempotency. Golden Records are written separately when MPI exceeds threshold.' },
            { label: 'STORAGE → API → DASHBOARD', note: 'FastAPI queries PostgreSQL on-demand and caches results in Redis. The WebSocket endpoint pushes the computed MPI grid to all connected clients every 60 seconds.' },
          ].map((n, i) => (
            <div key={i} style={ev.archNote}>
              <div style={ev.archNoteLabel}>{n.label}</div>
              <div style={ev.archNoteText}>{n.note}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Pipeline Stages ────────────────────────────────────────────────── */}
      <section style={ev.section}>
        <Eyebrow light={false}>Pipeline Stages</Eyebrow>
        <SectionTitle>Engineering rationale for each component decision</SectionTitle>
        <div style={ev.stageGrid}>
          {stages.map(s => (
            <div key={s.num} style={ev.stageCard}>
              <div style={ev.stageHeader}>
                <div style={ev.stageNum}>{s.num}</div>
                <div>
                  <div style={ev.stageTitle}>{s.title}</div>
                  <div style={ev.stageTool}>{s.tool}</div>
                </div>
              </div>
              <div style={ev.stageAccent} />
              <div style={ev.stageWhy}>
                <span style={ev.stageTag}>WHY</span>
                {s.why}
              </div>
              <div style={ev.stageHow}>
                <span style={ev.stageTag2}>HOW</span>
                {s.how}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── MPI Formula ────────────────────────────────────────────────────── */}
      <section style={ev.section}>
        <Eyebrow light={false}>MPI Scoring Model</Eyebrow>
        <SectionTitle>How market pressure is calculated — formula and calibration</SectionTitle>
        <p style={ev.body}>
          The Market Pressure Index is a rolling composite score (0.0–1.0) calculated per topic cluster
          every 5 minutes. It combines three normalized dimensions with configurable weights. All three
          weights and the threshold are environment variables — a marketing team can increase velocity
          sensitivity during fast-moving events or lower the threshold during high-stakes campaign periods
          without touching the codebase.
        </p>
        <div style={ev.diagramCard}><MpiFormulaDiagram /></div>
        <div style={ev.mpiNotes}>
          {[
            { label: 'Volume (0.40)', note: 'Normalized against each cluster\'s rolling baseline average to avoid rewarding inherently high-traffic clusters over emerging ones.' },
            { label: 'Velocity (0.35)', note: 'Ratio of the last 15-minute bucket to the preceding 15-minute bucket, normalized to 0–1. A ratio of 2.0 (doubling) maps to 1.0. Captures acceleration, not just volume.' },
            { label: 'Sentiment (0.25)', note: 'Proportion of signals classified as positive within the window. Negative-dominant clusters are surfaced as threats, not opportunities, even at high volume.' },
          ].map((n, i) => (
            <div key={i} style={ev.mpiNote}>
              <div style={ev.mpiNoteLabel}>{n.label}</div>
              <div style={ev.mpiNoteText}>{n.note}</div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Data Schema ────────────────────────────────────────────────────── */}
      <section style={ev.section}>
        <Eyebrow light={false}>Data Schema</Eyebrow>
        <SectionTitle>Core table structure and the key relationship between them</SectionTitle>
        <p style={ev.body}>
          The two primary tables are <code style={ev.code}>enriched_signals</code> and{' '}
          <code style={ev.code}>golden_records</code>. The conceptual link between them is the
          topic cluster name: <code style={ev.code}>topic_tags[1]</code> in enriched_signals is
          the value that the MPI aggregation groups by, and <code style={ev.code}>topic_cluster</code> in
          golden_records stores the result of that group. They are not joined by a foreign key — the
          relationship is semantic, enforced at the application layer, which allows the schema to evolve
          independently on each side.
        </p>
        <div style={ev.diagramCard}><DataSchemaDiagram /></div>
        <p style={ev.captionText}>
          Highlighted rows (gold left border) are the fields that link the two tables.
          PK columns are marked. The dashed arrow shows the conceptual relationship —
          not a database foreign key constraint.
        </p>
      </section>

      {/* ── Design Decisions ───────────────────────────────────────────────── */}
      <section style={ev.section}>
        <Eyebrow light={false}>Design Decisions</Eyebrow>
        <SectionTitle>Eight architectural choices and the constraint behind each one</SectionTitle>
        <div style={ev.decisionGrid}>
          {decisions.map(d => (
            <div key={d.num} style={ev.decisionCard}>
              <div style={ev.decisionNum}>{d.num}</div>
              <div style={ev.decisionAccent} />
              <h3 style={ev.decisionTitle}>{d.title}</h3>
              <p style={ev.decisionWhy}>{d.why}</p>
            </div>
          ))}
        </div>
      </section>

      {/* ── Tech Stack ─────────────────────────────────────────────────────── */}
      <section style={{ ...ev.section, marginBottom: 0 }}>
        <Eyebrow light={false}>Technology Stack</Eyebrow>
        <SectionTitle>Components grouped by pipeline layer</SectionTitle>
        <div style={ev.stackOuter}>
          {stackGroups.map(group => (
            <div key={group.label} style={ev.stackGroup}>
              <div style={ev.stackGroupLabel}>{group.label}</div>
              <div style={ev.stackGroupItems}>
                {group.items.map(item => (
                  <div key={item.name} style={ev.stackCard}>
                    <div style={ev.stackName}>{item.name}</div>
                    <div style={ev.stackRole}>{item.role}</div>
                    <div style={ev.stackDetail}>{item.detail}</div>
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Shared helpers
// ─────────────────────────────────────────────────────────────────────────────

function Eyebrow({ children, light = false }) {
  return (
    <div style={{ ...shared.eyebrow, color: light ? 'var(--gold-light)' : 'var(--gold)' }}>
      <div style={{ ...shared.eyebrowLine, backgroundColor: light ? 'var(--gold-light)' : 'var(--gold)' }} />
      {children}
    </div>
  );
}

function SectionTitle({ children }) {
  return <h2 style={shared.sectionTitle}>{children}</h2>;
}

// ─────────────────────────────────────────────────────────────────────────────
// Main page
// ─────────────────────────────────────────────────────────────────────────────

export default function InfoPage() {
  const [view, setView] = useState('business');
  return (
    <div style={p.page}>
      <header style={p.header}>
        <div style={p.headerInner}>
          <Eyebrow light>Documentation</Eyebrow>
          <h1 style={p.title}>Trend Arbitrage <em style={{ fontStyle: 'italic', color: 'var(--gold-light)' }}>&amp; Zero-Day Response</em></h1>
          <p style={p.subtitle}>Select a perspective to explore how the platform works and the value it delivers.</p>
          <div style={p.tabs}>
            <button style={{ ...p.tab, ...(view === 'business' ? p.tabActive : {}) }} onClick={() => setView('business')}>Business View</button>
            <button style={{ ...p.tab, ...(view === 'engineering' ? p.tabActive : {}) }} onClick={() => setView('engineering')}>Engineering View</button>
          </div>
        </div>
      </header>
      {view === 'business' ? <BusinessView /> : <EngineeringView />}
      <footer style={p.footer}>
        <span>OPB · OCTAVIO PÉREZ BRAVO · TREND ARBITRAGE & ZERO-DAY RESPONSE</span>
        <span>{new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' }).toUpperCase()}</span>
      </footer>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Styles
// ─────────────────────────────────────────────────────────────────────────────

const shared = {
  eyebrow: { display: 'inline-flex', alignItems: 'center', gap: 8, fontSize: 9, fontFamily: 'var(--fb)', fontWeight: 500, letterSpacing: '4px', textTransform: 'uppercase', marginBottom: 10 },
  eyebrowLine: { width: 24, height: 1, flexShrink: 0 },
  sectionTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300, color: '#0a1628', margin: '0 0 4px', lineHeight: 1.25 },
};

const p = {
  page: { minHeight: '100vh', backgroundColor: 'var(--light)' },
  header: { backgroundColor: 'var(--primary)', backgroundImage: `linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px)`, backgroundSize: '48px 48px', padding: '28px 48px 0' },
  headerInner: { maxWidth: 1200, margin: '0 auto' },
  title: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 28, fontWeight: 300, color: '#ffffff', margin: '0 0 8px', lineHeight: 1.1 },
  subtitle: { fontFamily: 'var(--fb)', fontSize: 12, color: 'rgba(255,255,255,0.5)', margin: '0 0 28px', lineHeight: 1.6 },
  tabs: { display: 'flex', gap: 4, borderBottom: '1px solid rgba(255,255,255,0.1)' },
  tab: { background: 'none', border: 'none', borderBottom: '2px solid transparent', cursor: 'pointer', padding: '10px 20px', marginBottom: -1, fontFamily: 'var(--fb)', fontSize: 11, fontWeight: 500, letterSpacing: '1.5px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)', transition: 'color 0.15s' },
  tabActive: { color: 'var(--gold-light)', borderBottomColor: 'var(--gold-light)' },
  footer: { backgroundColor: 'var(--primary)', padding: '20px 48px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', fontFamily: 'var(--fb)', fontSize: 9, letterSpacing: '3px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)' },
};

const bv = {
  root: { backgroundColor: 'var(--light)' },
  section: { maxWidth: 1200, margin: '0 auto', padding: '56px 48px', borderBottom: '1px solid #e8edf4' },
  impactBanner: { backgroundColor: '#003366', backgroundImage: `linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px)`, backgroundSize: '48px 48px' },
  impactInner: { maxWidth: 1200, margin: '0 auto', padding: '56px 48px' },
  impactLabel: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '4px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 16 },
  impactHeadline: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 30, fontWeight: 300, color: '#ffffff', margin: '0 0 16px', lineHeight: 1.35, maxWidth: 700 },
  impactSub: { fontFamily: 'var(--fb)', fontSize: 14, color: 'rgba(255,255,255,0.6)', lineHeight: 1.75, maxWidth: 600, margin: '0 0 40px' },
  statRow: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 24 },
  stat: { borderLeft: '2px solid #C8982A', paddingLeft: 18 },
  statValue: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 34, fontWeight: 300, color: '#E8C46A', lineHeight: 1, marginBottom: 8 },
  statLabel: { fontFamily: 'var(--fb)', fontSize: 12, color: 'rgba(255,255,255,0.5)', lineHeight: 1.55 },
  body: { fontFamily: 'var(--fb)', fontSize: 14, color: '#475569', lineHeight: 1.8, margin: '14px 0 0' },
  captionText: { fontFamily: 'var(--fb)', fontSize: 12, color: '#94a3b8', lineHeight: 1.65, margin: '14px 0 0', fontStyle: 'italic' },
  diagramCard: { backgroundColor: '#ffffff', borderRadius: 14, padding: '32px', boxShadow: '0 1px 6px rgba(0,51,102,0.09)', marginTop: 28, overflowX: 'auto' },
  trendNotes: { display: 'flex', flexDirection: 'column', gap: 10, marginTop: 20 },
  trendNote: { display: 'flex', alignItems: 'flex-start', gap: 12 },
  trendDot: { width: 10, height: 10, borderRadius: '50%', flexShrink: 0, marginTop: 4 },
  trendNoteText: { fontFamily: 'var(--fb)', fontSize: 13, color: '#475569', lineHeight: 1.6 },
  pillarGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 28, marginTop: 32 },
  pillar: { backgroundColor: '#ffffff', borderRadius: 14, padding: '28px 28px 24px', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' },
  pillarNum: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 44, fontWeight: 300, color: '#f1f5f9', lineHeight: 1, marginBottom: 4, userSelect: 'none' },
  pillarAccent: { width: 36, height: 3, backgroundColor: '#C8982A', borderRadius: 2, marginBottom: 14 },
  pillarTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 17, fontWeight: 400, color: '#0a1628', margin: '0 0 8px' },
  pillarSummary: { fontFamily: 'var(--fb)', fontSize: 13.5, fontWeight: 600, color: '#003366', lineHeight: 1.55, margin: '0 0 10px' },
  pillarDetail: { fontFamily: 'var(--fb)', fontSize: 13, color: '#475569', lineHeight: 1.75, margin: 0 },
  scenarioGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 20, marginTop: 28 },
  scenarioCard: { backgroundColor: '#ffffff', borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' },
  scenarioTag: { backgroundColor: '#003366', padding: '8px 18px', fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', color: '#E8C46A' },
  scenarioTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 16, fontWeight: 300, color: '#0a1628', margin: '16px 18px 12px' },
  scenarioBefore: { backgroundColor: '#fafafa', borderTop: '1px solid #f1f5f9', padding: '12px 18px' },
  scenarioAfter: { backgroundColor: '#f0fdf8', borderTop: '1px solid #dcfce7', padding: '12px 18px 18px' },
  scenarioRowLabel: (isAfter) => ({ fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', color: isAfter ? '#16a34a' : '#94a3b8', marginBottom: 6 }),
  scenarioText: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.65, margin: 0 },
  roleGrid: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 20, marginTop: 28 },
  roleCard: { backgroundColor: '#ffffff', borderRadius: 12, boxShadow: '0 1px 4px rgba(0,51,102,0.08)', overflow: 'hidden', borderTop: '3px solid #C8982A' },
  roleHeader: { display: 'flex', alignItems: 'center', gap: 12, padding: '20px 20px 14px' },
  roleIcon: { color: '#003366', flexShrink: 0 },
  roleTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 15, fontWeight: 300, color: '#0a1628', margin: 0 },
  roleList: { listStyle: 'none', margin: 0, padding: '0 20px 20px' },
  roleItem: { display: 'flex', alignItems: 'flex-start', gap: 10, marginBottom: 10 },
  roleDot: { width: 5, height: 5, borderRadius: '50%', backgroundColor: '#C8982A', flexShrink: 0, marginTop: 6 },
  roleText: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.6 },
  integGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 14, marginTop: 28 },
  integCard: { display: 'flex', alignItems: 'flex-start', gap: 14, backgroundColor: '#ffffff', borderRadius: 10, padding: '16px 18px', boxShadow: '0 1px 3px rgba(0,51,102,0.07)' },
  integDot: { width: 8, height: 8, borderRadius: '50%', backgroundColor: '#C8982A', flexShrink: 0, marginTop: 5 },
  integName: { fontFamily: 'var(--fb)', fontSize: 12, fontWeight: 700, color: '#003366', marginBottom: 4 },
  integDetail: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#64748b', lineHeight: 1.6 },
};

const ev = {
  root: { backgroundColor: 'var(--light)' },
  section: { maxWidth: 1200, margin: '0 auto', padding: '56px 48px', borderBottom: '1px solid #e8edf4' },
  body: { fontFamily: 'var(--fb)', fontSize: 13.5, color: '#475569', lineHeight: 1.8, margin: '12px 0 0' },
  code: { fontFamily: 'monospace', fontSize: 12.5, backgroundColor: '#f1f5f9', color: '#0a1628', padding: '1px 5px', borderRadius: 4 },
  captionText: { fontFamily: 'var(--fb)', fontSize: 12, color: '#94a3b8', lineHeight: 1.65, margin: '14px 0 0', fontStyle: 'italic' },

  // Impact banner
  impactBanner: { backgroundColor: '#003366', backgroundImage: `linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px)`, backgroundSize: '48px 48px' },
  impactInner: { maxWidth: 1200, margin: '0 auto', padding: '56px 48px' },
  impactLabel: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '4px', textTransform: 'uppercase', color: 'rgba(255,255,255,0.35)', marginBottom: 16 },
  impactHeadline: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 28, fontWeight: 300, color: '#ffffff', margin: '0 0 16px', lineHeight: 1.4, maxWidth: 680 },
  impactSub: { fontFamily: 'var(--fb)', fontSize: 13, color: 'rgba(255,255,255,0.6)', lineHeight: 1.75, maxWidth: 580, margin: '0 0 40px' },
  metricRow: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 24 },
  metric: { borderLeft: '2px solid #C8982A', paddingLeft: 18 },
  metricValue: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 34, fontWeight: 300, color: '#E8C46A', lineHeight: 1, marginBottom: 8 },
  metricLabel: { fontFamily: 'var(--fb)', fontSize: 12, color: 'rgba(255,255,255,0.5)', lineHeight: 1.55 },

  // Diagram card
  diagramCard: { backgroundColor: '#ffffff', borderRadius: 14, padding: '32px', boxShadow: '0 1px 6px rgba(0,51,102,0.09)', marginTop: 28, overflowX: 'auto' },

  // Architecture notes
  archNotes: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 14, marginTop: 24 },
  archNote: { backgroundColor: '#ffffff', borderRadius: 10, padding: '14px 16px', boxShadow: '0 1px 3px rgba(0,51,102,0.07)', borderLeft: '3px solid #C8982A' },
  archNoteLabel: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#C8982A', marginBottom: 5 },
  archNoteText: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.65 },

  // Stage cards (same visual DNA as BV pillar)
  stageGrid: { display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 24, marginTop: 32 },
  stageCard: { backgroundColor: '#ffffff', borderRadius: 14, padding: '24px 26px 22px', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' },
  stageHeader: { display: 'flex', alignItems: 'flex-start', gap: 16, marginBottom: 4 },
  stageNum: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 36, fontWeight: 300, color: '#f1f5f9', lineHeight: 1, flexShrink: 0, userSelect: 'none' },
  stageTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 16, fontWeight: 400, color: '#0a1628', lineHeight: 1.2 },
  stageTool: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '2px', textTransform: 'uppercase', color: '#C8982A', marginTop: 4 },
  stageAccent: { width: 36, height: 3, backgroundColor: '#C8982A', borderRadius: 2, margin: '10px 0 14px' },
  stageWhy: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.75, marginBottom: 10 },
  stageHow: { fontFamily: 'var(--fb)', fontSize: 12.5, color: '#475569', lineHeight: 1.75 },
  stageTag: { display: 'inline-block', fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700, letterSpacing: '2px', color: '#ffffff', backgroundColor: '#003366', borderRadius: 4, padding: '2px 6px', marginRight: 8, verticalAlign: 'middle', marginBottom: 2 },
  stageTag2: { display: 'inline-block', fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700, letterSpacing: '2px', color: '#003366', backgroundColor: '#e0eaf4', borderRadius: 4, padding: '2px 6px', marginRight: 8, verticalAlign: 'middle', marginBottom: 2 },

  // MPI notes
  mpiNotes: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 14, marginTop: 20 },
  mpiNote: { backgroundColor: '#ffffff', borderRadius: 10, padding: '14px 16px', boxShadow: '0 1px 3px rgba(0,51,102,0.07)', borderTop: '3px solid #C8982A' },
  mpiNoteLabel: { fontFamily: 'var(--fb)', fontSize: 11, fontWeight: 700, color: '#003366', marginBottom: 6 },
  mpiNoteText: { fontFamily: 'var(--fb)', fontSize: 12, color: '#475569', lineHeight: 1.65 },

  // Design decisions (same visual DNA as BV pillar)
  decisionGrid: { display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 20, marginTop: 32 },
  decisionCard: { backgroundColor: '#ffffff', borderRadius: 12, padding: '20px 20px 18px', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' },
  decisionNum: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 36, fontWeight: 300, color: '#f1f5f9', lineHeight: 1, marginBottom: 2, userSelect: 'none' },
  decisionAccent: { width: 28, height: 3, backgroundColor: '#C8982A', borderRadius: 2, margin: '6px 0 12px' },
  decisionTitle: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 14, fontWeight: 400, color: '#0a1628', margin: '0 0 10px', lineHeight: 1.3 },
  decisionWhy: { fontFamily: 'var(--fb)', fontSize: 12, color: '#475569', lineHeight: 1.7, margin: 0 },

  // Tech stack grouped
  stackOuter: { display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 24, marginTop: 28 },
  stackGroup: {},
  stackGroupLabel: { fontFamily: 'var(--fb)', fontSize: 8, fontWeight: 700, letterSpacing: '3px', textTransform: 'uppercase', color: '#003366', backgroundColor: '#e0eaf4', padding: '7px 12px', borderRadius: '8px 8px 0 0', borderBottom: '2px solid #C8982A' },
  stackGroupItems: { display: 'flex', flexDirection: 'column', gap: 1 },
  stackCard: { backgroundColor: '#ffffff', padding: '14px 16px', boxShadow: '0 1px 2px rgba(0,51,102,0.06)' },
  stackName: { fontFamily: "'Fraunces', Georgia, serif", fontSize: 14, fontWeight: 400, color: '#003366', marginBottom: 2 },
  stackRole: { fontFamily: 'var(--fb)', fontSize: 9, fontWeight: 700, letterSpacing: '1.5px', textTransform: 'uppercase', color: '#C8982A', marginBottom: 6 },
  stackDetail: { fontFamily: 'var(--fb)', fontSize: 11.5, color: '#64748b', lineHeight: 1.6 },
};
