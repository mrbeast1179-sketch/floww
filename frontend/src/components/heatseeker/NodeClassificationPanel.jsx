import React, { useMemo } from "react";
import { fmt, fmtAbs } from "../../lib/helpers";
import { useHeatseeker } from "../../hooks/useHeatseeker";

/**
 * Wave 3 — GET /api/heatseeker/node-classification
 * Returns:
 *   { ticker, spot, nodes, real_count, hedge_count }
 *
 * Each node carries:
 *   { strike, net_gex, taps, state, tap_probability,
 *     gamma_sign, oi_trend, classification }
 *
 * classification ∈ {"real", "hedge", "unknown"}
 *   real  → emerald (growing dealer intent — positive gamma + growing OI)
 *   hedge → amber  (fading protection — negative gamma + fading OI)
 *
 * Confidence proxy: tap_probability% (already encoded by lifecycle stage).
 */
function classBadgeStyle(c) {
  if (c === "real") {
    return {
      text: "text-emerald-300",
      bg: "bg-emerald-500/10",
      border: "border-emerald-500/40",
      label: "REAL",
    };
  }
  if (c === "hedge") {
    return {
      text: "text-amber-300",
      bg: "bg-amber-500/10",
      border: "border-amber-500/40",
      label: "HEDGE",
    };
  }
  return {
    text: "text-slate-400",
    bg: "bg-slate-700/30",
    border: "border-slate-600/40",
    label: "?",
  };
}

function NodeRow({ n }) {
  const s = classBadgeStyle(n.classification);
  const tp = n.tap_probability;
  const tpPct =
    tp == null || isNaN(tp) ? "—" : `${Math.round(Number(tp))}%`;
  return (
    <div className="flex items-center justify-between text-[11px] border-t border-slate-800/60 py-1 first:border-t-0">
      <div className="flex items-center gap-2">
        <span
          className={`text-[9px] mono uppercase tracking-widest rounded border px-1 py-[1px] ${s.text} ${s.bg} ${s.border}`}
        >
          {s.label}
        </span>
        <span className="mono font-bold text-slate-200">
          {fmt(n.strike, 0)}
        </span>
      </div>
      <div className="flex items-center gap-3">
        <span
          className={`mono text-[10px] ${
            (n.net_gex ?? 0) >= 0 ? "text-emerald-400" : "text-rose-400"
          }`}
        >
          γ {fmtAbs(n.net_gex)}
        </span>
        <span className="mono text-[10px] text-slate-400">{tpPct}</span>
      </div>
    </div>
  );
}

export default function NodeClassificationPanel({ ticker = "SPY" }) {
  const { data, loading, error } = useHeatseeker("node-classification", {
    ticker,
  });

  const { realNodes, hedgeNodes, unknownNodes } = useMemo(() => {
    const nodes = data?.nodes || [];
    return {
      realNodes: nodes.filter((n) => n.classification === "real"),
      hedgeNodes: nodes.filter((n) => n.classification === "hedge"),
      unknownNodes: nodes.filter((n) => n.classification === "unknown" || !n.classification),
    };
  }, [data]);

  return (
    <div className="panel p-3" data-testid="hs-node-classification">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Node Classification</div>
        <span className="text-[9px] text-slate-500">
          {data?.real_count ?? 0}r · {data?.hedge_count ?? 0}h
        </span>
      </div>
      {loading && !data && (
        <div className="text-slate-500 text-[11px]">Loading…</div>
      )}
      {error && <div className="text-rose-400 text-[10px]">Error: {error}</div>}
      {data && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-2">
          <div>
            <div className="label text-emerald-400 mb-1">
              Real ({realNodes.length})
            </div>
            <div className="text-[9px] text-slate-600 mb-1">
              positive γ · growing OI
            </div>
            {realNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>
                {realNodes.map((n, i) => (
                  <NodeRow key={`real-${n.strike}-${i}`} n={n} />
                ))}
              </div>
            )}
          </div>
          <div>
            <div className="label text-amber-400 mb-1">
              Hedge ({hedgeNodes.length})
            </div>
            <div className="text-[9px] text-slate-600 mb-1">
              negative γ · fading OI
            </div>
            {hedgeNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>
                {hedgeNodes.map((n, i) => (
                  <NodeRow key={`hedge-${n.strike}-${i}`} n={n} />
                ))}
              </div>
            )}
          </div>
          <div>
            <div className="label text-slate-400 mb-1">
              Unknown ({unknownNodes.length})
            </div>
            <div className="text-[9px] text-slate-600 mb-1">
              unclassified
            </div>
            {unknownNodes.length === 0 ? (
              <div className="text-slate-600 text-[10px]">—</div>
            ) : (
              <div>
                {unknownNodes.map((n, i) => (
                  <NodeRow key={`unk-${n.strike}-${i}`} n={n} />
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
