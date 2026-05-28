import React, { useState, useEffect, useCallback } from 'react';

const ALL_SOURCES = ['reddit', 'twitter', 'news', 'linkedin', 'rss', 'scraper'];
const URGENCY_OPTS = ['low', 'medium', 'high'];

const SOURCE_COLOR = {
  reddit:   { bg: '#fff0e6', text: '#c2410c', border: '#fdba74' },
  twitter:  { bg: '#eff6ff', text: '#1d4ed8', border: '#93c5fd' },
  news:     { bg: '#f8fafc', text: '#334155', border: '#cbd5e1' },
  linkedin: { bg: '#eff6ff', text: '#1e40af', border: '#93c5fd' },
  rss:      { bg: '#fff7ed', text: '#c2410c', border: '#fdba74' },
  scraper:  { bg: '#faf5ff', text: '#7e22ce', border: '#d8b4fe' },
};

const URGENCY_COLOR = {
  high:   { bg: '#fef2f2', text: '#dc2626', border: '#fecaca' },
  medium: { bg: '#fff7ed', text: '#ea580c', border: '#fed7aa' },
  low:    { bg: '#f0fdf4', text: '#16a34a', border: '#bbf7d0' },
};

// ── Subcomponents ─────────────────────────────────────────────────────────────

function SourceChip({ source }) {
  const c = SOURCE_COLOR[source] || { bg: '#f8fafc', text: '#475569', border: '#e2e8f0' };
  return (
    <span style={{
      fontSize: '9px', fontFamily: 'var(--fb)', fontWeight: 600,
      letterSpacing: '1px', textTransform: 'uppercase',
      padding: '2px 7px', borderRadius: '10px',
      backgroundColor: c.bg, color: c.text, border: `1px solid ${c.border}`,
    }}>
      {source}
    </span>
  );
}

function UrgencyBadge({ level }) {
  const c = URGENCY_COLOR[level] || URGENCY_COLOR.low;
  return (
    <span style={{
      fontSize: '9px', fontFamily: 'var(--fb)', fontWeight: 600,
      letterSpacing: '1.5px', textTransform: 'uppercase',
      padding: '2px 7px', borderRadius: '10px',
      backgroundColor: c.bg, color: c.text, border: `1px solid ${c.border}`,
    }}>
      {level}
    </span>
  );
}

function MpiBar({ score }) {
  const color = score >= 0.72 ? '#E03448' : score >= 0.50 ? '#F07020' : '#27B97C';
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
      <div style={{ flex: 1, height: '5px', backgroundColor: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
        <div style={{ width: `${Math.round(score * 100)}%`, height: '100%', backgroundColor: color, borderRadius: '3px' }} />
      </div>
      <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '13px', fontWeight: 300, color, minWidth: '34px', textAlign: 'right' }}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}

// ── Cluster form (used for both add and edit) ─────────────────────────────────

function ClusterForm({ initial, onSave, onCancel, saving }) {
  const [form, setForm] = useState(initial);

  function set(key, val) { setForm(f => ({ ...f, [key]: val })); }

  function toggleSource(src) {
    set('sources', form.sources.includes(src)
      ? form.sources.filter(s => s !== src)
      : [...form.sources, src]);
  }

  return (
    <div style={fs.form}>
      <div style={fs.grid2}>
        <div style={fs.field}>
          <label style={fs.label}>Cluster slug *</label>
          <input
            style={fs.input}
            value={form.name}
            onChange={e => set('name', e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ''))}
            placeholder="e.g. quantum-computing"
            disabled={initial.id}
          />
          <span style={fs.hint}>Lowercase, hyphens only. Cannot be changed after creation.</span>
        </div>
        <div style={fs.field}>
          <label style={fs.label}>Display name *</label>
          <input
            style={fs.input}
            value={form.display_name}
            onChange={e => set('display_name', e.target.value)}
            placeholder="e.g. Quantum Computing"
          />
        </div>
      </div>

      <div style={fs.field}>
        <label style={fs.label}>Data sources *</label>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px', marginTop: '4px' }}>
          {ALL_SOURCES.map(src => {
            const active = form.sources.includes(src);
            const c = SOURCE_COLOR[src];
            return (
              <button
                key={src}
                type="button"
                onClick={() => toggleSource(src)}
                style={{
                  padding: '4px 12px', borderRadius: '12px', cursor: 'pointer',
                  fontFamily: 'var(--fb)', fontSize: '10px', fontWeight: 600,
                  letterSpacing: '1px', textTransform: 'uppercase',
                  border: `1px solid ${active ? c.border : '#e2e8f0'}`,
                  backgroundColor: active ? c.bg : '#f8fafc',
                  color: active ? c.text : '#94a3b8',
                  transition: 'all 0.15s',
                }}
              >
                {src}
              </button>
            );
          })}
        </div>
      </div>

      <div style={fs.grid3}>
        <div style={fs.field}>
          <label style={fs.label}>Urgency</label>
          <select style={fs.select} value={form.urgency} onChange={e => set('urgency', e.target.value)}>
            {URGENCY_OPTS.map(u => <option key={u} value={u}>{u.charAt(0).toUpperCase() + u.slice(1)}</option>)}
          </select>
        </div>
        <div style={fs.field}>
          <label style={fs.label}>Signal count (per seed) — {form.signal_count}</label>
          <input
            type="range" min={5} max={200} step={1}
            value={form.signal_count}
            onChange={e => set('signal_count', parseInt(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--gold)', marginTop: '8px' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={fs.hint}>5</span><span style={fs.hint}>200</span>
          </div>
        </div>
        <div style={fs.field}>
          <label style={fs.label}>MPI target — {form.mpi_score.toFixed(2)}</label>
          <input
            type="range" min={0} max={1} step={0.01}
            value={form.mpi_score}
            onChange={e => set('mpi_score', parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: form.mpi_score >= 0.72 ? '#E03448' : '#27B97C', marginTop: '8px' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between' }}>
            <span style={fs.hint}>0.00</span>
            <span style={{ ...fs.hint, color: '#E03448' }}>threshold 0.72</span>
            <span style={fs.hint}>1.00</span>
          </div>
        </div>
      </div>

      <div style={fs.field}>
        <label style={fs.label}>Positive sentiment bias — {Math.round(form.positive_ratio * 100)}%</label>
        <span style={fs.hint}>Controls the opportunity / threat / noise split in seeded signals.</span>
        <input
          type="range" min={0} max={1} step={0.05}
          value={form.positive_ratio}
          onChange={e => set('positive_ratio', parseFloat(e.target.value))}
          style={{ width: '100%', accentColor: 'var(--primary)', marginTop: '6px' }}
        />
        <div style={{ display: 'flex', justifyContent: 'space-between' }}>
          <span style={fs.hint}>0% (all threat)</span>
          <span style={fs.hint}>100% (all opportunity)</span>
        </div>
      </div>

      <div style={fs.field}>
        <label style={fs.label}>Sample signal texts <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>(optional — one per line)</span></label>
        <textarea
          style={{ ...fs.input, height: '100px', resize: 'vertical', paddingTop: '10px', lineHeight: 1.5 }}
          value={(form.sample_texts || []).join('\n')}
          onChange={e => set('sample_texts', e.target.value.split('\n').map(l => l.trim()).filter(Boolean))}
          placeholder={`Market signal for ${form.name || 'this cluster'}…\nAnother example signal…`}
        />
        <span style={fs.hint}>Used as realistic signal text when seeding. Leave blank for generic placeholders.</span>
      </div>

      <div style={{ display: 'flex', gap: '10px', marginTop: '4px' }}>
        <button
          style={{ ...fs.btn, ...fs.btnPrimary, ...(saving ? { opacity: 0.6, cursor: 'not-allowed' } : {}) }}
          onClick={() => onSave(form)}
          disabled={saving || !form.name || !form.display_name || !form.sources.length}
        >
          {saving ? 'Saving…' : 'Save cluster'}
        </button>
        <button style={{ ...fs.btn, ...fs.btnGhost }} onClick={onCancel} disabled={saving}>
          Cancel
        </button>
      </div>
    </div>
  );
}

const BLANK_CLUSTER = {
  name: '', display_name: '', sources: [], urgency: 'medium',
  positive_ratio: 0.65, signal_count: 25, mpi_score: 0.70, sample_texts: [],
};

// ── Main page ─────────────────────────────────────────────────────────────────

export default function PersonalizePage({ authFetch }) {
  const [clusters, setClusters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [editingName, setEditingName] = useState(null);
  const [addingNew, setAddingNew] = useState(false);
  const [saving, setSaving] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [deletingName, setDeletingName] = useState(null);

  const fetchClusters = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const res = await authFetch('/clusters');
      if (!res || !res.ok) { setError('Failed to load clusters'); return; }
      const data = await res.json();
      setClusters(data.clusters);
    } catch { setError('Network error'); }
    finally { setLoading(false); }
  }, [authFetch]);

  useEffect(() => { fetchClusters(); }, [fetchClusters]);

  async function handleSaveNew(form) {
    setSaving(true);
    try {
      const res = await authFetch('/clusters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res || !res.ok) {
        const err = res ? await res.json().catch(() => ({})) : {};
        setError(err.detail || 'Failed to create cluster');
        return;
      }
      setAddingNew(false);
      await fetchClusters();
    } finally { setSaving(false); }
  }

  async function handleSaveEdit(name, form) {
    setSaving(true);
    try {
      const res = await authFetch(`/clusters/${name}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (!res || !res.ok) {
        const err = res ? await res.json().catch(() => ({})) : {};
        setError(err.detail || 'Failed to update cluster');
        return;
      }
      setEditingName(null);
      await fetchClusters();
    } finally { setSaving(false); }
  }

  async function handleDelete(name) {
    if (deletingName !== name) { setDeletingName(name); return; }
    setDeletingName(null);
    const res = await authFetch(`/clusters/${name}`, { method: 'DELETE' });
    if (res && (res.ok || res.status === 204)) await fetchClusters();
    else setError('Failed to delete cluster');
  }

  async function handleReset() {
    setResetting(true);
    try {
      const res = await authFetch('/clusters/reset', { method: 'POST' });
      if (!res || !res.ok) { setError('Reset failed'); return; }
      await fetchClusters();
    } finally { setResetting(false); }
  }

  return (
    <div style={s.page}>

      {/* ── Header ── */}
      <header style={s.header}>
        <div style={s.headerInner}>
          <div style={s.eyebrow}><div style={s.eyebrowLine} />Signal Configuration</div>
          <h1 style={s.title}>Personalize <em style={{ fontStyle: 'italic', color: 'var(--gold-light)' }}>Clusters</em></h1>
          <p style={s.subtitle}>
            Define the topic clusters the system monitors. These settings drive which signals are
            captured and what synthetic data is generated when you seed the demo.
          </p>
        </div>
      </header>

      <div style={s.body}>

        {/* ── Action bar ── */}
        <div style={s.actionBar}>
          <button
            style={{ ...s.btn, ...s.btnPrimary }}
            onClick={() => { setAddingNew(true); setEditingName(null); setError(null); }}
            disabled={addingNew}
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
            </svg>
            Add Cluster
          </button>
          <button
            style={{ ...s.btn, ...s.btnGhost, ...(resetting ? { opacity: 0.6, cursor: 'not-allowed' } : {}) }}
            onClick={handleReset}
            disabled={resetting}
          >
            {resetting ? 'Resetting…' : 'Reset to Defaults'}
          </button>
          <span style={s.clusterCount}>
            {loading ? '—' : clusters.length} cluster{clusters.length !== 1 ? 's' : ''} configured
          </span>
        </div>

        {error && (
          <div style={s.errorBox}>
            <span style={s.errorText}>{error}</span>
            <button onClick={() => setError(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#c0392b', fontSize: '14px', padding: '0 4px' }}>✕</button>
          </div>
        )}

        {/* ── Add new form ── */}
        {addingNew && (
          <div style={s.addCard}>
            <div style={{ ...s.cardAccent, backgroundColor: '#27B97C' }} />
            <div style={s.cardBody}>
              <div style={s.cardTitle}>New Cluster</div>
              <ClusterForm
                initial={BLANK_CLUSTER}
                onSave={handleSaveNew}
                onCancel={() => setAddingNew(false)}
                saving={saving}
              />
            </div>
          </div>
        )}

        {/* ── Cluster grid ── */}
        {loading ? (
          <div style={s.emptyState}>
            <span style={{ fontFamily: 'var(--fb)', fontSize: '13px', color: 'var(--mid)' }}>Loading clusters…</span>
          </div>
        ) : clusters.length === 0 && !addingNew ? (
          <div style={s.emptyState}>
            <p style={{ fontFamily: 'var(--fb)', fontSize: '13px', color: 'var(--mid)', textAlign: 'center', lineHeight: 1.7, margin: 0 }}>
              No clusters configured.<br />
              <button onClick={handleReset} style={{ color: 'var(--gold)', background: 'none', border: 'none', cursor: 'pointer', fontFamily: 'var(--fb)', fontSize: '13px', textDecoration: 'underline' }}>
                Load defaults
              </button>{' '}or add a cluster above.
            </p>
          </div>
        ) : (
          <div style={s.grid}>
            {clusters.map(cluster => (
              <div key={cluster.name} style={s.card}>
                <div style={{ ...s.cardAccent, backgroundColor: cluster.mpi_score >= 0.72 ? '#E03448' : '#64748b' }} />
                <div style={s.cardBody}>

                  {editingName === cluster.name ? (
                    <>
                      <div style={s.cardTitle}>{cluster.display_name}</div>
                      <ClusterForm
                        initial={cluster}
                        onSave={form => handleSaveEdit(cluster.name, form)}
                        onCancel={() => setEditingName(null)}
                        saving={saving}
                      />
                    </>
                  ) : (
                    <>
                      {/* View mode */}
                      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '10px' }}>
                        <div>
                          <div style={s.cardTitle}>{cluster.display_name}</div>
                          <code style={s.slug}>{cluster.name}</code>
                        </div>
                        <UrgencyBadge level={cluster.urgency} />
                      </div>

                      <div style={{ marginBottom: '12px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
                          <span style={s.metaLabel}>MPI target</span>
                          {cluster.mpi_score >= 0.72 && (
                            <span style={{ fontFamily: 'var(--fb)', fontSize: '9px', color: '#E03448', letterSpacing: '1px' }}>GOLDEN RECORD</span>
                          )}
                        </div>
                        <MpiBar score={cluster.mpi_score} />
                      </div>

                      <div style={s.statRow}>
                        <div style={s.stat}>
                          <span style={s.statValue}>{cluster.signal_count}</span>
                          <span style={s.statLabel}>signals / seed</span>
                        </div>
                        <div style={s.stat}>
                          <span style={s.statValue}>{Math.round(cluster.positive_ratio * 100)}%</span>
                          <span style={s.statLabel}>positive bias</span>
                        </div>
                      </div>

                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px', marginBottom: '16px' }}>
                        {cluster.sources.map(src => <SourceChip key={src} source={src} />)}
                      </div>

                      <div style={{ display: 'flex', gap: '8px' }}>
                        <button
                          style={{ ...s.btn, ...s.btnSmall, ...s.btnGhost, flex: 1 }}
                          onClick={() => { setEditingName(cluster.name); setAddingNew(false); setError(null); }}
                        >
                          Edit
                        </button>
                        {deletingName === cluster.name ? (
                          <>
                            <button
                              style={{ ...s.btn, ...s.btnSmall, ...s.btnDanger, flex: 1 }}
                              onClick={() => handleDelete(cluster.name)}
                            >
                              Confirm
                            </button>
                            <button
                              style={{ ...s.btn, ...s.btnSmall, ...s.btnGhost }}
                              onClick={() => setDeletingName(null)}
                            >
                              Cancel
                            </button>
                          </>
                        ) : (
                          <button
                            style={{ ...s.btn, ...s.btnSmall, ...s.btnGhost, color: '#E03448' }}
                            onClick={() => handleDelete(cluster.name)}
                          >
                            Delete
                          </button>
                        )}
                      </div>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* ── Callout ── */}
        {!loading && clusters.length > 0 && (
          <div style={s.callout}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#1d4ed8" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ flexShrink: 0, marginTop: '1px' }}>
              <circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>
            </svg>
            <span style={s.calloutText}>
              Changes here take effect on the next <strong>Seed Demo Data</strong> run.
              Clusters with MPI target ≥ 0.72 will produce a Golden Record when seeded.
            </span>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Page styles ───────────────────────────────────────────────────────────────

const s = {
  page: { minHeight: '100vh', backgroundColor: 'var(--light)' },
  header: {
    backgroundColor: 'var(--primary)',
    backgroundImage: `linear-gradient(rgba(255,255,255,.025) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,.025) 1px, transparent 1px)`,
    backgroundSize: '48px 48px',
    padding: '24px 48px',
  },
  headerInner: { maxWidth: '1300px', margin: '0 auto' },
  eyebrow: {
    display: 'inline-flex', alignItems: 'center', gap: '8px',
    fontSize: '9px', fontFamily: 'var(--fb)', fontWeight: 500,
    letterSpacing: '4px', textTransform: 'uppercase',
    color: 'var(--gold-light)', marginBottom: '8px',
  },
  eyebrowLine: { width: '24px', height: '1px', backgroundColor: 'var(--gold-light)', flexShrink: 0 },
  title: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: '28px',
    fontWeight: 300, color: '#ffffff', margin: '0 0 8px', lineHeight: 1.1,
  },
  subtitle: {
    fontFamily: 'var(--fb)', fontSize: '12px',
    color: 'rgba(255,255,255,0.5)', margin: 0, lineHeight: 1.6, maxWidth: '560px',
  },
  body: { maxWidth: '1300px', margin: '0 auto', padding: '40px 48px 80px' },
  actionBar: { display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '28px' },
  clusterCount: {
    marginLeft: 'auto', fontFamily: 'var(--fb)', fontSize: '11px',
    color: 'var(--mid)', letterSpacing: '0.5px',
  },
  errorBox: {
    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    backgroundColor: '#fff0f0', border: '1px solid #ffcccc',
    borderRadius: '8px', padding: '10px 14px', marginBottom: '20px',
  },
  errorText: { fontFamily: 'var(--fb)', fontSize: '12px', color: '#c0392b' },
  addCard: {
    backgroundColor: '#ffffff', borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)', overflow: 'hidden', marginBottom: '28px',
  },
  grid: {
    display: 'grid',
    gridTemplateColumns: 'repeat(auto-fill, minmax(280px, 1fr))',
    gap: '20px',
  },
  card: {
    backgroundColor: '#ffffff', borderRadius: '12px',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)', overflow: 'hidden',
  },
  cardAccent: { height: '3px' },
  cardBody: { padding: '20px' },
  cardTitle: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: '17px',
    fontWeight: 300, color: '#0a1628', marginBottom: '2px',
  },
  slug: {
    fontFamily: 'monospace', fontSize: '10px',
    color: '#94a3b8', backgroundColor: '#f1f5f9',
    padding: '1px 5px', borderRadius: '4px',
  },
  metaLabel: {
    fontFamily: 'var(--fb)', fontSize: '9px', fontWeight: 500,
    letterSpacing: '2px', textTransform: 'uppercase', color: 'var(--mid)',
  },
  statRow: { display: 'flex', gap: '16px', marginBottom: '12px' },
  stat: { display: 'flex', flexDirection: 'column', gap: '1px' },
  statValue: {
    fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px',
    fontWeight: 300, color: 'var(--dark)', lineHeight: 1,
  },
  statLabel: { fontFamily: 'var(--fb)', fontSize: '9px', color: 'var(--mid)', letterSpacing: '0.5px' },
  emptyState: {
    backgroundColor: '#ffffff', borderRadius: '12px',
    padding: '60px 24px', textAlign: 'center',
    boxShadow: '0 1px 4px rgba(0,51,102,0.08)',
    border: '1px dashed var(--primary-30)',
  },
  callout: {
    display: 'flex', alignItems: 'flex-start', gap: '10px',
    backgroundColor: '#eff6ff', border: '1px solid #bfdbfe',
    borderRadius: '8px', padding: '12px 16px', marginTop: '28px',
  },
  calloutText: { fontFamily: 'var(--fb)', fontSize: '12px', color: '#1e3a8a', lineHeight: 1.6 },
  btn: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    gap: '6px', padding: '9px 18px', borderRadius: '8px',
    fontSize: '11px', fontFamily: 'var(--fb)', fontWeight: 500,
    letterSpacing: '0.5px', cursor: 'pointer', border: 'none',
    transition: 'opacity 0.15s',
  },
  btnSmall: { padding: '6px 12px', fontSize: '10px' },
  btnPrimary: { backgroundColor: 'var(--primary)', color: '#ffffff' },
  btnGhost: { backgroundColor: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' },
  btnDanger: { backgroundColor: '#E03448', color: '#ffffff' },
};

// ── Form styles ───────────────────────────────────────────────────────────────

const fs = {
  form: { display: 'flex', flexDirection: 'column', gap: '18px', paddingTop: '14px' },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '16px' },
  grid3: { display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '16px' },
  field: { display: 'flex', flexDirection: 'column', gap: '4px' },
  label: {
    fontFamily: 'var(--fb)', fontSize: '9px', fontWeight: 500,
    letterSpacing: '2px', textTransform: 'uppercase', color: 'var(--mid)',
  },
  input: {
    height: '38px', padding: '0 12px', fontSize: '13px',
    fontFamily: 'var(--fb)', color: 'var(--dark)',
    backgroundColor: '#f7f9fc', border: '1px solid rgba(0,51,102,0.15)',
    borderRadius: '6px', outline: 'none',
  },
  select: {
    height: '38px', padding: '0 12px', fontSize: '13px',
    fontFamily: 'var(--fb)', color: 'var(--dark)',
    backgroundColor: '#f7f9fc', border: '1px solid rgba(0,51,102,0.15)',
    borderRadius: '6px', outline: 'none', cursor: 'pointer',
  },
  hint: { fontFamily: 'var(--fb)', fontSize: '10px', color: '#94a3b8', lineHeight: 1.4 },
  btn: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    gap: '6px', padding: '9px 18px', borderRadius: '8px',
    fontSize: '11px', fontFamily: 'var(--fb)', fontWeight: 500,
    letterSpacing: '0.5px', cursor: 'pointer', border: 'none',
    transition: 'opacity 0.15s',
  },
  btnPrimary: { backgroundColor: 'var(--primary)', color: '#ffffff' },
  btnGhost: { backgroundColor: '#f1f5f9', color: '#475569', border: '1px solid #e2e8f0' },
};
