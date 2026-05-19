import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — GET /api/heatseeker/rainbow-road
 * Card with top-strike-share + significant-strike-count.
 */
const RAINBOW = [
  "#f87171", "#fb923c", "#fbbf24", "#34d399", "#22d3ee", "#818cf8", "#c084fc",
];

export default function RainbowRoadIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("rainbow-road", { ticker });
  const active = !!data?.active;
  const topShare = Math.max(0, Math.min(1, Number(data?.top_strike_share) || 0));
  const n = Number(data?.n_strikes_significant) || 0;

  // Render n_strikes (capped at 7) coloured dots so dispersion is visually obvious
  const dotCount = Math.min(7, n);

  return (
    <div
      className={`panel p-3 ${active ? "border-sky-400/40" : ""}`}
      style={active ? { boxShadow: "0 0 0 1px rgba(56,189,248,0.25)" } : undefined}
      data-testid="hs-rainbow-road"
    >
      <div className="flex items-center justify-between mb-1">
        <div className="label">Rainbow Road</div>
        <span
          className={`text-[9px] uppercase tracking-widest ${
            active ? "text-sky-300 font-bold" : "text-slate-500"
          }`}
        >
          {active ? "● ACTIVE" : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="space-y-2 text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Top strike share</span>
            <span className="mono text-slate-200 font-bold">
              {(topShare * 100).toFixed(1)}%
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Significant strikes</span>
            <span className="mono text-slate-200 font-bold">{n}</span>
          </div>
          <div className="flex gap-1 mt-1">
            {Array.from({ length: dotCount }).map((_, i) => (
              <span
                key={i}
                className="inline-block w-2 h-2 rounded-full"
                style={{ background: RAINBOW[i % RAINBOW.length] }}
              />
            ))}
            {dotCount === 0 && (
              <span className="text-[10px] text-slate-600">
                — concentrated —
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
