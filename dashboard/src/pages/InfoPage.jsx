import React, { useState } from 'react';

// ─────────────────────────────────────────────────────────────────────────────
// SVG Diagrams
// ─────────────────────────────────────────────────────────────────────────────

function PipelineDiagram() {
  const layers = [
    { title: 'DATA SOURCES', desc: 'Reddit · Twitter/X · Web Scrapers · RSS Feeds', dark: true },
    { title: 'APACHE KAFKA', desc: 'Message buffer — decouples ingestion from processing, absorbs traffic bursts', dark: false },
    { title: 'AIRFLOW  +  CLAUDE AI', desc: 'Semantic ETL — classifies signals as opportunity / threat / noise every 5 min', dark: false },
    { title: 'POSTGRESQL  +  REDIS', desc: 'enriched_signals · golden_records (Postgres) + hot-path cache (Redis)', dark: false },
    { title: 'FASTAPI', desc: 'REST endpoints + WebSocket /ws/heatmap — pushes updated MPI grid every 60 s', dark: false },
    { title: 'REACT DASHBOARD', desc: 'Live opportunity heat map · Per-cluster MPI gauges · Golden Record sidebar', dark: true },
  ];
  const BH = 62, GAP = 30, W = 580, PAD = 14;
  const totalH = PAD * 2 + layers.length * BH + (layers.length - 1) * GAP;

  return (
    <svg viewBox={`0 0 ${W} ${totalH}`} style={{ width: '100%', maxWidth: 580, display: 'block' }}>
      {layers.map((layer, i) => {
        const y = PAD + i * (BH + GAP);
        const fill = layer.dark ? '#003366' : '#1A4D80';
        const arrowTop = y + BH;
        const arrowBot = arrowTop + GAP;
        return (
          <g key={i}>
            <rect x={10} y={y} width={W - 20} height={BH} rx={8}
              fill={fill} stroke="#C8982A" strokeWidth="1.5" />
            <text x={28} y={y + 22} fill="#E8C46A"
              style={{ fontSize: '11px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1.5px' }}>
              {layer.title}
            </text>
            <text x={28} y={y + 44} fill="rgba(255,255,255,0.65)"
              style={{ fontSize: '11.5px', fontFamily: 'system-ui, sans-serif' }}>
              {layer.desc}
            </text>
            {i < layers.length - 1 && (
              <>
                <line x1={W / 2} y1={arrowTop} x2={W / 2} y2={arrowBot - 9}
                  stroke="#C8982A" strokeWidth="1.5" />
                <polygon
                  points={`${W / 2 - 7},${arrowBot - 9} ${W / 2 + 7},${arrowBot - 9} ${W / 2},${arrowBot + 2}`}
                  fill="#C8982A" />
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
    { label: 'Velocity Score',  weight: '× 0.35', barW: 0.68, note: '(last 15 min ÷ prev 15 min) − 1, normalised' },
    { label: 'Sentiment Score', weight: '× 0.25', barW: 0.91, note: 'proportion of positive signals in window' },
  ];
  const ROW = 56, PAD = 16, LABEL_W = 140, WEIGHT_W = 52, BAR_X = LABEL_W + 12;
  const BAR_AREA = W - BAR_X - WEIGHT_W - PAD * 2 - 12;
  const totalH = PAD + components.length * ROW + 64;

  return (
    <svg viewBox={`0 0 ${W} ${totalH}`} style={{ width: '100%', maxWidth: 540, display: 'block' }}>
      {/* Header */}
      <text x={PAD} y={PAD + 14} fill="#0a1628"
        style={{ fontSize: '11px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1px' }}>
        MPI SCORE  =  Weighted Sum  (0.0 – 1.0)
      </text>

      {components.map((c, i) => {
        const y = PAD + 28 + i * ROW;
        const barFill = W * c.barW * 0.72;
        return (
          <g key={i}>
            {/* Row bg */}
            <rect x={PAD} y={y} width={W - PAD * 2} height={ROW - 6} rx={6}
              fill={i % 2 === 0 ? '#f8fafc' : '#f1f5f9'} />
            {/* Label */}
            <text x={PAD + 10} y={y + 22} fill="#0a1628"
              style={{ fontSize: '12px', fontWeight: 600, fontFamily: 'system-ui, sans-serif' }}>
              {c.label}
            </text>
            <text x={PAD + 10} y={y + 38} fill="#94a3b8"
              style={{ fontSize: '9.5px', fontFamily: 'system-ui, sans-serif' }}>
              {c.note}
            </text>
            {/* Bar track */}
            <rect x={BAR_X + PAD} y={y + 18} width={BAR_AREA} height={8} rx={4} fill="#e2e8f0" />
            {/* Bar fill */}
            <rect x={BAR_X + PAD} y={y + 18} width={BAR_AREA * c.barW} height={8} rx={4} fill="#C8982A" />
            {/* Weight */}
            <text x={W - PAD - WEIGHT_W + 4} y={y + 27} fill="#003366"
              style={{ fontSize: '12px', fontWeight: 700, fontFamily: 'monospace' }}>
              {c.weight}
            </text>
          </g>
        );
      })}

      {/* Result line */}
      <line x1={PAD} y1={totalH - 30} x2={W - PAD} y2={totalH - 30} stroke="#e2e8f0" strokeWidth="1" />
      <text x={PAD} y={totalH - 10} fill="#003366"
        style={{ fontSize: '11.5px', fontFamily: 'system-ui, sans-serif' }}>
        When MPI ≥ 0.72 →
      </text>
      <text x={PAD + 118} y={totalH - 10} fill="#E03448"
        style={{ fontSize: '11.5px', fontWeight: 700, fontFamily: 'system-ui, sans-serif' }}>
        Golden Record triggered — audience segment ready for activation
      </text>
    </svg>
  );
}

function SignalLifecycleDiagram() {
  const steps = [
    { id: '01', label: 'Raw Signal', sub: 'Social post, news article\nor scraped page' },
    { id: '02', label: 'Kafka Buffer', sub: 'Persisted until\nETL processes it' },
    { id: '03', label: 'AI Classification', sub: 'Category · Sentiment\nConfidence · Tags' },
    { id: '04', label: 'MPI Calculation', sub: 'Volume + Velocity\n+ Sentiment scored' },
    { id: '05', label: 'Golden Record', sub: 'Audience segment\n+ Recommended action' },
  ];
  const W = 680, BW = 104, BH = 72, GAP = 24, PAD = 16;
  const step = BW + GAP;
  const totalW = steps.length * step - GAP + PAD * 2;

  return (
    <svg viewBox={`0 0 ${totalW} ${BH + PAD * 2}`}
      style={{ width: '100%', maxWidth: totalW, display: 'block' }}>
      {steps.map((s, i) => {
        const x = PAD + i * step;
        return (
          <g key={i}>
            <rect x={x} y={PAD} width={BW} height={BH} rx={8}
              fill="#003366" stroke="#C8982A" strokeWidth="1.5" />
            <text x={x + BW / 2} y={PAD + 16} textAnchor="middle" fill="#E8C46A"
              style={{ fontSize: '9px', fontWeight: 700, fontFamily: 'monospace', letterSpacing: '1px' }}>
              {s.id}
            </text>
            <text x={x + BW / 2} y={PAD + 30} textAnchor="middle" fill="#ffffff"
              style={{ fontSize: '11px', fontWeight: 600, fontFamily: 'system-ui, sans-serif' }}>
              {s.label}
            </text>
            {s.sub.split('\n').map((line, li) => (
              <text key={li} x={x + BW / 2} y={PAD + 47 + li * 14} textAnchor="middle"
                fill="rgba(255,255,255,0.6)"
                style={{ fontSize: '9.5px', fontFamily: 'system-ui, sans-serif' }}>
                {line}
              </text>
            ))}
            {i < steps.length - 1 && (
              <>
                <line x1={x + BW + 2} y1={PAD + BH / 2} x2={x + BW + GAP - 8} y2={PAD + BH / 2}
                  stroke="#C8982A" strokeWidth="1.5" />
                <polygon
                  points={`${x + BW + GAP - 8},${PAD + BH / 2 - 5} ${x + BW + GAP - 8},${PAD + BH / 2 + 5} ${x + BW + GAP + 1},${PAD + BH / 2}`}
                  fill="#C8982A" />
              </>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Business View
// ─────────────────────────────────────────────────────────────────────────────

function BusinessView() {
  const advantages = [
    {
      title: 'Speed',
      body: 'The system detects and validates an emerging signal within minutes of it appearing online. A trend that would take a human analyst hours to spot is ready for action in under 10 minutes.',
    },
    {
      title: 'Scale',
      body: 'Thousands of social posts, articles, and competitor pages are evaluated continuously — 24 hours a day, 7 days a week — without increasing headcount.',
    },
    {
      title: 'Prioritization',
      body: 'Not every signal is an opportunity. The Market Pressure Index (MPI) scores each topic cluster on a 0–1 scale, so teams focus effort on clusters that actually warrant attention.',
    },
    {
      title: 'Readiness',
      body: 'When a threshold is crossed, the system does not just send an alert — it delivers a pre-built audience segment (sources, handles, site sections) and a recommended action brief, ready for execution.',
    },
  ];

  const integrations = [
    { name: 'Paid Media Platforms', detail: 'The Golden Record event stream (Kafka) is consumed by media-buying tools to initiate keyword bids or audience targeting on Google Ads and Meta Ads before competitors respond.' },
    { name: 'Marketing Automation', detail: 'Segment attributes from the audience proxy (subreddits, Twitter accounts, content topics) map directly into audience definitions for email, push, and in-product messaging tools.' },
    { name: 'CRM & DMP Systems', detail: 'Topic tags and urgency scores can enrich existing customer segments, allowing personalization engines to surface trend-aligned content to the right users.' },
    { name: 'BI and Reporting', detail: 'The enriched_signals table provides a structured audit trail. Any BI tool connected to the PostgreSQL database can query historical signal volume, sentiment shifts, and MPI trends over time.' },
    { name: 'Internal Alerting', detail: 'The alerts endpoint integrates with Slack, PagerDuty, or any webhook-capable platform to notify the right team member when an MPI threshold is crossed.' },
  ];

  const outcomes = [
    { metric: '15–60 min', label: 'Typical head start over competitors reacting to the same trend' },
    { metric: '5 min', label: 'MPI recalculation cadence — signals are never more than one cycle stale' },
    { metric: '0.72', label: 'Default MPI threshold for automatic Golden Record generation, fully adjustable' },
    { metric: '60 min', label: 'Rolling window — the dashboard reflects market pressure as it is now, not last week' },
  ];

  return (
    <div style={bv.root}>

      {/* What it is */}
      <section style={bv.section}>
        <Eyebrow>What is this system</Eyebrow>
        <SectionTitle>A continuous market listening post that turns social noise into timed action.</SectionTitle>
        <p style={bv.body}>
          Trend Arbitrage & Zero-Day Response is a real-time intelligence platform that monitors
          social media, news outlets, and competitor digital activity at scale. It detects meaningful
          shifts in market conversation — price signals, regulatory moves, product launches, cultural
          moments — before they saturate the mainstream news cycle.
        </p>
        <p style={bv.body}>
          The system does not just flag activity. It applies AI-driven analysis to separate genuine
          market pressure from background noise, scores the urgency of each topic cluster, and
          — when the evidence crosses a configurable threshold — automatically produces a ready-to-use
          audience segment with a recommended marketing action. The entire cycle from signal detection
          to actionable brief takes less than 10 minutes.
        </p>
      </section>

      {/* Signal lifecycle */}
      <section style={bv.section}>
        <Eyebrow>How it works</Eyebrow>
        <SectionTitle>Five steps from raw signal to audience segment</SectionTitle>
        <div style={{ overflowX: 'auto', marginTop: 24 }}>
          <SignalLifecycleDiagram />
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(5,1fr)', gap: 12, marginTop: 16 }}>
          {[
            'Social posts, articles, and scraped pages arrive continuously.',
            'Kafka holds every event safely while downstream systems catch up.',
            'Claude AI classifies each signal: opportunity, threat, or noise.',
            'A rolling score measures volume, velocity, and sentiment per topic.',
            'Clusters above the threshold become actionable audience briefs.',
          ].map((t, i) => (
            <p key={i} style={bv.stepNote}>{t}</p>
          ))}
        </div>
      </section>

      {/* Advantages */}
      <section style={bv.section}>
        <Eyebrow>Key advantages</Eyebrow>
        <SectionTitle>What makes the approach different</SectionTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2,1fr)', gap: 20, marginTop: 24 }}>
          {advantages.map(a => (
            <div key={a.title} style={bv.card}>
              <div style={bv.cardAccent} />
              <div style={bv.cardBody}>
                <h3 style={bv.cardTitle}>{a.title}</h3>
                <p style={bv.cardText}>{a.body}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* Integrations */}
      <section style={bv.section}>
        <Eyebrow>Integrations</Eyebrow>
        <SectionTitle>Where this data connects in the marketing stack</SectionTitle>
        <div style={{ marginTop: 24 }}>
          {integrations.map((intg, i) => (
            <div key={i} style={bv.integRow}>
              <div style={bv.integName}>{intg.name}</div>
              <div style={bv.integDetail}>{intg.detail}</div>
            </div>
          ))}
        </div>
      </section>

      {/* Outcomes */}
      <section style={bv.section}>
        <Eyebrow>Measurable targets</Eyebrow>
        <SectionTitle>What the system is built to deliver</SectionTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4,1fr)', gap: 16, marginTop: 24 }}>
          {outcomes.map(o => (
            <div key={o.metric} style={bv.metricCard}>
              <div style={bv.metricAccent} />
              <div style={bv.metricBody}>
                <span style={bv.metricValue}>{o.metric}</span>
                <span style={bv.metricLabel}>{o.label}</span>
              </div>
            </div>
          ))}
        </div>
        <p style={{ ...bv.body, marginTop: 20 }}>
          These figures assume the system is running with live data sources. The 60-minute rolling
          window and 0.72 MPI threshold are defaults — both are configurable without a code change
          through environment variables, allowing marketing and data teams to tune sensitivity
          independently.
        </p>
      </section>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
// Engineering View
// ─────────────────────────────────────────────────────────────────────────────

function EngineeringView() {
  const layers = [
    {
      num: '01',
      title: 'Ingestion Layer — Apache Kafka',
      why: 'Apache Kafka was chosen as the ingestion backbone for a single critical reason: it decouples the rate at which data arrives from the rate at which it can be processed. Social media produces traffic in spikes — a viral post can generate thousands of related signals in seconds. If the ETL pipeline consumed directly from the source APIs, a spike would either overwhelm the processing logic or require the pipeline to provision for peak capacity at all times. Kafka absorbs the burst into a persistent, ordered log. The ETL consumer reads at its own pace with no signal loss.',
      how: 'Three producers run as independent services: a Reddit producer polling subreddits every 90 seconds via PRAW, a Twitter filtered stream producer subscribing to real-time keyword events, and a Playwright-based web scraper with randomized delays. Every producer publishes JSON events to the raw_signals topic using a consistent schema that includes event_id (UUID), source, collected_at, raw_text, engagement_score, and metadata.',
    },
    {
      num: '02',
      title: 'Semantic ETL — Apache Airflow + Claude AI',
      why: 'Airflow was selected to orchestrate the enrichment pipeline because it provides observable, retryable, dependency-aware task execution. Raw signals need to be deduplicated, classified, tagged, and written to the database in a reliable sequence. A bare cron job or a simple loop provides none of that. Airflow\'s DAG model makes each transformation step independently testable and the overall pipeline visually inspectable.',
      how: 'The semantic_enrichment_dag runs every 5 minutes. It consumes from raw_signals, calls the Claude API (claude-sonnet-4-20250514) in parallel batches of 20, and writes enriched records to the enriched_signals PostgreSQL table. The LLM is prompted to return a structured JSON response with five fields: category, confidence, topic_tags, sentiment, and urgency. Claude was chosen over fine-tuned classifiers because it generalises to arbitrary topic domains without retraining — the system can track a new trend cluster (e.g., a regulatory change or an unexpected competitor move) the moment signals for it begin appearing, with no model update required.',
    },
    {
      num: '03',
      title: 'Predictive Layer — Market Pressure Index',
      why: 'The MPI was designed as a composite score rather than a single metric because no single dimension (volume alone, sentiment alone) is a reliable proxy for genuine market pressure. High volume with neutral sentiment may be noise. A modest volume spike with strongly positive sentiment and increasing velocity is a genuine opportunity. Combining three normalized dimensions — volume, velocity, sentiment — with tunable weights produces a score that is both interpretable and calibratable.',
      how: 'The formula is computed over a configurable rolling window (default 60 minutes) for each topic cluster. Volume score normalizes signal count against the cluster\'s baseline average. Velocity score compares the most recent 15-minute bucket against the preceding 15-minute bucket. Sentiment score is the proportion of signals classified as positive. Weights (0.40 / 0.35 / 0.25) are externalized as configuration — marketing teams can increase velocity weight during fast-moving events or increase sentiment weight for brand-sensitive categories without a code deploy.',
    },
    {
      num: '04',
      title: 'Storage Layer — PostgreSQL + Redis',
      why: 'PostgreSQL was chosen over a document store or a time-series database because the data model is relational: signals reference topic clusters, golden records reference signals, API keys reference users. SQL joins and window functions are the natural primitive for MPI calculation. Redis was added as a hot-path cache for the WebSocket endpoint — computing the full MPI grid on every client connection is expensive at scale; caching the result with a 60-second TTL collapses N concurrent client computations to one.',
      how: 'The schema uses two primary tables: enriched_signals (one row per classified signal, with topic_tags as a PostgreSQL TEXT[] array for efficient group-by) and golden_records (one row per triggered segment with audience_proxy as JSONB). Alembic manages all migrations; no ALTER TABLE commands are executed manually. The MPI grid SQL uses date_trunc with a modulo operation to bucket timestamps into 5-minute slots entirely within the database engine — no in-application aggregation loop is required.',
    },
    {
      num: '05',
      title: 'API Layer — FastAPI',
      why: 'FastAPI was selected for three reasons: native async support (required for the WebSocket push loop), automatic OpenAPI documentation generation, and Pydantic-based request/response validation. The WebSocket endpoint must hold thousands of concurrent connections without blocking — an ASGI framework running under uvicorn provides that. Synchronous DB operations are offloaded to a thread pool via asyncio.to_thread, keeping the event loop free.',
      how: 'Authentication uses short-lived JWTs (30-minute expiry, HS256) for browser sessions and bcrypt-hashed API keys with prefix-based lookup for programmatic access. Both token types are accepted in the same Authorization: Bearer header. Scope enforcement (read:signals, read:segments, write:alerts) prevents unauthorized access to write endpoints. The WebSocket closes with code 4001 on invalid tokens rather than sending an error message, preventing token leakage.',
    },
    {
      num: '06',
      title: 'Visualization Layer — React + Recharts',
      why: 'The dashboard is a single-page React application served by Vite. React was chosen because the UI has significant derived state (the MPI grid drives the heat map, the gauge widgets, and the KPI counters simultaneously) that benefits from the unidirectional data flow model. All state derives from two sources: the WebSocket stream (heatmap data) and a 60-second REST poll (golden records). This separation ensures that losing the WebSocket connection does not affect the segment sidebar.',
      how: 'The heat map encodes MPI score as color intensity on a perceptually uniform scale. Each cell also encodes velocity through opacity: higher-velocity cells appear brighter. The MPI gauge widgets use SVG arc paths (semicircle geometry with sweep-flag=1 for the clockwise top arc) to render per-cluster pressure scores. The WebSocket reconnects with exponential backoff (2 s → 4 s → 8 s … max 30 s) and authenticates via a JWT query parameter since the browser WebSocket API does not support custom headers.',
    },
  ];

  const decisions = [
    { decision: 'Kafka over direct API polling', why: 'Spike absorption — social traffic is bursty; the ETL pipeline cannot provision for peak load without Kafka as a buffer.' },
    { decision: 'Claude AI over fine-tuned classifiers', why: 'Zero retraining — the system adapts to new topic clusters (new products, regulations, events) without model updates.' },
    { decision: 'Composite MPI score over single metric', why: 'No single dimension is reliable alone; the weighted composite is interpretable, auditable, and independently tunable.' },
    { decision: 'MPI weights in config, not code', why: 'Marketing teams adjust sensitivity to match campaign cycles without engineering involvement or a deployment.' },
    { decision: 'PostgreSQL TEXT[] for topic_tags', why: 'Enables native array indexing and GROUP BY in the MPI SQL — no separate join table needed for a 1:N tags relationship.' },
    { decision: 'WebSocket push over REST polling', why: 'The dashboard is an operational screen; a 60-second poll would cause visible stale data and unnecessary server load with many clients.' },
    { decision: 'JWT + API key dual-auth in same header', why: 'Browser sessions use short-lived JWTs; integrations use long-lived API keys. The same middleware handles both transparently.' },
    { decision: 'Alembic for all schema changes', why: 'Reproducible, reversible migrations. Manual ALTER TABLE leaves the DB in an undocumented state that breaks new environment setup.' },
  ];

  return (
    <div style={ev.root}>

      {/* Overview */}
      <section style={ev.section}>
        <Eyebrow>System Overview</Eyebrow>
        <SectionTitle>A four-layer event-driven pipeline from data collection to decision support</SectionTitle>
        <p style={ev.body}>
          The system is architected as a linear pipeline with four conceptually distinct stages: ingestion,
          enrichment, prediction, and visualization. Each stage is independently scalable and communicates
          with adjacent stages through well-defined interfaces (Kafka topics and PostgreSQL tables) rather
          than direct function calls. This means any stage can be replaced, re-implemented, or horizontally
          scaled without affecting the others.
        </p>
        <p style={ev.body}>
          The pipeline is event-driven at the ingestion and enrichment layers (Kafka), and request-driven
          at the API and visualization layers (WebSocket + REST). This hybrid model allows the system to
          ingest continuously while serving the dashboard on-demand.
        </p>
        <div style={{ marginTop: 32, overflowX: 'auto' }}>
          <PipelineDiagram />
        </div>
      </section>

      {/* Layer-by-layer */}
      <section style={ev.section}>
        <Eyebrow>Layer Breakdown</Eyebrow>
        <SectionTitle>Engineering rationale for each pipeline stage</SectionTitle>
        <div style={{ marginTop: 24 }}>
          {layers.map(layer => (
            <div key={layer.num} style={ev.layerCard}>
              <div style={ev.layerNum}>{layer.num}</div>
              <div style={{ flex: 1 }}>
                <h3 style={ev.layerTitle}>{layer.title}</h3>
                <p style={ev.layerWhy}><strong style={{ color: '#C8982A' }}>Why this tool:</strong> {layer.why}</p>
                <p style={ev.layerHow}><strong style={{ color: '#003366' }}>How it works:</strong> {layer.how}</p>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* MPI Formula */}
      <section style={ev.section}>
        <Eyebrow>MPI Scoring</Eyebrow>
        <SectionTitle>How market pressure is quantified</SectionTitle>
        <p style={ev.body}>
          The Market Pressure Index is computed every 5 minutes over a configurable rolling window
          (default 60 minutes) per topic cluster. Three normalized components are combined using
          a weighted sum. All weights are externalized to environment variables — no code change is
          required to adjust sensitivity.
        </p>
        <div style={{ marginTop: 24, backgroundColor: '#ffffff', borderRadius: 12, padding: '24px 28px', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' }}>
          <MpiFormulaDiagram />
        </div>
        <p style={{ ...ev.body, marginTop: 16 }}>
          The 0.72 threshold for Golden Record generation was chosen empirically: below this value,
          signals represent moderate interest; above it, the combination of volume, velocity, and
          positive sentiment is consistent with a window of actionable market opportunity. This
          threshold is configurable via the <code style={ev.code}>MPI_THRESHOLD</code> environment variable.
        </p>
      </section>

      {/* Design decisions */}
      <section style={ev.section}>
        <Eyebrow>Design Decisions</Eyebrow>
        <SectionTitle>Key architectural choices and their justification</SectionTitle>
        <div style={{ marginTop: 24, backgroundColor: '#ffffff', borderRadius: 12, overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,51,102,0.08)' }}>
          <table style={ev.table}>
            <thead>
              <tr style={ev.thead}>
                <th style={ev.th}>Decision</th>
                <th style={ev.th}>Justification</th>
              </tr>
            </thead>
            <tbody>
              {decisions.map((d, i) => (
                <tr key={i} style={i % 2 === 0 ? ev.trEven : ev.trOdd}>
                  <td style={ev.tdDecision}>{d.decision}</td>
                  <td style={ev.tdWhy}>{d.why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* Tech stack */}
      <section style={ev.section}>
        <Eyebrow>Technology Stack</Eyebrow>
        <SectionTitle>Component versions and their roles</SectionTitle>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 14, marginTop: 24 }}>
          {[
            { name: 'Apache Kafka',     role: 'Message buffer',           detail: 'Ingestion decoupling, exactly-once semantics via event_id' },
            { name: 'Apache Airflow',   role: 'ETL orchestration',        detail: 'DAG-based scheduling with retries and task-level observability' },
            { name: 'Claude AI',        role: 'Signal classification',    detail: 'claude-sonnet-4-20250514 — zero-shot topic classification + structured JSON output' },
            { name: 'PostgreSQL 15',    role: 'Persistent storage',       detail: 'enriched_signals, golden_records, api_keys, alert_rules tables' },
            { name: 'Redis',            role: 'MPI response cache',       detail: '60-second TTL on computed MPI grids, hot-path acceleration' },
            { name: 'FastAPI',          role: 'API & WebSocket server',   detail: 'ASGI, async-native, Pydantic validation, JWT + API key auth' },
            { name: 'React + Recharts', role: 'Dashboard',                detail: 'WebSocket-driven heat map, SVG gauges, 60-second segment polling' },
            { name: 'Alembic',          role: 'Schema migrations',        detail: 'Versioned, reversible SQL migrations — no manual ALTER TABLE' },
            { name: 'Docker Compose',   role: 'Container orchestration',  detail: 'All services defined in a single Compose file with health checks' },
          ].map(t => (
            <div key={t.name} style={ev.techCard}>
              <div style={ev.techName}>{t.name}</div>
              <div style={ev.techRole}>{t.role}</div>
              <div style={ev.techDetail}>{t.detail}</div>
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

function Eyebrow({ children }) {
  return (
    <div style={shared.eyebrow}>
      <div style={shared.eyebrowLine} />
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

      {/* Page header */}
      <header style={p.header}>
        <div style={p.headerInner}>
          <Eyebrow>Documentation</Eyebrow>
          <h1 style={p.title}>
            Trend Arbitrage{' '}
            <em style={{ fontStyle: 'italic', color: 'var(--gold-light)' }}>&amp; Zero-Day Response</em>
          </h1>
          <p style={p.subtitle}>
            Select a perspective to explore how the platform works and the value it delivers.
          </p>

          {/* Tab switcher */}
          <div style={p.tabs}>
            <button
              style={{ ...p.tab, ...(view === 'business' ? p.tabActive : {}) }}
              onClick={() => setView('business')}
            >
              Business View
            </button>
            <button
              style={{ ...p.tab, ...(view === 'engineering' ? p.tabActive : {}) }}
              onClick={() => setView('engineering')}
            >
              Engineering View
            </button>
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
  eyebrow: {
    display: 'inline-flex', alignItems: 'center', gap: 8,
    fontSize: 9, fontFamily: 'var(--fb)', fontWeight: 500,
    letterSpacing: '4px', textTransform: 'uppercase',
    color: 'var(--gold-light)', marginBottom: 10,
  },
  eyebrowLine: { width: 24, height: 1, backgroundColor: 'var(--gold-light)', flexShrink: 0 },
  sectionTitle: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 22, fontWeight: 300,
    color: '#0a1628', margin: '0 0 4px', lineHeight: 1.25,
  },
};

const p = {
  page: { minHeight: '100vh', backgroundColor: 'var(--light)' },
  header: {
    backgroundColor: 'var(--primary)',
    backgroundImage: `linear-gradient(rgba(255,255,255,.025) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.025) 1px,transparent 1px)`,
    backgroundSize: '48px 48px',
    padding: '28px 48px 0',
  },
  headerInner: { maxWidth: 1200, margin: '0 auto' },
  title: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 28, fontWeight: 300,
    color: '#ffffff', margin: '0 0 8px', lineHeight: 1.1,
  },
  subtitle: {
    fontFamily: 'var(--fb)', fontSize: 12, color: 'rgba(255,255,255,0.5)',
    margin: '0 0 28px', lineHeight: 1.6,
  },
  tabs: { display: 'flex', gap: 4, borderBottom: '1px solid rgba(255,255,255,0.1)' },
  tab: {
    background: 'none', border: 'none', borderBottom: '2px solid transparent',
    cursor: 'pointer', padding: '10px 20px', marginBottom: -1,
    fontFamily: 'var(--fb)', fontSize: 11, fontWeight: 500,
    letterSpacing: '1.5px', textTransform: 'uppercase',
    color: 'rgba(255,255,255,0.4)', transition: 'color 0.15s',
  },
  tabActive: { color: 'var(--gold-light)', borderBottomColor: 'var(--gold-light)' },
  footer: {
    backgroundColor: 'var(--primary)', padding: '20px 48px',
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    fontFamily: 'var(--fb)', fontSize: 9, letterSpacing: '3px',
    textTransform: 'uppercase', color: 'rgba(255,255,255,0.4)',
  },
};

// Business view styles
const bv = {
  root: { maxWidth: 1200, margin: '0 auto', padding: '48px 48px 80px' },
  section: { marginBottom: 64 },
  body: {
    fontFamily: 'var(--fb)', fontSize: 14, color: '#475569',
    lineHeight: 1.75, margin: '12px 0 0',
  },
  stepNote: {
    fontFamily: 'var(--fb)', fontSize: 11, color: '#64748b',
    lineHeight: 1.6, margin: 0, textAlign: 'center',
  },
  card: {
    backgroundColor: '#ffffff', borderRadius: 12, overflow: 'hidden',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
  },
  cardAccent: { height: 3, backgroundColor: '#C8982A' },
  cardBody: { padding: '20px 22px 22px' },
  cardTitle: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 17, fontWeight: 300,
    color: '#0a1628', margin: '0 0 8px',
  },
  cardText: {
    fontFamily: 'var(--fb)', fontSize: 13, color: '#475569',
    lineHeight: 1.7, margin: 0,
  },
  integRow: {
    display: 'grid', gridTemplateColumns: '200px 1fr', gap: 20,
    padding: '16px 0', borderBottom: '1px solid #f1f5f9', alignItems: 'start',
  },
  integName: {
    fontFamily: 'var(--fb)', fontSize: 12, fontWeight: 700,
    color: '#003366', lineHeight: 1.4,
  },
  integDetail: {
    fontFamily: 'var(--fb)', fontSize: 13, color: '#475569', lineHeight: 1.65,
  },
  metricCard: {
    backgroundColor: '#ffffff', borderRadius: 12,
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)', overflow: 'hidden',
  },
  metricAccent: { height: 3, backgroundColor: '#003366' },
  metricBody: {
    display: 'flex', flexDirection: 'column', alignItems: 'center',
    padding: '20px 12px 18px',
  },
  metricValue: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 28, fontWeight: 300,
    color: '#003366', lineHeight: 1, marginBottom: 8,
  },
  metricLabel: {
    fontFamily: 'var(--fb)', fontSize: 11, color: '#64748b',
    textAlign: 'center', lineHeight: 1.5,
  },
};

// Engineering view styles
const ev = {
  root: { maxWidth: 1200, margin: '0 auto', padding: '48px 48px 80px' },
  section: { marginBottom: 64 },
  body: {
    fontFamily: 'var(--fb)', fontSize: 13.5, color: '#475569',
    lineHeight: 1.8, margin: '12px 0 0',
  },
  layerCard: {
    display: 'flex', gap: 24, padding: '24px 0',
    borderBottom: '1px solid #e2e8f0', alignItems: 'flex-start',
  },
  layerNum: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 32, fontWeight: 300,
    color: '#C8982A', lineHeight: 1, flexShrink: 0, width: 44, marginTop: 4,
  },
  layerTitle: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 17, fontWeight: 400,
    color: '#0a1628', margin: '0 0 10px',
  },
  layerWhy: {
    fontFamily: 'var(--fb)', fontSize: 13, color: '#475569',
    lineHeight: 1.75, margin: '0 0 8px',
  },
  layerHow: {
    fontFamily: 'var(--fb)', fontSize: 13, color: '#475569',
    lineHeight: 1.75, margin: 0,
  },
  code: {
    fontFamily: 'monospace', fontSize: 11.5,
    backgroundColor: '#f1f5f9', color: '#0a1628',
    padding: '1px 5px', borderRadius: 4,
  },
  table: { width: '100%', borderCollapse: 'collapse' },
  thead: { backgroundColor: '#003366' },
  th: {
    padding: '12px 18px', textAlign: 'left',
    fontFamily: 'var(--fb)', fontSize: 10, fontWeight: 600,
    letterSpacing: '2px', textTransform: 'uppercase', color: 'var(--gold-light)',
  },
  trEven: { backgroundColor: '#ffffff' },
  trOdd: { backgroundColor: '#f8fafc' },
  tdDecision: {
    padding: '12px 18px', fontFamily: 'var(--fb)', fontSize: 12,
    fontWeight: 600, color: '#003366', verticalAlign: 'top',
    width: '36%', borderBottom: '1px solid #f1f5f9',
  },
  tdWhy: {
    padding: '12px 18px', fontFamily: 'var(--fb)', fontSize: 12.5,
    color: '#475569', lineHeight: 1.65, borderBottom: '1px solid #f1f5f9',
  },
  techCard: {
    backgroundColor: '#ffffff', borderRadius: 10,
    boxShadow: '0 1px 3px rgba(0,51,102,0.07)',
    padding: '18px 18px 16px',
    borderTop: '3px solid #C8982A',
  },
  techName: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: 15, fontWeight: 400,
    color: '#003366', marginBottom: 3,
  },
  techRole: {
    fontFamily: 'var(--fb)', fontSize: 10, fontWeight: 600,
    letterSpacing: '1.5px', textTransform: 'uppercase',
    color: '#C8982A', marginBottom: 8,
  },
  techDetail: {
    fontFamily: 'var(--fb)', fontSize: 11.5, color: '#64748b', lineHeight: 1.6,
  },
};
