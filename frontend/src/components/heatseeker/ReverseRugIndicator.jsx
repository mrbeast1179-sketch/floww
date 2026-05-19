import React from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 2 — GET /api/heatseeker/reverse-rug
 * Single status card with floor + ceiling strikes/GEX.
 */
export default function ReverseRugIndicator({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("reverse-rug", { ticker });
  const active = !!data?.active;

  return (
    <div
      className={`panel p-3 ${active ? "border-rose-400/40" : ""}`}
      style={active ? { boxShadow: "0 0 0 1px rgba(248,113,113,0.25)" } : undefined}
      data-testid="hs-reverse-rug"
    >
      <div className="flex items-center justify-between mb-1">
        <div className="label">Reverse Rug</div>
        <span
          className={`text-[9px] uppercase tracking-widest ${
            active ? "text-rose-300 font-bold" : "text-slate-500"
          }`}
        >
          {active ? "● ACTIVE" : "○ idle"}
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-[11px]">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="grid grid-cols-2 gap-2 text-[11px]">
          <div>
            <div className="label text-emerald-400">Floor</div>
            <div className="mono text-slate-200 font-bold">
              {fmt(data.floor_strike, 0) ?? "—"}
            </div>
            <div className="text-[9px] text-slate-500 mono">
              γ {fmtAbs(data.floor_gex)}
            </div>
          </div>
          <div>
            <div className="label text-rose-400">Ceiling</div>
            <div className="mono text-slate-200 font-bold">
              {fmt(data.ceiling_strike, 0) ?? "—"}
            </div>
            <div className="text-[9px] text-slate-500 mono">
              γ {fmtAbs(data.ceiling_gex)}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
