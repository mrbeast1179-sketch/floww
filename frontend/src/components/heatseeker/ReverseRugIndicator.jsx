import React from "react";
import { fmt } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Reverse Rug pattern — positive floor below + negative ceiling above.
 * Shows support/resistance levels.
 */
export default function ReverseRugIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("reverse-rug", { ticker });
  const active = !!data?.active;
  const conf = Math.max(0, Math.min(1, Number(data?.confidence) || 0));

  return (
    <div className={`rounded-xl border p-3 transition-all ${active ? "border-emerald-400/40 bg-emerald-500/5" : "border-slate-700/30 bg-slate-800/20"}`}
      data-testid="hs-reverse-rug">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">🔄</span>
          <span className="text-xs font-semibold text-slate-200">Reverse Rug</span>
        </div>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${active ? "text-emerald-300" : "text-slate-500"}`}>
          {active ? <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />ACTIVE</span> : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="space-y-1.5 text-xs">
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Floor</span>
            <span className="mono font-bold text-emerald-400">{data.floor ? `$${fmt(data.floor, 0)}` : "—"}</span>
          </div>
          <div className="flex justify-between items-center">
            <span className="text-slate-400">Ceiling</span>
            <span className="mono font-bold text-rose-400">{data.ceiling ? `$${fmt(data.ceiling, 0)}` : "—"}</span>
          </div>
          <div>
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-slate-400">Confidence</span>
              <span className="mono text-slate-300">{Math.round(conf * 100)}%</span>
            </div>
            <div className="relative h-2 bg-slate-800/60 rounded-full overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-emerald-500 to-emerald-400 rounded-full transition-all" style={{ width: `${conf * 100}%` }} />
            </div>
          </div>
          {data.interpretation && <div className="text-[10px] text-slate-400 italic mt-1">{data.interpretation}</div>}
        </div>
      )}
    </div>
  );
}
