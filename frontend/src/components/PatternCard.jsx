import React from "react";
import { fmt, fmtAbs, pctClass, tagFor } from "../lib/helpers";

export default function PatternCard({ p }) {
  const biasColor = {
    bearish: "text-rose-400 border-rose-500/40",
    bullish: "text-emerald-400 border-emerald-500/40",
    reversion: "text-amber-300 border-amber-500/40",
    trap: "text-fuchsia-400 border-fuchsia-500/40",
    "do not trade": "text-slate-500 border-slate-600",
    resistance: "text-rose-400 border-rose-500/40",
    support: "text-emerald-400 border-emerald-500/40",
  }[p.bias] || "text-slate-300 border-slate-700";
  return (
    <div className={`panel-2 p-3 border ${biasColor}`} data-testid={`pattern-${p.name.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex justify-between items-baseline">
        <div className="text-sm font-bold tracking-wide uppercase">{p.name}</div>
        <div className="text-[10px] uppercase tracking-widest opacity-70">{p.bias}</div>
      </div>
      <div className="h-1 mt-2 mb-2 bg-slate-800 rounded">
        <div className="h-full rounded" style={{ width: `${(p.severity * 100).toFixed(0)}%`, background: "currentColor", opacity: 0.6 }} />
      </div>
      <div className="text-[11px] text-slate-400 leading-snug">{p.note}</div>
    </div>
  );
}
