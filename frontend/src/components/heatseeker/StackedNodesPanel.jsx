import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — GET /api/heatseeker/stacked-nodes
 * Returns:
 *   { ticker, spot, stacked_nodes, count }
 *
 * Each stacked node carries: { strike, call_gex, put_gex, conflict }
 *
 * Visualization: side-by-side bars where call (emerald) and put (rose)
 * widths are scaled to the largest combined magnitude in the result set —
 * makes it visually obvious which strikes carry the largest two-sided
 * dealer footprint. Sorted by combined |GEX| descending.
 */
export default function StackedNodesPanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("stacked-nodes", { ticker });

  const { rows, maxMag } = useMemo(() => {
    const nodes = data?.stacked_nodes || [];
    const enriched = nodes.map((n) => {
      const cg = Math.abs(Number(n.call_gex) || 0);
      const pg = Math.abs(Number(n.put_gex) || 0);
      return { ...n, cg, pg, mag: cg + pg };
    });
    enriched.sort((a, b) => b.mag - a.mag);
    const mx = enriched.reduce((m, n) => Math.max(m, n.mag), 0) || 1;
    return { rows: enriched, maxMag: mx };
  }, [data]);

  return (
    <div className="panel p-3" data-testid="hs-stacked-nodes">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Stacked Nodes</div>
        <span className="text-[9px] text-slate-500">{data?.count ?? 0}</span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && rows.length === 0 && (
        <div className="text-slate-500 text-[11px]">
          No stacked conflict strikes.
        </div>
      )}
      {rows.length > 0 && (
        <div className="space-y-2">
          {rows.map((n, i) => {
            const cw = (n.cg / maxMag) * 50; // half-width, 0-50%
            const pw = (n.pg / maxMag) * 50;
            return (
              <div key={`${n.strike}-${i}`} className="text-[11px]">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="mono font-bold text-slate-200">
                    {fmt(n.strike, 0)}
                  </span>
                  <span className="mono text-[10px] text-amber-300">
                    {fmtAbs(n.mag)}
                  </span>
                </div>
                <div className="relative h-2 bg-slate-800/60 rounded overflow-hidden flex">
                  {/* Put bar grows leftward from center */}
                  <div className="w-1/2 flex justify-end">
                    <div
                      className="h-full bg-rose-400/70"
                      style={{ width: `${Math.max(2, pw * 2)}%` }}
                    />
                  </div>
                  {/* Call bar grows rightward from center */}
                  <div className="w-1/2 flex justify-start">
                    <div
                      className="h-full bg-emerald-400/70"
                      style={{ width: `${Math.max(2, cw * 2)}%` }}
                    />
                  </div>
                  {/* Center divider */}
                  <div className="absolute top-0 bottom-0 left-1/2 w-px bg-slate-600/60" />
                </div>
                <div className="flex justify-between text-[9px] mono mt-0.5">
                  <span className="text-rose-400">
                    put {fmtAbs(n.put_gex)}
                  </span>
                  <span className="text-emerald-400">
                    call {fmtAbs(n.call_gex)}
                  </span>
                </div>
              </div>
            );
          })}
          <div className="text-[9px] text-slate-600 italic">
            Two-sided dealer footprint.
          </div>
        </div>
      )}
    </div>
  );
}
