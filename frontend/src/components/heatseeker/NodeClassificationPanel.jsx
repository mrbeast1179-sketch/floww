import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — Node Classification.
 * Classifies nodes as real (growing intent) vs hedge (fading protection).
 */
function classBadgeStyle(c) {
  if (c === "real") return { text: "text-emerald-300", bg: "bg-emerald-500/10", border: "border-emerald-500/40", label: "REAL" };
  if (c === "hedge") return { text: "text-amber-300", bg: "bg-amber-500/10", border: "border-amber-500/40", label: "HEDGE" };
  return { text: "text-slate-400", bg: "bg-slate-700/30", border: "border-slate-600/40", label: "?" };
}

function NodeRow({ n }) {
  const s = classBadgeStyle(n.classification);
  const tp = n.tap_probability;
  const tpPct = tp == null || isNaN(tp) ? "—" : `${Math.round(Number(tp))}%`;
  return (
    <div className="flex items-center justify-between text-xs border-t border-slate-800/40 py-1.5 first:border-t-0">
      <div className="flex items-center gap-2">
        <span className={`text-[9px] mono uppercase tracking-widest rounded border px-1.5 py-0.5 font-bold ${s.text} ${s.bg} ${s.border}`}>
          {s.label}
        </span>
        <span className="mono font-bold text-slate-200">${fmt(n.strike, 0)}</span>
      </div>
      <div className="flex items-center gap-3">
        <span className={`mono text-[11px] font-bold ${(n.net_gex ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"}`}>
          γ {fmtAbs(n.net_gex)}
        </span>
        <span className="mono text-[10px] text-slate-400">{tpPct}</span>
      </div>
    </div>
  );
}

export default function NodeClassificationPanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("node-classification", { ticker });

  const { realNodes, hedgeNodes, unknownNodes } = useMemo(() => {
    const nodes = data?.nodes || [];
    return {
      realNodes: nodes.filter(n => n.classification === "real"),
      hedgeNodes: nodes.filter(n => n.classification === "hedge"),
      unknownNodes: nodes.filter(n => n.classification === "unknown" || !n.classification),
    };
  }, [data]);

  const hasAny = realNodes.length > 0 || hedgeNodes.length > 0 || unknownNodes.length > 0;

  return (
    <div className="rounded-xl border border-slate-700/30 bg-slate-800/20 p-3" data-testid="hs-node-classification">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2">
          <span className="text-sm">🏷️</span>
          <span className="text-xs font-semibold text-slate-200">Node Classification</span>
        </div>
        <span className="text-[10px] text-slate-500">
          {data?.real_count ?? 0}R · {data?.hedge_count ?? 0}H
        </span>
      </div>
      {loading && !data && <div className="text-slate-500 text-xs">Loading…</div>}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {!hasAny && data && <div className="text-slate-500 text-xs py-2 text-center">No classified nodes</div>}
      {hasAny && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <div className="text-emerald-400 font-semibold text-xs mb-1">Real ({realNodes.length})</div>
            <div className="text-[10px] text-slate-500 mb-1.5">positive γ · growing OI</div>
            {realNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>{realNodes.map((n, i) => <NodeRow key={`real-${n.strike}-${i}`} n={n} />)}</div>
            )}
          </div>
          <div>
            <div className="text-amber-400 font-semibold text-xs mb-1">Hedge ({hedgeNodes.length})</div>
            <div className="text-[10px] text-slate-500 mb-1.5">negative γ · fading OI</div>
            {hedgeNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>{hedgeNodes.map((n, i) => <NodeRow key={`hedge-${n.strike}-${i}`} n={n} />)}</div>
            )}
          </div>
          <div>
            <div className="text-slate-400 font-semibold text-xs mb-1">Unknown ({unknownNodes.length})</div>
            <div className="text-[10px] text-slate-500 mb-1.5">unclassified</div>
            {unknownNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>{unknownNodes.map((n, i) => <NodeRow key={`unk-${n.strike}-${i}`} n={n} />)}</div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
