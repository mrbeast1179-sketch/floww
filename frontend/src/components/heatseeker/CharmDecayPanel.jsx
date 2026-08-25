/**
 * CharmDecayPanel — Solstice steal-list extension
 *
 * Shows how CHARM decays across listed expiries at the strikes nearest
 * spot: one line per strike, x = expiry date, y = net charm ($).
 *
 * Why it matters: charm = dDelta/dTheta. Large negative charm near spot
 * means dealers must BUY as time passes (pin support); large positive
 * charm means dealer selling into decay (pin resistance). Watching charm
 * migrate across expiries shows where the pin lives TODAY vs TOMORROW.
 *
 * Data source: /api/heatmap/{ticker} → grid.charm_grid[expiry][strikeKey]
 * (Rust-computed via decoder_core compute_gex_grid.)
 */
import React, { useMemo } from "react";
import { useEffect, useState } from "react";
import { BACKEND_URL } from "../../config/api";

function fmtM(v) {
  if (v == null || isNaN(v)) return "—";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (a >= 1e9) return `${sign}$${(a / 1e9).toFixed(2)}B`;
  if (a >= 1e6) return `${sign}$${(a / 1e6).toFixed(1)}M`;
  if (a >= 1e3) return `${sign}$${(a / 1e3).toFixed(0)}K`;
  return `${sign}$${a.toFixed(0)}`;
}
function fmtExp(e) {
  const m = /^\d{4}-(\d{2})-(\d{2})$/.exec(e || "");
  return m ? `${m[1]}-${m[2]}` : e;
}

export default function CharmDecayPanel({ ticker = "SPY", spot = null, maxExpiries = 6 }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const ctrl = new AbortController();
    setLoading(true);
    // /api/data not /api/heatmap — same shape, ~300x faster (skill pitfall)
    fetch(
      `${BACKEND_URL}/api/data/${encodeURIComponent(ticker)}?mode=day&expiries=${maxExpiries}`,
      { signal: ctrl.signal },
    )
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(`HTTP ${r.status}`))))
      .then((d) => { setData(d); setLoading(false); })
      .catch((e) => {
        if (e.name === "AbortError") return;
        setError(e.message); setLoading(false);
      });
    return () => ctrl.abort();
  }, [ticker, maxExpiries]);

  const model = useMemo(() => {
    const grid = data?.grid;
    const cg = grid?.charm_grid;
    if (!cg || !grid?.expiries?.length) return null;
    const expiries = [...grid.expiries].sort();
    // strikes nearest spot (±4 strikes)
    const allStrikes = grid.strikes || [];
    let centerIdx = Math.floor(allStrikes.length / 2);
    if (spot) {
      let best = 0, bestD = Infinity;
      allStrikes.forEach((s, i) => {
        const d = Math.abs(s - spot);
        if (d < bestD) { bestD = d; best = i; }
      });
      centerIdx = best;
    }
    const near = allStrikes.slice(Math.max(0, centerIdx - 4), centerIdx + 5);
    // series per strike
    const series = near.map((s) => {
      const key = Number.isInteger(s) ? String(s) : String(s);
      const points = expiries.map((e) => ({ expiry: e, value: cg[e]?.[key] ?? 0 }));
      const total = points.reduce((acc, p) => acc + p.value, 0);
      return { strike: s, points, total };
    });
    series.sort((a, b) => Math.abs(b.total) - Math.abs(a.total));
    const allVals = series.flatMap((s) => s.points.map((p) => p.value));
    const maxAbs = Math.max(1e3, ...allVals.map(Math.abs));
    // net charm per expiry (whole chain)
    const netPerExpiry = expiries.map((e) => {
      const row = cg[e] || {};
      let net = 0;
      Object.values(row).forEach((v) => { net += v; });
      return { expiry: e, net };
    });
    return { expiries, series: series.slice(0, 5), maxAbs, netPerExpiry };
  }, [data, spot]);

  if (loading && !model) {
    return (
      <div className="p-3 rounded-xl border" style={{ background: "rgba(15,23,42,0.5)", borderColor: "rgba(51,65,85,0.5)" }}>
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mb-2">Charm Decay by Expiry</div>
        <div className="h-16 animate-pulse bg-slate-800/40 rounded" />
      </div>
    );
  }
  if (error || !model) {
    return (
      <div className="p-3 rounded-xl border text-[10px] text-slate-500" style={{ background: "rgba(15,23,42,0.5)", borderColor: "rgba(51,65,85,0.5)" }}>
        Charm decay unavailable{error ? ` — ${error}` : ""}
      </div>
    );
  }

  const W = 100; // svg viewBox width in %
  const H = 64;
  const xFor = (i) => (i / Math.max(1, model.expiries.length - 1)) * W;
  const yFor = (v) => H / 2 - (v / model.maxAbs) * (H / 2 - 6);
  const COLORS = ["#38bdf8", "#f472b6", "#34d399", "#fbbf24", "#a78bfa"];

  return (
    <div className="p-3 rounded-xl border" style={{ background: "rgba(15,23,42,0.5)", borderColor: "rgba(51,65,85,0.5)" }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Charm Decay by Expiry</div>
        <div className="text-[9px] text-slate-500">Δ delta per day · dealers hedge the pin</div>
      </div>

      {/* Net charm per expiry — the aggregate decay profile */}
      <div className="flex gap-1.5 flex-wrap mb-2">
        {model.netPerExpiry.map(({ expiry, net }) => (
          <span key={expiry}
            className="px-2 py-0.5 rounded border text-[9px] font-mono"
            style={{
              background: net >= 0 ? "rgba(52,211,153,0.08)" : "rgba(251,113,133,0.08)",
              borderColor: net >= 0 ? "rgba(52,211,153,0.25)" : "rgba(251,113,133,0.25)",
              color: net >= 0 ? "#34d399" : "#fb7185",
            }}
            title={`Net charm ${fmtExp(expiry)}`}>
            {fmtExp(expiry)} · {fmtM(net)}
          </span>
        ))}
      </div>

      {/* Per-strike decay lines */}
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-20" preserveAspectRatio="none">
        {/* zero line */}
        <line x1="0" y1={H / 2} x2={W} y2={H / 2} stroke="rgba(148,163,184,0.25)" strokeWidth="0.4" strokeDasharray="2 2" />
        {model.series.map((s, si) => {
          const pts = s.points.map((p, i) => `${xFor(i)},${yFor(p.value)}`).join(" ");
          return (
            <g key={s.strike}>
              <polyline points={pts} fill="none" stroke={COLORS[si % COLORS.length]} strokeWidth="1" opacity={si === 0 ? 1 : 0.75} />
              {s.points.map((p, i) => (
                <circle key={i} cx={xFor(i)} cy={yFor(p.value)} r="0.8"
                  fill={COLORS[si % COLORS.length]}>
                  <title>{`K=${s.strike} · ${fmtExp(p.expiry)} · ${fmtM(p.value)}`}</title>
                </circle>
              ))}
            </g>
          );
        })}
      </svg>
      <div className="flex justify-between text-[9px] text-slate-500 mt-1">
        <span>{fmtExp(model.expiries[0])}</span>
        <div className="flex gap-2 flex-wrap justify-center">
          {model.series.map((s, i) => (
            <span key={s.strike} className="inline-flex items-center gap-1">
              <span className="w-2 h-0.5 inline-block" style={{ background: COLORS[i % COLORS.length] }} />
              {s.strike}
            </span>
          ))}
        </div>
        <span>{fmtExp(model.expiries[model.expiries.length - 1])}</span>
      </div>
    </div>
  );
}
