import React, { useState } from 'react';
import { useAuth } from '../context/AuthContext';

export default function SignInPage({ onSignIn }) {
  const { login } = useAuth();
  const [email, setEmail] = useState('demo@skylit.dev');
  const [tier, setTier] = useState('pro');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { user } = await login(email, tier);
      if (onSignIn) onSignIn(user);
    } catch (err) {
      setError(err.response?.data?.detail || err.message || 'Sign in failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div
      className="min-h-screen flex items-center justify-center"
      style={{
        background: 'radial-gradient(1100px 700px at 80% -10%, rgba(201,168,76,0.08), transparent 60%), radial-gradient(900px 600px at 0% 100%, rgba(56,189,248,0.06), transparent 60%), var(--bg)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <div
        className="w-full max-w-md p-8 rounded-2xl"
        style={{
          background: 'var(--panel)',
          border: '1px solid var(--border)',
          boxShadow: '0 24px 80px rgba(0,0,0,0.5), inset 0 1px rgba(255,255,255,0.03)',
        }}
      >
        {/* Logo */}
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-14 h-14 rounded-xl mb-4"
            style={{ background: 'var(--gold-dim)', border: '1px solid var(--gold-border)' }}
          >
            <span className="display font-bold text-2xl" style={{ color: 'var(--gold)' }}>α</span>
          </div>
          <h1
            className="display text-2xl font-bold tracking-[0.08em]"
            style={{ color: 'var(--text-primary)' }}
          >
            Alpha Pod
          </h1>
          <p className="mt-2 text-[13px]" style={{ color: 'var(--text-tertiary)' }}>
            Dev login — issues a local JWT. In production this is replaced by Whop OAuth.
          </p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          {/* Email */}
          <div>
            <label
              className="block text-[10px] font-semibold uppercase tracking-[0.12em] mb-2"
              style={{ color: 'var(--text-quaternary)' }}
            >
              Email
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              placeholder="you@example.com"
              className="w-full px-4 py-3 rounded-xl text-[14px] transition-colors"
              style={{
                background: 'var(--surface-1)',
                border: '1px solid var(--border-c)',
                color: 'var(--text-primary)',
                outline: 'none',
              }}
            />
          </div>

          {/* Tier */}
          <div>
            <label
              className="block text-[10px] font-semibold uppercase tracking-[0.12em] mb-2"
              style={{ color: 'var(--text-quaternary)' }}
            >
              Tier
            </label>
            <div className="relative">
              <select
                value={tier}
                onChange={e => setTier(e.target.value)}
                className="w-full px-4 py-3 rounded-xl text-[14px] appearance-none cursor-pointer transition-colors"
                style={{
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-c)',
                  color: 'var(--text-primary)',
                  outline: 'none',
                }}
              >
                <option value="free">Free</option>
                <option value="pro">Pro</option>
                <option value="elite">Elite</option>
              </select>
              <div
                className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none"
                style={{ color: 'var(--text-quaternary)' }}
              >
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m6 9 6 6 6-6"/>
                </svg>
              </div>
            </div>
          </div>

          {/* Error */}
          {error && (
            <div
              className="px-4 py-3 rounded-xl text-[13px]"
              style={{
                background: 'var(--red-dim)',
                border: '1px solid var(--red)',
                color: 'var(--red)',
              }}
            >
              {error}
            </div>
          )}

          {/* Submit */}
          <button
            type="submit"
            disabled={loading}
            className="w-full py-3 rounded-xl text-[14px] font-semibold tracking-[0.04em] transition-all"
            style={{
              background: loading ? 'var(--surface-1)' : 'var(--gold)',
              color: loading ? 'var(--text-quaternary)' : '#000',
              border: '1px solid',
              borderColor: loading ? 'var(--border-c)' : 'var(--gold)',
              cursor: loading ? 'not-allowed' : 'pointer',
              opacity: loading ? 0.7 : 1,
            }}
          >
            {loading ? 'Signing in…' : 'SIGN IN'}
          </button>
        </form>

        {/* Footer */}
        <div className="mt-6 text-center">
          <p className="text-[11px]" style={{ color: 'var(--text-quaternary)' }}>
            Alpha Pod Hub · Institutional Options Intelligence
          </p>
        </div>
      </div>
    </div>
  );
}
