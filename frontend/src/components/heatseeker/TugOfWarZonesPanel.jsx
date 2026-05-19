import React from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — GET /api/heatseeker/tug-of-war
 * Returns:
 *   { ticker, in_tug_of_war, zone_low, zone_high,
 *     positive_strikes, negative_strikes,
 *     positive_gex, negative_gex, gex_balance }
 *
 * gex_balance ∈ [-1, 1]:
 *   +1  = all positive   → green
 *    0  = balanced       → amber/yellow
 *   -1  = all negative   → red
 *
 * Bar shows the relative mass of positive vs negative GEX inside the zone;
 * the marker indicates where balance sits in the [-1, +1] range.
 */
function balanceColor(b) {
  if (b > 0.33) return "emerald";
  if (b < -0.33) return "rose";
  return "amber";
}

const COLOR_CLASSES = {
  emerald: {
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
    bar: "bg-emerald-400/70",
    label: "Positive dominates",
  },
  rose: {
    text: "text-rose-300",
    bg: "bg-rose-500/10",
    border: "border-rose-500/40",
    bar: "bg-rose-400/70",
    label: "Negative dominates",
  },
  amber: {
    text: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/40",
    bar: "bg-amber-400/70",
    label: "Balanced — tug of war",
  },
};

export default function TugOfWarZonesPanel({ ticker = "SPY", spot = null }) {
  const { data, loading, error } = useHeatseeker("tug-of-war", { ticker });

  const inTug = !!data?.in_tug_of_war;
  const balance = Number(data?.gex_balance) || 0; // [-1, 1]
  const palette = COLOR_CLASSES[balanceColor(balance)];

  // Map [-1, 1] → [0, 100]% for the marker position.
  const markerPct = Math.max(0, Math.min(100, ((balance + 1) / 2) * 100));

  // Positive/negative bar fills (each is half of the meter).
  const pos = Number(data?.positive_gex) || 0;
  const neg = Math.abs(Number(data?.negative_gex) || 0);
  const total = pos + neg || 1;
  const posPct = (pos / total) * 100;
  const negPct = (neg / total) * 100;

  return (
    <div className="panel p-3" data-testid="hs-tug-of-war">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Tug-of-War Zones</div>
        <span
          className={`text-[9px] uppercase tracking-widest ${
            inTug ? "text-amber-300 font-bold" : "text-slate-500"
          }`}
        >
          {inTug ? "● ACTIVE" : "○ idle"}
        </span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && !inTug && (
        <div className="text-slate-500 text-[11px]">
          No GEX conflict within ±1% of spot.
        </div>
      )}
      {data && inTug && (
        <div className="space-y-2">
          <div className={`rounded border px-2 py-1.5 ${palette.bg} ${palette.border}`}>
            <div className={`text-[10px] uppercase tracking-widest ${palette.text}`}>
              {palette.label}
            </div>
            <div className="flex justify-between text-[11px] mono mt-0.5">
              <span className="text-slate-400">zone</span>
              <span className={palette.text}>
                {fmt(data.zone_low, 1)} – {fmt(data.zone_high, 1)}
              </span>
            </div>
          </div>

          {/* Balance meter: marker on a red→amber→green track */}
          <div>
            <div className="flex justify-between text-[10px] mb-0.5">
              <span className="text-rose-400">−1</span>
              <span className="text-slate-500">balance</span>
              <span className="text-emerald-400">+1</span>
            </div>
            <div className="relative h-2 rounded overflow-hidden bg-gradient-to-r from-rose-500/40 via-amber-400/40 to-emerald-500/40">
              <div
                className="absolute top-0 bottom-0 w-0.5 bg-slate-100"
                style={{ left: `${markerPct}%` }}
              />
            </div>
            <div className="text-[10px] mono text-center mt-0.5 text-slate-300">
              {balance.toFixed(3)}
            </div>
          </div>

          {/* GEX mass split */}
          <div>
            <div className="flex justify-between text-[10px] mb-0.5">
              <span className="text-rose-400">
                neg {fmtAbs(data.negative_gex)} ({data.negative_strikes})
              </span>
              <span className="text-emerald-400">
                pos {fmtAbs(data.positive_gex)} ({data.positive_strikes})
              </span>
            </div>
            <div className="relative h-1.5 bg-slate-800/60 rounded overflow-hidden flex">
              <div
                className="h-full bg-rose-400/70"
                style={{ width: `${negPct}%` }}
              />
              <div
                className="h-full bg-emerald-400/70"
                style={{ width: `${posPct}%` }}
              />
            </div>
          </div>

          {spot != null && (
            <div className="text-[9px] text-slate-600 mono">
              spot {fmt(spot, 1)}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
