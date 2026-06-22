import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — Velocity Mode.
 * Shows dealer urgency: calm / active / urgent.
 */
const MODE_STYLES = {
  calm:   { text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/40", emoji: "🟢", label: "Calm" },
  active: { text: "text-amber-300",   bg: "bg-amber-500/10",   border: "border-amber-500/40",   emoji: "🟡", label: "Active" },
  urgent: { text: "text-rose-300",    bg: "bg-rose-500/10",    border: "border-rose-500/40",    emoji: "🔴", label: "Urgent" },
};

export default function VelocityModeBadge({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("velocity-mode", { ticker });
  const mode = String(data?.mode || "").toLowerCase();
  const style = MODE_STYLES[mode] || { text: "text-slate-300", bg: "bg-slate-700/30", border: "border-slate-600/40", emoji: "⚪", label: "Unknown" };
  const v = Number(data?.velocity_strikes_per_min);
  const vStr = isFinite(v) ? v.toFixed(2) : "—";

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-velocity-mode">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">⚡</span>
          <span className="text-xs font-semibold text-slate-200">Velocity Mode</span>
        </div>
        <span className="text-[10px] text-slate-500">n={data?.n_snapshots ?? "—"}</span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className={`flex items-center justify-between rounded-lg border px-3 py-2.5 ${style.bg} ${style.border}`}>
          <div className="flex items-center gap-2">
            <span className="text-lg">{style.emoji}</span>
            <div>
              <div className={`text-xs font-bold uppercase tracking-widest ${style.text}`}>{data.mode || style.label}</div>
              <div className="text-[9px] text-slate-500">strikes / min</div>
            </div>
          </div>
          <div className={`mono text-2xl font-bold ${style.text}`}>{vStr}</div>
        </div>
      )}
    </div>
  );
}
