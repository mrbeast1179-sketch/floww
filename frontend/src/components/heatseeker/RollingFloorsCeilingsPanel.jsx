import React from "react";
import { fmt } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — Rolling Floors / Ceilings.
 * Shows trend formation: rising floor = bullish, falling ceiling = bearish.
 */
function trendArrow(trend) {
  if (trend === "rising") return { sym: "▲", cls: "text-emerald-400" };
  if (trend === "falling") return { sym: "▼", cls: "text-rose-400" };
  return { sym: "→", cls: "text-slate-500" };
}

function signalStyle(signal) {
  if (signal === "bullish") return { label: "Bullish — floors rolling up", text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/40" };
  if (signal === "bearish") return { label: "Bearish — ceilings rolling down", text: "text-rose-300", bg: "bg-rose-500/10", border: "border-rose-500/40" };
  return { label: "Neutral — no trend formation", text: "text-slate-300", bg: "bg-slate-700/30", border: "border-slate-600/40" };
}

export default function RollingFloorsCeilingsPanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("rolling-floors-ceilings", { ticker });
  const floors = data?.floor_series || [];
  const ceilings = data?.ceiling_series || [];
  const fa = trendArrow(data?.floor_trend);
  const ca = trendArrow(data?.ceiling_trend);
  const sig = signalStyle(data?.signal);

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-rolling-floors-ceilings">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">📊</span>
          <span className="text-xs font-semibold text-slate-200">Rolling Floors / Ceilings</span>
        </div>
        <span className="text-[10px] text-slate-500">{floors.length}f · {ceilings.length}c</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <>
          <div className={`rounded-lg border px-3 py-2 mb-3 ${sig.bg} ${sig.border}`}>
            <div className={`text-[10px] uppercase tracking-widest font-bold ${sig.text}`}>{data.signal || "—"}</div>
            <div className={`text-xs mt-0.5 ${sig.text}`}>{sig.label}</div>
          </div>
          <div className="grid grid-cols-2 gap-3 text-xs">
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-emerald-400 font-semibold">Floors</span>
                <span className={`mono text-sm font-bold ${fa.cls}`}>{fa.sym}</span>
              </div>
              {floors.length === 0 ? (
                <div className="text-slate-600 text-[10px]">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {floors.slice(-6).map((f, i) => (
                    <li key={i} className="mono text-emerald-300 flex justify-between text-[11px]">
                      <span className="text-slate-500 text-[9px]">t-{floors.length - 1 - i - (floors.length - Math.min(6, floors.length))}</span>
                      <span className="font-bold">${fmt(f, 1)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="text-[10px] text-slate-500 mt-1">trend: {data.floor_trend || "—"}</div>
            </div>
            <div>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-rose-400 font-semibold">Ceilings</span>
                <span className={`mono text-sm font-bold ${ca.cls}`}>{ca.sym}</span>
              </div>
              {ceilings.length === 0 ? (
                <div className="text-slate-600 text-[10px]">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {ceilings.slice(-6).map((c, i) => (
                    <li key={i} className="mono text-rose-300 flex justify-between text-[11px]">
                      <span className="text-slate-500 text-[9px]">t-{ceilings.length - 1 - i - (ceilings.length - Math.min(6, ceilings.length))}</span>
                      <span className="font-bold">${fmt(c, 1)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="text-[10px] text-slate-500 mt-1">trend: {data.ceiling_trend || "—"}</div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
