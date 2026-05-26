/**
 * RateLimitDashboard.jsx - Alpha Vantage API Rate Limit Tracker
 * Displays real-time quota usage with color-coded bars.
 */
import React, { useState, useEffect, useCallback } from "react";

const API = `${process.env.REACT_APP_BACKEND_URL}/api`;

function QuotaBar({ used, limit, label, pctUsed }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0;
  const remaining = Math.max(0, limit - used);
  const ratio = limit > 0 ? remaining / limit : 0;
  const barColor = ratio > 0.5 ? "bg-emerald-500" : ratio > 0.25 ? "bg-amber-500" : "bg-rose-500";
  const borderColor = ratio > 0.5 ? "border-emerald-500/30" : ratio > 0.25 ? "border-amber-500/30" : "border-rose-500/30";
  const textColor = ratio > 0.5 ? "text-emerald-400" : ratio > 0.25 ? "text-amber-400" : "text-rose-400";
  return (
    <div className={`rounded-lg border ${borderColor} bg-slate-800/50 p-3`}>
      <div className="flex justify-between items-center mb-2">
        <span className="text-xs font-semibold text-slate-300 uppercase tracking-wider">{label}</span>
        <span className={`text-xs font-bold ${textColor}`}>{remaining} / {limit} left</span>
      </div>
      <div className="w-full bg-slate-700 rounded-full h-2.5">
        <div className={`${barColor} h-2.5 rounded-full transition-all duration-300`} style={{ width: `${pct}%` }} />
      </div>
      <div className="flex justify-between mt-1">
        <span className="text-[10px] text-slate-500">{used} used</span>
        <span className="text-[10px] text-slate-500">{pctUsed != null ? `${pctUsed}%` : `${pct.toFixed(1)}%`} consumed</span>
      </div>
    </div>
  );
}

export default function RateLimitDashboard({ compact = false }) {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch(`${API}/admin/rate-limits`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStatus(data); setError(null);
    } catch (err) { setError(err.message); } finally { setLoading(false); }
  }, []);
  useEffect(() => { fetchStatus(); const i = setInterval(fetchStatus, 15000); return () => clearInterval(i); }, [fetchStatus]);
  if (loading) return <div className="rounded-lg border border-slate-700 bg-slate-800/50 p-4 animate-pulse" />;
  if (error) return <div className="rounded-lg border border-rose-500/30 bg-rose-500/5 p-4 text-xs text-rose-400">{error}<button onClick={fetchStatus} className="block mt-1 underline">Retry</button></div>;
  const m = status?.per_minute, d = status?.per_day;
  if (compact) return <div className="flex items-center gap-3 text-xs"><span className="text-slate-500">AV:</span><span className={m?.remaining > 2 ? "text-emerald-400" : m?.remaining > 0 ? "text-amber-400" : "text-rose-400"}>{m?.remaining ?? "—"}/min</span> <span className="text-slate-600">|</span> <span className={d?.remaining > 100 ? "text-emerald-400" : d?.remaining > 50 ? "text-amber-400" : "text-rose-400"}>{d?.remaining ?? "—"}/day</span></div>;
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-200">Alpha Vantage API Quota</h3>
        <button onClick={fetchStatus} className="text-[10px] text-slate-500 hover:text-slate-300">Refresh</button>
      </div>
      <QuotaBar used={m?.used ?? 0} limit={m?.limit ?? 5} label="Per Minute" pctUsed={m?.pct_used} />
      <QuotaBar used={d?.used ?? 0} limit={d?.limit ?? 500} label="Per Day" pctUsed={d?.pct_used} />
      <div className="text-[10px] text-slate-600 text-center">Free tier: 5 calls/min, 500 calls/day. Auto-refreshes every 15s.</div>
    </div>
  );
}
