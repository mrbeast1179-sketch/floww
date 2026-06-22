import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — Flip Zones panel.
 * Renders flip zones sorted by distance from spot.
 */
export default function FlipZonesPanel({ ticker = "SPY", spot = null, windowPct = 0.05 }) {
  const { data, loading, error } = useheatseeker("flip-zones", { ticker, window_pct: windowPct });

  const rows = useMemo(() => {
    const zones = data?.flip_zones || [];
    if (spot == null) return zones;
    return [...zones].sort((a, b) => Math.abs(a.price - spot) - Math.abs(b.price - spot));
  }, [data, spot]);

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-flip-zones">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">⚡</span>
          <span className="text-xs font-semibold text-slate-200">Flip Zones</span>
        </div>
        <span className="text-[10px] text-slate-500 mono">
          {data?.window_low != null && data?.window_high != null
            ? `${fmt(data.window_low, 0)} – ${fmt(data.window_high, 0)}`
            : "—"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && rows.length === 0 && (
        <div className="text-slate-500 text-xs py-2 text-center">No flip zones in window</div>
      )}
      {rows.length > 0 && (
        <div className="space-y-1">
          {rows.map((z, i) => {
            const dir = `${z.from_sign === "positive" ? "+" : "−"} → ${z.to_sign === "positive" ? "+" : "−"}`;
            const isBullish = z.to_sign === "positive";
            return (
              <div key={`${z.price}-${i}`} className="flex items-center justify-between text-xs py-1 border-b border-slate-800/40 last:border-0">
                <span className="mono font-bold text-slate-200">${fmt(z.price, 1)}</span>
                <span className={`mono text-[10px] font-bold ${isBullish ? "text-emerald-400" : "text-rose-400"}`}>{dir}</span>
                <span className="mono text-slate-400 text-[10px]">γ {fmtAbs(z.strength)}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
