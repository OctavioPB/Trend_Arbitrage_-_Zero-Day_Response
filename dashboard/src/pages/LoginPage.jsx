import React, { useState } from 'react';

/**
 * Login page — POSTs OAuth2 form credentials to /auth/token, stores the JWT
 * in sessionStorage, then calls onLogin(token) to hand control back to App.
 */
export default function LoginPage({ onLogin }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const body = new URLSearchParams({ username, password });
      const res = await fetch('/auth/token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: body.toString(),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail || 'Authentication failed');
        return;
      }
      const data = await res.json();
      sessionStorage.setItem('ta_token', data.access_token);
      onLogin(data.access_token);
    } catch {
      setError('Network error — is the API running?');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div style={s.page}>

      {/* ── Navigation ── */}
      <nav style={s.nav}>
        <span>
          <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, color: '#ffffff' }}>O</span>
          <em style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: '20px', fontWeight: 300, fontStyle: 'italic', color: 'var(--gold-light)' }}>PB</em>
        </span>
        <span style={s.navTitle}>TREND ARBITRAGE · INTELLIGENCE</span>
      </nav>

      {/* ── Centered card ── */}
      <div style={s.center}>
        <div style={s.card}>

          {/* Gold accent bar */}
          <div style={s.accent} />

          <div style={s.cardBody}>
            <h1 style={s.title}>
              Trend{' '}
              <em style={{ fontStyle: 'italic', color: 'var(--gold)' }}>Arbitrage</em>
            </h1>
            <p style={s.sub}>Sign in to access the intelligence dashboard</p>

            <form onSubmit={handleSubmit} style={s.form}>
              <div style={s.field}>
                <label style={s.label} htmlFor="ta-username">Username</label>
                <input
                  id="ta-username"
                  type="text"
                  autoComplete="username"
                  required
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  style={s.input}
                  placeholder="admin"
                />
              </div>

              <div style={s.field}>
                <label style={s.label} htmlFor="ta-password">Password</label>
                <input
                  id="ta-password"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  style={s.input}
                  placeholder="••••••••"
                />
              </div>

              {error && (
                <div style={s.errorBox}>
                  <span style={s.errorText}>{error}</span>
                </div>
              )}

              <button type="submit" style={loading ? { ...s.btn, ...s.btnDisabled } : s.btn} disabled={loading}>
                {loading ? 'Signing in…' : 'Sign In'}
              </button>
            </form>
          </div>
        </div>

        <p style={s.hint}>
          OPB · OCTAVIO PÉREZ BRAVO · TREND ARBITRAGE & ZERO-DAY RESPONSE
        </p>
      </div>
    </div>
  );
}

// ── Styles ────────────────────────────────────────────────────────────────────

const s = {
  page: {
    minHeight: '100vh',
    backgroundColor: 'var(--light)',
    display: 'flex',
    flexDirection: 'column',
  },
  nav: {
    height: '52px',
    backgroundColor: 'rgba(0,51,102,0.97)',
    borderBottom: '1px solid rgba(255,255,255,0.08)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '0 40px',
    flexShrink: 0,
  },
  navTitle: {
    fontFamily: 'var(--fb)',
    fontSize: '9px',
    letterSpacing: '3px',
    textTransform: 'uppercase',
    color: 'rgba(255,255,255,0.4)',
  },
  center: {
    flex: 1,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    justifyContent: 'center',
    padding: '48px 24px',
  },
  card: {
    width: '100%',
    maxWidth: '420px',
    backgroundColor: 'var(--white)',
    borderRadius: '12px',
    boxShadow: '0 4px 24px rgba(0,51,102,0.12)',
    overflow: 'hidden',
  },
  accent: {
    height: '4px',
    backgroundColor: 'var(--gold)',
  },
  cardBody: {
    padding: '40px 40px 36px',
  },
  title: {
    fontFamily: "'Fraunces', Georgia, serif",
    fontSize: '32px',
    fontWeight: 300,
    color: 'var(--dark)',
    margin: '0 0 8px 0',
    lineHeight: 1.1,
  },
  sub: {
    fontFamily: 'var(--fb)',
    fontSize: '13px',
    color: 'var(--mid)',
    margin: '0 0 32px 0',
    lineHeight: 1.5,
  },
  form: {
    display: 'flex',
    flexDirection: 'column',
    gap: '20px',
  },
  field: {
    display: 'flex',
    flexDirection: 'column',
    gap: '6px',
  },
  label: {
    fontFamily: 'var(--fb)',
    fontSize: '10px',
    fontWeight: 500,
    letterSpacing: '2px',
    textTransform: 'uppercase',
    color: 'var(--mid)',
  },
  input: {
    height: '44px',
    padding: '0 14px',
    fontSize: '14px',
    fontFamily: 'var(--fb)',
    color: 'var(--dark)',
    backgroundColor: '#f7f9fc',
    border: '1px solid rgba(0,51,102,0.15)',
    borderRadius: '8px',
    outline: 'none',
    transition: 'border-color 0.15s',
  },
  errorBox: {
    padding: '10px 14px',
    borderRadius: '8px',
    backgroundColor: '#fff0f0',
    border: '1px solid #ffcccc',
  },
  errorText: {
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    color: '#c0392b',
    lineHeight: 1.4,
  },
  btn: {
    height: '48px',
    backgroundColor: 'var(--primary)',
    color: 'var(--white)',
    border: 'none',
    borderRadius: '8px',
    cursor: 'pointer',
    fontFamily: 'var(--fb)',
    fontSize: '12px',
    fontWeight: 500,
    letterSpacing: '2px',
    textTransform: 'uppercase',
    marginTop: '4px',
    transition: 'opacity 0.15s',
  },
  btnDisabled: {
    opacity: 0.6,
    cursor: 'not-allowed',
  },
  hint: {
    marginTop: '24px',
    fontFamily: 'var(--fb)',
    fontSize: '9px',
    letterSpacing: '2px',
    textTransform: 'uppercase',
    color: 'rgba(0,51,102,0.35)',
  },
};
