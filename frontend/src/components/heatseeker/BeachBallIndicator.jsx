import React from "react";
import { fmt } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — GET /api/heatseeker/beach-ball
 * Single status card. Renders prominent when active.
 */
export default function BeachBallIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("beach-ball", { ticker });
  const active = !!data?.active;
  const conf = Math.max(0, Math.min(1, Number(data?.confidence) || 0));
  const dirSign =
    data?.direction === "above" ? 1 :
    data?.direction === "below" ? -1 : 0;

  return (
    <div
      className={`panel p-3 ${active ? "border-amber-400/40" : ""}`}
      style={active ? { boxShadow: "0 0 0 1px rgba(251,191,36,0.25)" } : undefined}
      data-testid="hs-beach-ball"
    >
      <div className="flex items-center justify-between mb-1">
        <div className="label">Beach Ball</div>
        <span
          className={`text-[9px] uppercase tracking-widest ${
            active ? "text-amber-300 font-bold" : "text-slate-500"
          }`}
        >
          {active ? "● ACTIVE" : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="space-y-1 text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">King</span>
            <span className="mono text-amber-300">
              {fmt(data.king_node, 0) ?? "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Distance</span>
            <span
              className={`mono ${
                dirSign > 0
                  ? "text-emerald-400"
                  : dirSign < 0
                  ? "text-rose-400"
                  : "text-slate-300"
              }`}
            >
              {data.spot_distance_pct != null
                ? `${(data.spot_distance_pct * 100).toFixed(2)}%`
                : "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Direction</span>
            <span className="mono text-slate-300">{data.direction || "—"}</span>
          </div>
          <div>
            <div className="flex justify-between text-[10px] mb-0.5">
              <span className="text-slate-500">Confidence</span>
              <span className="mono text-slate-400">
                {Math.round(conf * 100)}%
              </span>
            </div>
            <div className="relative h-1.5 bg-slate-800/60 rounded overflow-hidden">
              <div
                className="absolute inset-y-0 left-0 bg-amber-400/70 rounded"
                style={{ width: `${conf * 100}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
