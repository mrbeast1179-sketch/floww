import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — GET /api/heatseeker/velocity-mode
 * Returns { velocity_strikes_per_min, mode, n_snapshots }.
 *
 * Mode → colour:
 *   calm   → emerald (green)
 *   active → amber  (yellow)
 *   urgent → rose   (red)
 */
const MODE_STYLES = {
  calm: {
    text: "text-emerald-300",
    bg: "bg-emerald-500/10",
    border: "border-emerald-500/40",
  },
  active: {
    text: "text-amber-300",
    bg: "bg-amber-500/10",
    border: "border-amber-500/40",
  },
  urgent: {
    text: "text-rose-300",
    bg: "bg-rose-500/10",
    border: "border-rose-500/40",
  },
};

export default function VelocityModeBadge({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("velocity-mode", { ticker });
  const mode = String(data?.mode || "").toLowerCase();
  const style = MODE_STYLES[mode] || {
    text: "text-slate-300",
    bg: "bg-slate-700/30",
    border: "border-slate-600/40",
  };
  const v = Number(data?.velocity_strikes_per_min);
  const vStr = isFinite(v) ? v.toFixed(2) : "—";

  return (
    <div className="panel p-3" data-testid="hs-velocity-mode">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Velocity Mode</div>
        <span className="text-[9px] text-slate-500">
          n={data?.n_snapshots ?? "—"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div
          className={`flex items-center justify-between rounded border px-2 py-1.5 ${style.bg} ${style.border}`}
        >
          <div>
            <div className={`text-[10px] uppercase tracking-widest ${style.text}`}>
              {data.mode || "—"}
            </div>
            <div className="text-[9px] text-slate-500">strikes / min</div>
          </div>
          <div className={`mono text-xl font-bold ${style.text}`}>{vStr}</div>
        </div>
      )}
    </div>
  );
}
