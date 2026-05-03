import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { HeatMap } from './components/HeatMap';
import { TrendCard } from './components/TrendCard';
import { MpiGauge } from './components/MpiGauge';
import { PerformancePanel } from './components/PerformancePanel';
import LoginPage from './pages/LoginPage';

export default function App() {
  const [authToken, setAuthToken] = useState(
    () => sessionStorage.getItem('ta_token') || null
  );
  const [heatmapData, setHeatmapData] = useState(null);
  const [segments, setSegments] = useState([]);
  const [wsStatus, setWsStatus] = useState('connecting');

  const wsRef = useRef(null);
  const reconnectRef = useRef(null);
  const delayRef = useRef(2000);

  function handleLogin(token) {
    setAuthToken(token);
  }

  function handleLogout() {
    sessionStorage.removeItem('ta_token');
    setAuthToken(null);
    wsRef.current?.close();
  }

  // Authenticated fetch — clears token and forces re-login on 401
  const authFetch = useCallback(async (url, opts = {}) => {
    const res = await fetch(url, {
      ...opts,
      headers: {
        ...(opts.headers || {}),
        Authorization: `Bearer ${authToken}`,
      },
    });
    if (res.status === 401) {
      handleLogout();
      return null;
    }
    return res;
  }, [authToken]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!authToken) {
    return <LoginPage onLogin={handleLogin} />;
  }

  // WS URL includes the JWT as a query param (browser WS API has no custom headers)
  const wsUrl = `${window.location.protocol === 'https:' ? 'wss:' : 'ws:'}//${window.location.host}/ws/heatmap?token=${encodeURIComponent(authToken)}`;

  // ── WebSocket with exponential-backoff reconnect ──────────────────────────

  const connectWs = useCallback(() => {
    setWsStatus('connecting');
    const ws = new WebSocket(wsUrl);

    ws.onopen = () => {
      setWsStatus('open');
      delayRef.current = 2000;
    };

    ws.onmessage = (e) => {
      try {
        setHeatmapData(JSON.parse(e.data));
      } catch (err) {
        console.error('WS parse error:', err);
      }
    };

    ws.onclose = (ev) => {
      // 4001/4003 = auth failure — don't retry, force re-login
      if (ev.code === 4001 || ev.code === 4003) {
        handleLogout();
        return;
      }
      setWsStatus('closed');
      reconnectRef.current = setTimeout(() => {
        delayRef.current = Math.min(delayRef.current * 2, 30000);
        connectWs();
      }, delayRef.current);
    };

    ws.onerror = () => ws.close();
    wsRef.current = ws;
  }, [wsUrl]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    connectWs();
    return () => {
      clearTimeout(reconnectRef.current);
      wsRef.current?.close();
    };
  }, [connectWs]);

  // ── REST polling for Golden Records (60s interval) ────────────────────────

  const fetchSegments = useCallback(async () => {
    try {
      const res = await authFetch('/segments');
      if (res && res.ok) {
        const data = await res.json();
        setSegments(data.records ?? []);
      }
    } catch (err) {
      console.error('Failed to fetch segments:', err);
    }
  }, [authFetch]);

  useEffect(() => {
    fetchSegments();
    const id = setInterval(fetchSegments, 60_000);
    return () => clearInterval(id);
  }, [fetchSegments]);

  // ── Derived KPIs ──────────────────────────────────────────────────────────

  const kpis = useMemo(() => {
    const cells = heatmapData?.cells ?? [];
    const totalSignals = cells.reduce((s, c) => s + c.signal_count, 0);
    const topMpi = cells.length ? Math.max(...cells.map((c) => c.score)) : 0;
    const activeClusters = heatmapData?.topic_clusters?.length ?? 0;
    return { totalSignals, topMpi, activeClusters, activeSegments: segments.length };
  }, [heatmapData, segments]);

  // Per-cluster max score across time buckets for gauge widgets
  const clusterGauges = useMemo(() => {
    const cells = heatmapData?.cells ?? [];
    const map = {};
    cells.forEach(({ topic_cluster, score, signal_count }) => {
      if (!map[topic_cluster] || score > map[topic_cluster].score) {
        map[topic_cluster] = { score, signal_count };
      }
    });
    return Object.entries(map)
      .map(([cluster, { score, signal_count }]) => ({ cluster, score, signal_count }))
      .sort((a, b) => b.score - a.score)
      .slice(0, 6);
  }, [heatmapData]);

  const lastUpdated = heatmapData?.computed_at
    ? new Date(heatmapData.computed_at).toLocaleTimeString('en-US', { hour12: false })
    : '—';

  const wsColor =
    wsStatus === 'open' ? '#27B97C' : wsStatus === 'connecting' ? '#F07020' : '#E03448';
  const wsLabel =
    wsStatus === 'open' ? 'Live' : wsStatus === 'connecting' ? 'Connecting…' : 'Reconnecting…';

  // ── Render ────────────────────────────────────────────────────────────────

  return (
    <div style={{ minHeight: '100vh', backgroundColor: 'var(--light)' }}>

      {/* ── Navigation ── */}
      <nav style={s.nav}>
        <span>
          <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, color: '#ffffff' }}>O</span>
          <em style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, fontStyle: 'italic', color: 'var(--gold-light)' }}>PB</em>
        </span>
        <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: wsColor, display: 'inline-block' }} />
            <span style={s.navTitle}>TREND ARBITRAGE · INTELLIGENCE</span>
          </div>
          <button onClick={handleLogout} style={s.logoutBtn} title="Sign out">
            Sign out
          </button>
        </div>
      </nav>

      {/* ── Hero ── */}
      <header style={s.hero}>
        <div style={s.heroInner}>
          <h1 style={s.heroTitle}>
            Real-time market{' '}
            <em style={{ fontStyle: 'italic', color: 'var(--gold-light)' }}>pressure.</em>
          </h1>
          <p style={s.heroSub}>
            Opportunity heat map · {heatmapData?.window_minutes ?? 60}-minute rolling window
            · Updated {lastUpdated}
          </p>
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '4px 12px',
              borderRadius: '20px',
              fontSize: '10px',
              fontFamily: 'var(--fb)',
              fontWeight: 500,
              backgroundColor: wsColor + '22',
              color: wsColor,
              border: `1px solid ${wsColor}44`,
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: wsColor }} />
            {wsLabel}
          </span>
        </div>
      </header>

      {/* ── KPI Row ── */}
      <section style={s.kpiSection}>
        {[
          { label: 'Signals in Window',    value: kpis.totalSignals.toLocaleString(), sub: 'opportunity + threat' },
          { label: 'Active Topic Clusters', value: kpis.activeClusters,               sub: 'last 60 min' },
          { label: 'Peak MPI Score',        value: kpis.topMpi.toFixed(3),            sub: 'across all clusters' },
          { label: 'Active Segments',       value: kpis.activeSegments,               sub: 'golden records live' },
        ].map(({ label, value, sub }) => (
          <div key={label} style={s.kpiCard}>
            <div style={s.kpiAccent} />
            <div style={s.kpiBody}>
              <span style={s.kpiValue}>{value}</span>
              <span style={s.kpiLabel}>{label}</span>
              <span style={s.kpiSub}>{sub}</span>
            </div>
          </div>
        ))}
      </section>

      {/* ── Main content ── */}
      <main style={s.main}>

        {/* Left: HeatMap + Gauges */}
        <div style={s.leftCol}>

          <div style={s.sectionHead}>
            <div style={s.eyebrow}>
              <div style={s.eyebrowLine} />
              Signal Intensity Map
            </div>
            <p style={s.sectionDesc}>MPI heat grid — 5-minute resolution, last 60 minutes.</p>
          </div>

          <div style={s.card}>
            <HeatMap
              cells={heatmapData?.cells ?? []}
              topic_clusters={heatmapData?.topic_clusters ?? []}
              time_buckets={heatmapData?.time_buckets ?? []}
            />
          </div>

          {clusterGauges.length > 0 && (
            <>
              <div style={s.divider} />

              <div style={s.sectionHead}>
                <div style={s.eyebrow}>
                  <div style={s.eyebrowLine} />
                  Per-Cluster Pressure
                </div>
                <p style={s.sectionDesc}>Peak MPI score per topic cluster across the window.</p>
              </div>

              <div style={s.gaugeRow}>
                {clusterGauges.map(({ cluster, score, signal_count }) => (
                  <MpiGauge
                    key={cluster}
                    topic_cluster={cluster}
                    score={score}
                    signal_count={signal_count}
                  />
                ))}
              </div>
            </>
          )}
        </div>

        {/* Right sidebar: Active Segments */}
        <div style={s.sidebar}>
          <div style={s.sectionHead}>
            <div style={s.eyebrow}>
              <div style={s.eyebrowLine} />
              Active Segments
            </div>
            <p style={s.sectionDesc}>Top 5 golden records — ordered by MPI score.</p>
          </div>

          {segments.length === 0 ? (
            <div style={s.emptySegments}>
              <p style={{ fontFamily: 'var(--fb)', fontSize: '13px', color: 'var(--mid)', textAlign: 'center', lineHeight: 1.7, margin: 0 }}>
                No active segments.<br />
                Generated automatically when MPI ≥ 0.72.
              </p>
            </div>
          ) : (
            segments.slice(0, 5).map((rec) => (
              <TrendCard key={rec.id} record={rec} />
            ))
          )}

          <PerformancePanel authFetch={authFetch} />
        </div>
      </main>

      {/* ── Footer ── */}
      <footer style={s.footer}>
        <span>OPB · OCTAVIO PÉREZ BRAVO · TREND ARBITRAGE & ZERO-DAY RESPONSE</span>
        <span>
          {new Date().toLocaleDateString('en-US', { year: 'numeric', month: 'long' }).toUpperCase()}
        </span>
      </footer>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  nav: {
    position: 'sticky',
    top: 0,
    zIndex: 100,
    height: '52px',
    backgroundColor: 'rgba(0,51,102,0.97)',
    backdropFilter: 'blur(12px)',
    WebkitBackdropFilter: 'blur(12px)',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 40px',
  },
  navTitle: {
    fontFamily: 'var(--fb)',
    fontSize: '9px',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: 'rgba(255,255,255,0.4)',
  },
  logoutBtn: {
    background: 'none',
    border: '1px solid rgba(255,255,255,0.2)',
    borderRadius: '6px',
    color: 'rgba(255,255,255,0.5)',
    cursor: 'pointer',
    fontFamily: 'var(--fb)',
    fontSize: '9px',
    letterSpacing: '2px',
    textTransform: 'uppercase',
    padding: '5px 10px',
  },
  hero: {
    backgroundColor: 'var(--primary)',
    backgroundImage: `
      linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)
    `,
    backgroundSize: '48px 48px',
    padding: '64px 48px',
  },
  heroInner: {
    maxWidth: '1300px',
    margin: '0 auto',
  },
  heroTitle: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '48px',
    fontWeight: 300,
    color: 'var(--white)',
    margin: '0 0 12px 0',
    lineHeight: 1.1,
  },
  heroSub: {
    fontFamily: 'var(--fb)',
    fontSize: '15px',
    color: 'rgba(255,255,255,0.6)',
    margin: '0 0 16px 0',
    lineHeight: 1.7,
  },
  kpiSection: {
    display: 'grid',
    gridTemplateColumns: 'repeat(4, 1fr)',
    gap: '16px',
    padding: '32px 48px',
    maxWidth: '1300px',
    margin: '0 auto',
    width: '100%',
    boxSizing: 'border-box',
  },
  kpiCard: {
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    overflow: 'hidden',
  },
  kpiAccent: {
    height: '3px',
    backgroundColor: 'var(--gold)',
  },
  kpiBody: {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '24px 16px 20px',
  },
  kpiValue: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '32px',
    fontWeight: 300,
    color: 'var(--dark)',
    lineHeight: 1,
    marginBottom: '8px',
  },
  kpiLabel: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    fontWeight: 500,
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: 'var(--mid)',
    textAlign: 'center',
    marginBottom: '4px',
  },
  kpiSub: {
    fontFamily: 'var(--fb)',
    fontSize: '11px',
    color: 'var(--mid)',
    textAlign: 'center',
  },
  main: {
    display: 'grid',
    gridTemplateColumns: '1fr 340px',
    gap: '24px',
    padding: '0 48px 64px',
    maxWidth: '1300px',
    margin: '0 auto',
    width: '100%',
    boxSizing: 'border-box',
  },
  leftCol: { minWidth: 0 },
  sidebar: { minWidth: 0 },
  sectionHead: {
    marginTop: '32px',
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
    marginBottom: '6px',
  },
  eyebrowLine: {
    width: '24px',
    height: '1px',
    backgroundColor: 'var(--gold)',
    flexShrink: 0,
  },
  sectionDesc: {
    fontFamily: 'var(--fb)',
    fontSize: '13px',
    color: 'var(--mid)',
    margin: 0,
    lineHeight: 1.5,
  },
  card: {
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    padding: '28px',
  },
  divider: {
    height: '1px',
    backgroundColor: 'var(--primary-10)',
    margin: '28px 0',
  },
  gaugeRow: {
    display: 'flex',
    flexWrap: 'wrap',
    gap: '16px',
  },
  emptySegments: {
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    padding: '40px 24px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    border: '1px dashed var(--primary-30)',
  },
  footer: {
    backgroundColor: 'var(--primary)',
    padding: '20px 48px',
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
    fontFamily: 'var(--fb)',
    fontSize: '9px',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: 'rgba(255,255,255,0.4)',
  },
};
