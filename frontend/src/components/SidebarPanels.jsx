import React from "react";
import { fmt, fmtAbs } from "../lib/helpers";

// ============ Collapsible Section Wrapper ============
function Section({ title, children, defaultOpen = true, badge }) {
  const [open, setOpen] = React.useState(defaultOpen);
  return (
    <div className="panel-2 p-2">
      <button className="flex items-center justify-between w-full text-left" onClick={() => setOpen(!open)} style={{ background: "none", border: "none", padding: 0, cursor: "pointer" }}>
        <div className="label mb-0">{title}</div>
        <div className="flex items-center gap-1">
          {badge && <span className="text-[8px] px-1 py-px rounded bg-slate-700 text-slate-400">{badge}</span>}
          <span className="text-slate-500 text-[10px]">{open ? "▾" : "▸"}</span>
        </div>
      </button>
      {open && <div className="mt-1.5">{children}</div>}
    </div>
  );
}

// ============ Flip Zones Panel ============
export function FlipZonesPanel({ data }) {
  if (!data?.nodes) return null;
  const { spot, nodes } = data;
  return (
    <Section title="Flip Zones">
      <div className="flex gap-2 text-[10px] flex-wrap">
        {nodes.polarity_level && <FlipBadge label="GEX Flip" value={nodes.polarity_level} spot={spot} color="amber" />}
        {nodes.vex_flip && <FlipBadge label="VEX Flip" value={nodes.vex_flip} spot={spot} color="pink" />}
        {nodes.charm_flip && <FlipBadge label="Charm Flip" value={nodes.charm_flip} spot={spot} color="cyan" />}
        {nodes.max_pain && <FlipBadge label="Max Pain" value={nodes.max_pain} spot={spot} color="orange" />}
      </div>
    </Section>
  );
}

function FlipBadge({ label, value, spot, color }) {
  const pct = ((value - spot) / spot * 100).toFixed(2);
  const dotColor = color === "amber" ? "bg-amber-400/60" : color === "pink" ? "bg-pink-500/60" : color === "cyan" ? "bg-cyan-400/60" : "bg-orange-400/60";
  const textColor = color === "amber" ? "text-amber-300" : color === "pink" ? "text-pink-300" : color === "cyan" ? "text-cyan-300" : "text-orange-300";
  return (
    <div className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full ${dotColor}`} />
      <span className="text-slate-500">{label}:</span>
      <span className={`${textColor} font-bold mono`}>{fmt(value, 1)}</span>
      <span className="text-slate-600">({pct}%)</span>
    </div>
  );
}

// ============ Stacked Nodes Panel ============
export function StackedNodesPanel({ data }) {
  if (!data?.nodes?.stacked_nodes?.length) return null;
  return (
    <Section title="Stacked Nodes" badge={`${data.nodes.stacked_nodes.length}`}>
      <div className="space-y-0.5">
        {data.nodes.stacked_nodes.slice(0, 4).map((s, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[9px]">
            <span className="mono text-slate-300 w-12">{fmt(s.strike, 0)}</span>
            <div className="flex-1 flex gap-0.5 items-center h-2">
              <div className="h-full rounded-l bg-teal-500/70" style={{ width: `${s.call_pct * 100}%` }} />
              <div className="h-full rounded-r bg-purple-500/70" style={{ width: `${s.put_pct * 100}%` }} />
            </div>
            <span className="text-teal-400 w-6 text-right">{Math.round(s.call_pct * 100)}</span>
            <span className="text-purple-400 w-6 text-right">{Math.round(s.put_pct * 100)}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Tug of War Panel ============
export function TugOfWarPanel({ data }) {
  if (!data?.nodes?.tug_of_war?.length) return null;
  return (
    <Section title="Tug-of-War" badge={`${data.nodes.tug_of_war.length}`}>
      <div className="space-y-0.5">
        {data.nodes.tug_of_war.slice(0, 3).map((z, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[9px]">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
            <span className="mono text-slate-300">{fmt(z.low, 0)}–{fmt(z.high, 0)}</span>
            <span className="text-emerald-400">+{fmtAbs(z.positive)}</span>
            <span className="text-rose-400">{fmtAbs(z.negative)}</span>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Scenario Panel ============
export function ScenarioPanel({ data }) {
  if (!data?.nodes) return null;
  const { nodes, spot } = data;
  return (
    <Section title="Scenario">
      <div className="space-y-1">
        {nodes.regime === "positive" && <>
          <div className="text-[9px] text-sky-400 font-bold">◎ RANGE DAY</div>
          <div className="text-[8px] text-slate-400">Dealers dampen vol. Mean-reversion.</div>
          {nodes.king?.strike > spot && <div className="text-[8px] text-rose-400">▽ Ceiling at {fmt(nodes.king.strike, 0)}</div>}
          {nodes.king?.strike < spot && <div className="text-[8px] text-emerald-400">△ Floor at {fmt(nodes.king.strike, 0)}</div>}
        </>}
        {nodes.regime === "negative" && <>
          <div className="text-[9px] text-amber-400 font-bold">⚡ TREND DAY</div>
          <div className="text-[8px] text-slate-400">Dealers amplify moves. Momentum.</div>
        </>}
        {nodes.regime === "neutral" && <>
          <div className="text-[9px] text-orange-400 font-bold">⚠ WHIPSAW</div>
          <div className="text-[8px] text-slate-400">Mixed signals. Reduce size.</div>
        </>}
        {nodes.polarity_level && <div className="text-[8px] text-yellow-300">⟷ Flip at {fmt(nodes.polarity_level, 1)}</div>}
        {nodes.total_vega && Math.abs(nodes.total_vega) > 1e6 && <div className="text-[8px] text-slate-500">Vega: {fmtAbs(nodes.total_vega)}</div>}
        {nodes.put_call_ratio && <div className="text-[8px] text-slate-500">P/C Ratio: <span className={nodes.put_call_ratio > 1 ? "text-rose-400" : "text-emerald-400"}>{nodes.put_call_ratio.toFixed(2)}</span></div>}
      </div>
    </Section>
  );
}

// ============ Risk Dashboard Panel ============
export function RiskDashboardPanel({ data }) {
  if (!data?.nodes?.risk_metrics) return null;
  const rm = data.nodes.risk_metrics;
  return (
    <Section title="Risk Dashboard">
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
        <RiskMetric label="GCI" value={rm.gci.toFixed(3)} warn={rm.gci > 0.25} caution={rm.gci > 0.15} />
        <RiskMetric label="PGR" value={(rm.pgr * 100).toFixed(1) + "%"} warn={rm.pgr < 0.3} caution={rm.pgr < 0.5} invert />
        <RiskMetric label="GDW" value={fmtAbs(rm.gdw)} />
        <RiskMetric label="T-Amp" value={rm.time_amp + "x"} />
        <RiskMetric label="CAR Net" value={rm.car_net.toFixed(1) + "M"} warn={rm.car_net < 0} invert />
        <RiskMetric label="CAR Gross" value={rm.car_gross.toFixed(1) + "M"} caution />
        <RiskMetric label="Charm Risk" value={rm.charm_risk.toFixed(1) + "M"} warn={Math.abs(rm.charm_risk) > 50} />
        <RiskMetric label="Vomma" value={fmtAbs(data?.nodes?.total_vomma)} />
      </div>
      <div className="mt-1.5 text-[8px] text-slate-600 leading-tight">GCI: gamma concentration. PGR: protective gamma near spot. CAR: convexity acceleration risk.</div>
    </Section>
  );
}

function RiskMetric({ label, value, warn, caution, invert }) {
  const color = invert ? (warn ? "text-emerald-400" : caution ? "text-amber-400" : "text-rose-400") : (warn ? "text-rose-400" : caution ? "text-amber-400" : "text-slate-300");
  return (
    <div className="flex justify-between">
      <span className="text-slate-500">{label}</span>
      <span className={`mono font-bold ${color}`}>{value}</span>
    </div>
  );
}

// ============ Opportunities Panel ============
export function OpportunitiesPanel({ data }) {
  if (!data?.opportunities?.length) return null;
  return (
    <Section title="Opportunities" badge={`${data.opportunities.length}`}>
      <div className="space-y-1.5">
        {data.opportunities.slice(0, 5).map((o, i) => (
          <div key={i} className={`text-[9px] p-1.5 rounded border-l-2 ${o.direction === "bullish" ? "border-emerald-500 bg-emerald-500/5" : o.direction === "bearish" ? "border-rose-500 bg-rose-500/5" : "border-amber-500 bg-amber-500/5"}`}>
            <div className="flex justify-between items-center">
              <span className="font-bold text-slate-200">{o.name}</span>
              <span className={`mono text-[8px] px-1 py-px rounded ${o.risk === "high" ? "bg-rose-500/20 text-rose-400" : o.risk === "medium" ? "bg-amber-500/20 text-amber-400" : "bg-emerald-500/20 text-emerald-400"}`}>{o.risk}</span>
            </div>
            <div className="text-slate-400 mt-0.5">{o.description}</div>
            <div className="flex gap-2 mt-0.5 text-[8px]">
              <span className="text-slate-500">conf: <span className="text-slate-300 mono">{(o.confidence * 100).toFixed(0)}%</span></span>
              {o.entry && <span className="text-slate-500">entry: <span className="text-slate-300 mono">${o.entry[0]}–${o.entry[1]}</span></span>}
              {o.target && <span className="text-slate-500">target: <span className="text-emerald-400 mono">${fmt(o.target, 0)}</span></span>}
              {o.stop && <span className="text-slate-500">stop: <span className="text-rose-400 mono">${fmt(o.stop, 0)}</span></span>}
            </div>
          </div>
        ))}
      </div>
    </Section>
  );
}

// ============ Implied Move Panel ============
export function ImpliedMovePanel({ data }) {
  if (!data?.implied_move) return null;
  const im = data.implied_move;
  return (
    <Section title="Implied Move">
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
        <div className="flex justify-between"><span className="text-slate-500">Expected</span><span className="mono text-amber-300 font-bold">±{im.implied_move_pct}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Range</span><span className="mono text-slate-300">${fmt(im.lower_range, 1)}–${fmt(im.upper_range, 1)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">ATM Strike</span><span className="mono text-slate-300">{fmt(im.atm_strike, 0)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Avg IV</span><span className="mono text-slate-300">{(im.avg_iv * 100).toFixed(1)}%</span></div>
      </div>
      <div className="mt-1.5 h-2 bg-slate-800 rounded-full overflow-hidden relative">
        <div className="absolute inset-y-0 left-1/2 w-0.5 bg-slate-500" />
        <div className="absolute inset-y-0 bg-amber-500/30 rounded-full" style={{ left: `${Math.max(0, 50 - im.implied_move_pct * 5)}%`, right: `${Math.max(0, 50 - im.implied_move_pct * 5)}%` }} />
      </div>
      <div className="text-[8px] text-slate-600 mt-1">Market expects ±{im.implied_move_pct}% move by nearest expiry</div>
    </Section>
  );
}

// ============ Vol Analytics Panel ============
export function VolAnalyticsPanel({ data }) {
  if (!data?.skew && !data?.iv_rank) return null;
  return (
    <Section title="Volatility">
      <div className="space-y-1.5">
        {data?.skew && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider">Skew</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
            <div className="flex justify-between"><span className="text-slate-500">ATM IV</span><span className="mono text-slate-300">{(data.skew.atm_iv * 100).toFixed(1)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">RR 25d</span><span className={`mono font-bold ${data.skew.interpretation?.risk_reversal === "bullish" ? "text-emerald-400" : data.skew.interpretation?.risk_reversal === "bearish" ? "text-rose-400" : "text-slate-300"}`}>{(data.skew.risk_reversal_25d * 100).toFixed(2)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Butterfly</span><span className="mono text-slate-300">{(data.skew.butterfly_25d * 100).toFixed(2)}%</span></div>
            <div className="flex justify-between"><span className="text-slate-500">Skew Slope</span><span className={`mono ${data.skew.interpretation?.skew_slope === "steep" ? "text-amber-400" : "text-slate-300"}`}>{data.skew.skew_slope.toFixed(2)}</span></div>
          </div>
        </>}
        {data?.iv_rank && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider mt-1">IV Rank / RV</div>
          <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
            <div className="flex justify-between"><span className="text-slate-500">IV Rank</span><span className={`mono font-bold ${data.iv_rank.interpretation === "expensive" ? "text-rose-400" : data.iv_rank.interpretation === "cheap" ? "text-emerald-400" : "text-amber-400"}`}>{data.iv_rank.iv_rank !== null ? (data.iv_rank.iv_rank * 100).toFixed(0) + "%" : "—"}</span></div>
            <div className="flex justify-between"><span className="text-slate-500">IV Pctl</span><span className="mono text-slate-300">{data.iv_rank.iv_percentile !== null ? (data.iv_rank.iv_percentile * 100).toFixed(0) + "%" : "—"}</span></div>
            {data.iv_rank.rv_close && <>
              <div className="flex justify-between"><span className="text-slate-500">RV 20d</span><span className="mono text-slate-300">{(data.iv_rank.rv_close * 100).toFixed(1)}%</span></div>
              <div className="flex justify-between"><span className="text-slate-500">RV-IV</span><span className={`mono font-bold ${(data.iv_rank.rv_iv_spread || 0) > 0.05 ? "text-rose-400" : (data.iv_rank.rv_iv_spread || 0) < -0.05 ? "text-emerald-400" : "text-slate-300"}`}>{(data.iv_rank.rv_iv_spread !== undefined ? (data.iv_rank.rv_iv_spread * 100).toFixed(1) + "%" : "—")}</span></div>
            </>}
          </div>
        </>}
        {data?.iv_surface?.term_structure?.length > 0 && <>
          <div className="text-[8px] text-slate-500 uppercase tracking-wider mt-1">Term Structure</div>
          <div className="flex gap-1 flex-wrap">
            {data.iv_surface.term_structure.slice(0, 6).map((ts, i) => (
              <div key={i} className="text-[8px] px-1.5 py-0.5 bg-slate-800 rounded"><span className="text-slate-500">{ts.dte}d</span> <span className="mono text-slate-300">{(ts.atm_iv * 100).toFixed(1)}%</span></div>
            ))}
          </div>
        </>}
      </div>
    </Section>
  );
}

// ============ Greek Reference Panel ============
export function GreekReferencePanel() {
  return (
    <Section title="Greek Reference" defaultOpen={false}>
      <details className="text-[9px]">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Gamma (∂Δ/∂S)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Rate of delta change. Highest ATM near expiry. Long γ = dealers hedge against market (stabilizing). Short γ = dealers hedge with market (destabilizing).</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vanna (∂Δ/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Delta sensitivity to IV changes. Long vanna = IV up → delta up (selling pressure). Short vanna = IV up → delta down (buying pressure).</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Charm (∂Δ/∂t)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Delta decay per day. For 0DTE, charm is extreme. Forces hedging flows as expiry approaches.</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vomma (∂V/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Vega sensitivity to vol changes. High vomma = option prices explode during vol spikes.</div>
      </details>
      <details className="text-[9px] mt-1">
        <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Zomma (∂Γ/∂σ)</summary>
        <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">Gamma sensitivity to vol changes. Vol spike → gamma increase → bigger hedging demand → more vol.</div>
      </details>
    </Section>
  );
}

// ============ Databento Usage Panel ============
export function UsagePanel() {
  const [usage, setUsage] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchUsage = async () => {
    setLoading(true);
    try {
      const base = process.env.REACT_APP_BACKEND_URL || "";
      const res = await axios.get(`${base}/api/databento/usage`);
      setUsage(res.data);
    } catch (e) { /* noop */ }
    setLoading(false);
  };

  return (
    <Section title="Data Usage" defaultOpen={false} badge={usage ? `$${usage.total_usd}` : undefined}>
      <button onClick={fetchUsage} className="btn w-full text-[9px] mb-1" disabled={loading}>
        {loading ? "…" : "Check Usage"}
      </button>
      {usage && (
        <div className="space-y-0.5 text-[9px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Total</span>
            <span className="mono font-bold text-slate-300">${usage.total_usd}</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">OI Fetches</span>
            <span className="mono text-slate-400">${usage.est_oi_cost_usd} ({usage.oi_fetch_count})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Live Tape</span>
            <span className="mono text-slate-400">${usage.est_tape_cost_usd} ({usage.tape_session_count})</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Credits Left</span>
            <span className="mono font-bold text-emerald-400">${usage.credits_remaining}</span>
          </div>
        </div>
      )}
    </Section>
  );
}
