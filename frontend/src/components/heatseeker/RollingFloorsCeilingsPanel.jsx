import React from "react";
import { fmt } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — GET /api/heatseeker/rolling-floors-ceilings
 * Returns:
 *   { ticker, floor_series, ceiling_series, floor_trend, ceiling_trend, signal }
 *
 * floor_trend / ceiling_trend ∈ {"rising", "falling", "flat"}
 * signal ∈ {"bullish", "bearish", "neutral"}
 *
 * Trend formation: a rising floor is dealers adding long-gamma support higher
 * (bullish); a falling ceiling is dealers adding short-gamma resistance lower
 * (bearish). Verdict pill at the top is the headline takeaway.
 */
function trendArrow(trend) {
  if (trend === "rising") return { sym: "▲", cls: "text-emerald-400" };
  if (trend === "falling") return { sym: "▼", cls: "text-rose-400" };
  return { sym: "→", cls: "text-slate-500" };
}

function signalStyle(signal) {
  if (signal === "bullish") {
    return {
      label: "Bullish — floors rolling up",
      text: "text-emerald-300",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/40",
    };
  }
  if (signal === "bearish") {
    return {
      label: "Bearish — ceilings rolling down",
      text: "text-rose-300",
      bg: "bg-rose-500/10",
      border: "border-rose-500/40",
    };
  }
  return {
    label: "Neutral — no trend formation",
    text: "text-slate-300",
    bg: "bg-slate-700/30",
    border: "border-slate-600/40",
  };
}

export default function RollingFloorsCeilingsPanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("rolling-floors-ceilings", {
    ticker,
  });
  const floors = data?.floor_series || [];
  const ceilings = data?.ceiling_series || [];
  const fa = trendArrow(data?.floor_trend);
  const ca = trendArrow(data?.ceiling_trend);
  const sig = signalStyle(data?.signal);

  return (
    <div className="panel p-3" data-testid="hs-rolling-floors-ceilings">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Rolling Floors / Ceilings</div>
        <span className="text-[9px] text-slate-500">
          {floors.length}f · {ceilings.length}c
        </span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <>
          <div
            className={`rounded border px-2 py-1.5 mb-2 ${sig.bg} ${sig.border}`}
          >
            <div className={`text-[10px] uppercase tracking-widest ${sig.text}`}>
              {data.signal || "—"}
            </div>
            <div className={`text-[11px] ${sig.text}`}>{sig.label}</div>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[11px]">
            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="label text-emerald-400">Floors</div>
                <span className={`mono text-sm font-bold ${fa.cls}`}>
                  {fa.sym}
                </span>
              </div>
              {floors.length === 0 ? (
                <div className="text-slate-600 text-[10px]">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {floors.slice(-6).map((f, i) => (
                    <li
                      key={i}
                      className="mono text-emerald-300 flex justify-between"
                    >
                      <span className="text-slate-600 text-[9px]">
                        t-{floors.length - 1 - i - (floors.length - Math.min(6, floors.length))}
                      </span>
                      <span>{fmt(f, 1)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="text-[9px] text-slate-600 mt-1">
                trend: {data.floor_trend || "—"}
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <div className="label text-rose-400">Ceilings</div>
                <span className={`mono text-sm font-bold ${ca.cls}`}>
                  {ca.sym}
                </span>
              </div>
              {ceilings.length === 0 ? (
                <div className="text-slate-600 text-[10px]">—</div>
              ) : (
                <ul className="space-y-0.5">
                  {ceilings.slice(-6).map((c, i) => (
                    <li
                      key={i}
                      className="mono text-rose-300 flex justify-between"
                    >
                      <span className="text-slate-600 text-[9px]">
                        t-{ceilings.length - 1 - i - (ceilings.length - Math.min(6, ceilings.length))}
                      </span>
                      <span>{fmt(c, 1)}</span>
                    </li>
                  ))}
                </ul>
              )}
              <div className="text-[9px] text-slate-600 mt-1">
                trend: {data.ceiling_trend || "—"}
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
