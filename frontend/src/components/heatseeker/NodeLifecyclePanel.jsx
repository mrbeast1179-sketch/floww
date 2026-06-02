import React from "react";
import { fmt, fmtAbs, tagFor } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 1 — GET /api/heatseeker/node-lifecycle
 * Renders the top 10 nodes with strike / GEX / taps / state / tap-probability.
 *
 * State colour mapping uses the existing .tag.fresh/.tested/.delivered/.decaying
 * CSS classes (defined in index.css) so chips match the rest of the app.
 */
function stateClass(state) {
  if (!state) return "tag";
  const key = String(state).toLowerCase();
  if (key.startsWith("fresh")) return tagFor("fresh");
  if (key.startsWith("test")) return tagFor("tested");
  if (key.startsWith("deliver")) return tagFor("delivered");
  if (key.startsWith("decay")) return tagFor("decaying");
  return "tag";
}

export default function NodeLifecyclePanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("node-lifecycle", { ticker });
  const nodes = (data?.nodes || []).slice(0, 10);

  return (
    <div className="panel p-3" data-testid="hs-node-lifecycle">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Node Lifecycle</div>
        <span className="text-[9px] text-slate-500">{nodes.length} of top-10</span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && nodes.length === 0 && (
        <div className="text-slate-500 text-[11px]">No lifecycle data.</div>
      )}
      {nodes.length > 0 && (
        <div className="overflow-y-auto" style={{ maxHeight: 260 }}>
          <table className="w-full text-[11px] mono">
            <thead className="text-slate-500 text-[9px] uppercase tracking-widest">
              <tr>
                <th className="text-left px-1 py-1">Strike</th>
                <th className="text-right px-1 py-1">Net γ</th>
                <th className="text-right px-1 py-1">Taps</th>
                <th className="text-left px-1 py-1">State</th>
                <th className="text-right px-1 py-1">Tap%</th>
              </tr>
            </thead>
            <tbody>
              {nodes.map((n, i) => {
                const tp = n.tap_probability;
                const tpPct = tp == null || isNaN(tp) ? "—" : `${Math.round(Number(tp))}%`;
                return (
                  <tr
                    key={`${n.strike}-${i}`}
                    className="border-t border-slate-800/60"
                  >
                    <td className="px-1 py-1 font-bold text-slate-200">
                      {fmt(n.strike, 0)}
                    </td>
                    <td
                      className={`px-1 py-1 text-right ${
                        (n.net_gex ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
                      }`}
                    >
                      {fmtAbs(n.net_gex)}
                    </td>
                    <td className="px-1 py-1 text-right text-slate-400">
                      {n.taps ?? "—"}
                    </td>
                    <td className="px-1 py-1">
                      <span className={stateClass(n.state)}>
                        {n.state || "—"}
                      </span>
                    </td>
                    <td className="px-1 py-1 text-right text-slate-300">{tpPct}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
