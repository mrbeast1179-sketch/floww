import React, { useEffect, useState } from "react";
import { fmt, fmtAbs } from "../lib/helpers";
import { BACKEND_URL, API } from "../config/api";

// API imported from config/api.js

export function MorningBriefing({ ticker, spot }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!ticker) return;
    let cancelled = false;
    setLoading(true);
    fetch(`${API}/daily-checklist/${ticker}?expiries=4`)
      .then(r => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(d => {
        if (!cancelled) setData(d);
      })
      .catch(() => {
        if (!cancelled) setData(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [ticker]);

  if (loading && !data) return <div className="panel p-3 text-slate-500 text-xs flex items-center gap-1.5"><span className="inline-block w-2 h-2 rounded-full bg-slate-600 animate-pulse" />Loading morning briefing…</div>;
  if (!data) return <div className="panel p-3 text-slate-500 text-xs">No briefing data available</div>;

  const safeTime = data?.asof ? new Date(data.asof).toLocaleTimeString() : "—";
  const safeRegimeDesc = data?.strategy?.regime_description ?? "";
  const safePositionNote = data?.strategy?.position_sizing_note ?? "";
  const regime = data?.regime?.gex_regime || "unknown";
  const isPositive = regime === "positive_gamma";
  const isNegative = regime === "negative_gamma";
  const regimeColor = isPositive ? "text-emerald-400" : isNegative ? "text-rose-400" : "text-slate-400";
  const regimeBg = isPositive ? "bg-emerald-500/10 border-emerald-500/30" : isNegative ? "bg-rose-500/10 border-rose-500/30" : "bg-slate-800/50 border-slate-700/50";

  return (
    <div className="panel p-3 space-y-3">
      <div className="flex items-center justify-between">
        <div className="label mb-0">Morning Briefing</div>
        <div className="text-[9px] text-slate-500">{safeTime}</div>
      </div>

      {/* Regime Banner */}
      <div className={`p-2 rounded border ${regimeBg}`}>
        <div className={`font-bold text-sm ${regimeColor}`}>
          {isPositive ? "🟢 POSITIVE GAMMA" : isNegative ? "🔴 NEGATIVE GAMMA" : "⚪ UNKNOWN"}
        </div>
        {safeRegimeDesc && <div className="text-[10px] text-slate-400 mt-0.5">{safeRegimeDesc}</div>}
      </div>

      {/* Key Levels */}
      <div>
        <div className="label mb-1">Key Levels</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Gamma Flip</span>
            <span className={`mono font-bold ${data?.key_levels?.dist_to_flip != null && data.key_levels.dist_to_flip < 0 ? "text-rose-400" : "text-emerald-400"}`}>
              {data?.key_levels?.gamma_flip != null ? fmt(data.key_levels.gamma_flip, 0) : "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">vs Flip</span>
            <span className={`mono ${data?.key_levels?.dist_to_flip != null && data.key_levels.dist_to_flip < 0 ? "text-rose-400" : "text-emerald-400"}`}>
              {data?.key_levels?.dist_to_flip != null ? `${data.key_levels.dist_to_flip > 0 ? "+" : ""}${data.key_levels.dist_to_flip} pts` : "—"}
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Call Wall</span>
            <span className="mono text-rose-400">{data?.key_levels?.call_wall != null ? fmt(data.key_levels.call_wall, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Put Wall</span>
            <span className="mono text-emerald-400">{data?.key_levels?.put_wall != null ? fmt(data.key_levels.put_wall, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Max Pain</span>
            <span className="mono text-amber-400">{data?.key_levels?.max_pain != null ? fmt(data.key_levels.max_pain, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Spot</span>
            <span className="mono text-slate-200">{spot != null ? fmt(spot, 2) : "—"}</span>
          </div>
        </div>
      </div>

      {/* Strategy */}
      <div>
        <div className="label mb-1">Strategy</div>
        <div className="text-[10px] text-slate-300 space-y-0.5">
          {data?.strategy?.recommended_strategies?.map((s, i) => (
            <div key={i} className="flex gap-1">
              <span className="text-slate-500">•</span>
              <span>{s}</span>
            </div>
          ))}
        </div>
        {data?.strategy?.warning && (
          <div className="mt-1 text-[10px] text-amber-400 bg-amber-500/10 rounded px-2 py-1 border border-amber-500/20">
            ⚠️ {data.strategy.warning}
          </div>
        )}
        {data?.strategy?.skew_note && (
          <div className="mt-1 text-[9px] text-slate-500 italic">{data.strategy.skew_note}</div>
        )}
      </div>

      {/* Position Sizing */}
      {safePositionNote && (
        <div>
          <div className="label mb-1">Position Sizing</div>
          <div className="text-[10px] text-slate-400 bg-slate-800/50 rounded px-2 py-1 border border-slate-700/50">
            {safePositionNote}
          </div>
        </div>
      )}

      {/* Risk Levels */}
      <div>
        <div className="label mb-1">Risk Levels</div>
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[10px]">
          <div className="flex justify-between">
            <span className="text-slate-500">R1</span>
            <span className="mono text-rose-400">{data?.risk_management?.resistance?.R1 != null ? fmt(data.risk_management.resistance.R1, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">S1</span>
            <span className="mono text-emerald-400">{data?.risk_management?.support?.S1 != null ? fmt(data.risk_management.support.S1, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">R2</span>
            <span className="mono text-rose-400">{data?.risk_management?.resistance?.R2 != null ? fmt(data.risk_management.resistance.R2, 0) : "—"}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">S2</span>
            <span className="mono text-emerald-400">{data?.risk_management?.support?.S2 != null ? fmt(data.risk_management.support.S2, 0) : "—"}</span>
          </div>
        </div>
        {data?.risk_management?.stop_suggestion?.below_put_wall != null && (
          <div className="mt-1 text-[9px] text-slate-500">
            Stop below put wall: <span className="mono text-rose-400">{fmt(data.risk_management.stop_suggestion.below_put_wall, 0)}</span>
          </div>
        )}
      </div>

      {/* Pre-Market Checklist */}
      <div>
        <div className="label mb-1">Pre-Market Checklist</div>
        <div className="bg-slate-800/40 rounded p-2 border border-slate-700/40 space-y-1">
          <CheckItem label="GEX regime identified" done={!!data?.regime?.gex_regime && data.regime.gex_regime !== "unknown"} />
          <CheckItem label="Gamma flip level noted" done={data?.key_levels?.gamma_flip != null} />
          <CheckItem label="Call/Put walls confirmed" done={data?.key_levels?.call_wall != null && data?.key_levels?.put_wall != null} />
          <CheckItem label="Max pain identified" done={data?.key_levels?.max_pain != null} />
          <CheckItem label="Strategy selected" done={data?.strategy?.recommended_strategies?.length > 0} />
          <CheckItem label="Position size calculated" done={data?.strategy?.position_sizing_note != null && data?.strategy?.position_sizing_note !== ""} />
          <CheckItem label="Stop loss set" done={data?.risk_management?.stop_suggestion?.below_put_wall != null} />
          <CheckItem label="Risk/reward ≥ 1:2" done={(() => {
            const s = data?.strategy?.recommended_strategies || [];
            return s.some(str => str.toLowerCase().includes("defined") || str.toLowerCase().includes("spread") || str.toLowerCase().includes("condor"));
          })()} />
        </div>
      </div>
    </div>
  );
}

function CheckItem({ label, done }) {
  return (
    <div className="flex items-center gap-1.5 text-[9px]">
      <span className={`w-3 h-3 rounded-sm border flex items-center justify-center text-[7px] flex-shrink-0 ${done ? "bg-emerald-500/20 border-emerald-500/50 text-emerald-400" : "border-slate-600 text-slate-600"}`}>
        {done ? "✓" : ""}
      </span>
      <span className={done ? "text-slate-300" : "text-slate-500"}>{label}</span>
    </div>
  );
}
