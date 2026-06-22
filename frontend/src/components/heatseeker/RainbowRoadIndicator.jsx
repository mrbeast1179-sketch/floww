import React from "react";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Rainbow Road pattern — no dominant structure, chaos.
 * Warning to sit out or reduce size.
 */
export default function RainbowRoadIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("rainbow-road", { ticker });
  const active = !!data?.active;
  const conf = Math.max(0, Math.min(1, Number(data?.confidence) || 0));

  return (
    <div className={`rounded-xl border p-3 transition-all ${active ? "border-purple-400/40 bg-purple-500/5" : "border-slate-700/30 bg-slate-800/20"}`}
      data-testid="hs-rainbow-road">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <span className="text-sm">🌈</span>
          <span className="text-xs font-semibold text-slate-200">Rainbow Road</span>
        </div>
        <span className={`text-[10px] uppercase tracking-widest font-bold ${active ? "text-purple-300" : "text-slate-500"}`}>
          {active ? <span className="flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-purple-400 animate-pulse" />CHAOS</span> : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="space-y-2 text-xs">
          <div className={`text-center py-2 rounded-lg ${active ? "bg-purple-500/10 border border-purple-500/20" : "bg-slate-800/30"}`}>
            <div className={`font-bold text-sm ${active ? "text-purple-300" : "text-slate-400"}`}>
              {active ? "⚠️ No Dominant Structure" : "Structure Detected"}
            </div>
            <div className="text-[10px] text-slate-400 mt-0.5">
              {active ? "Reduce size or sit out" : "Market showing clear positioning"}
            </div>
          </div>
          <div>
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-slate-400">Confidence</span>
              <span className="mono text-slate-300">{Math.round(conf * 100)}%</span>
            </div>
            <div className="relative h-2 bg-slate-800/60 rounded-full overflow-hidden">
              <div className="absolute inset-y-0 left-0 bg-gradient-to-r from-purple-500 to-purple-400 rounded-full transition-all" style={{ width: `${conf * 100}%` }} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
