import React from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — Tug-of-War Zones.
 * Shows GEX conflict zone with balance meter.
 */
function balanceColor(b) {
  if (b > 0.33) return "emerald";
  if (b < -0.33) return "rose";
  return "amber";
}

const COLOR_CLASSES = {
  emerald: { text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/40", bar: "bg-emerald-400/70", label: "Positive dominates" },
  rose: { text: "text-rose-300", bg: "bg-rose-500/10", border: "border-rose-500/40", bar: "bg-rose-400/70", label: "Negative dominates" },
  amber: { text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/40", bar: "bg-amber-400/70", label: "Balanced — tug of war" },
};

export default function TugOfWarZonesPanel({ ticker = "SPY", spot = null }) {
  const { data, loading, error } = useHeatseeker("tug-of-war", { ticker });
  const inTug = !!data?.in_tug_of_war;
  const balance = Number(data?.gex_balance) || 0;
  const palette = COLOR_CLASSES[balanceColor(balance)];
  const markerPct = Math.max(0, Math.min(100, ((balance + 1) / 2) * 100));
  const pos = Number(data?.positive_gex) || 0;
  const neg = Math.abs(Number(data?.negative_gex) || 0);
  const total = pos + neg || 1;
  const posPct = (pos / total) * 100;
  const negPct = (neg / total) * 100;

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-tug-of-war">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">⚔️</span>
          <span className="text-xs font-semibold text-slate-200">Tug-of-War Zones</span>
        </div>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${inTug ? "text-amber-300" : "text-slate-500"}`}>
          {inTug ? <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />ACTIVE</span> : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && !inTug && (
        <div className="text-slate-500 text-xs py-2 text-center">No GEX conflict near spot</div>
      )}
      {data && inTug && (
        <div className="space-y-2.5">
          <div className={`rounded-lg border px-3 py-2 ${palette.bg} ${palette.border}`}>
            <div className={`text-[10px] uppercase tracking-widest font-bold ${palette.text}`}>{palette.label}</div>
            <div className="flex justify-between text-xs mono mt-1">
              <span className="text-slate-400">zone</span>
              <span className={`font-bold ${palette.text}`}>{fmt(data.zone_low, 1)} – {fmt(data.zone_high, 1)}</span>
            </div>
          </div>

          {/* Balance meter */}
          <div>
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-rose-400 font-bold">−1</span>
              <span className="text-slate-400">balance</span>
              <span className="text-emerald-400 font-bold">+1</span>
            </div>
            <div className="relative h-2.5 rounded-full overflow-hidden bg-gradient-to-r from-rose-500/40 via-amber-400/40 to-emerald-500/40">
              <div className="absolute top-0 bottom-0 w-1 bg-white rounded-full shadow-lg" style={{ left: `${markerPct}%`, transform: "translateX(-50%)" }} />
            </div>
            <div className="text-xs mono text-center mt-1 text-slate-200 font-bold">{balance.toFixed(3)}</div>
          </div>

          {/* GEX mass split */}
          <div>
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-rose-400 font-bold">neg {fmtAbs(data.negative_gex)} ({data.negative_strikes})</span>
              <span className="text-emerald-400 font-bold">pos {fmtAbs(data.positive_gex)} ({data.positive_strikes})</span>
            </div>
            <div className="relative h-2.5 bg-slate-800/60 rounded-full overflow-hidden flex">
              <div className="h-full bg-rose-400/70 rounded-l-full" style={{ width: `${negPct}%` }} />
              <div className="h-full bg-emerald-400/70 rounded-r-full" style={{ width: `${posPct}%` }} />
            </div>
          </div>

          {spot != null && (
            <div className="text-[10px] text-slate-500 mono text-center pt-1 border-t border-slate-700/30">
              spot: {fmt(spot, 2)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
