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

// ============ Mini Bar Chart ============
function MiniBar({ value, max, color = "teal", label }) {
  const pct = max > 0 ? Math.min(100, Math.abs(value) / max * 100) : 0;
  const barColor = color === "teal" ? "bg-teal-500/60" : color === "rose" ? "bg-rose-500/60" : color === "amber" ? "bg-amber-500/60" : "bg-sky-500/60";
  return (
    <div className="flex items-center gap-1 text-[8px]">
      <span className="text-slate-500 w-12 text-right truncate">{label}</span>
      <div className="flex-1 h-1.5 bg-slate-800 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="mono text-slate-400 w-10 text-right">{typeof value === "number" ? value.toFixed(2) : value}</span>
    </div>
  );
}

// ============ Market Regime Panel ============
export function MarketRegimePanel({ data }) {
  if (!data?.market_regime) return null;
  const mr = data.market_regime;
  const regimeColor = mr.regime === "calm" ? "text-emerald-400" : mr.regime === "normal" ? "text-sky-400" : mr.regime === "stressed" ? "text-amber-400" : "text-rose-400";
  const regimeBg = mr.regime === "calm" ? "bg-emerald-500/10 border-emerald-500/30" : mr.regime === "normal" ? "bg-sky-500/10 border-sky-500/30" : mr.regime === "stressed" ? "bg-amber-500/10 border-amber-500/30" : "bg-rose-500/10 border-rose-500/30";

  return (
    <Section title="Regime" badge={mr.regime?.toUpperCase()}>
      <div className={`text-[9px] p-1.5 rounded border ${regimeBg} mb-1.5`}>
        <div className={`font-bold text-[11px] ${regimeColor}`}>{mr.regime?.toUpperCase()}</div>
        <div className="text-slate-400 mt-0.5">{mr.interpretation?.fear_greed?.replace("_", " ")} · {mr.interpretation?.tail_risk} tails</div>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
        <div className="flex justify-between"><span className="text-slate-500">ATM IV</span><span className="mono text-slate-300">{(mr.atm_iv * 100).toFixed(1)}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Skew</span><span className={`mono ${mr.skew > 0.02 ? "text-rose-400" : mr.skew < -0.02 ? "text-emerald-400" : "text-slate-300"}`}>{(mr.skew * 100).toFixed(2)}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Daily Move</span><span className="mono text-slate-300">±{mr.expected_daily_spot_move_pct}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Vol of Vol</span><span className="mono text-slate-300">{(mr.implied_vol_of_vol * 100).toFixed(1)}%</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Spot-Vol ρ</span><span className="mono text-slate-300">{mr.implied_spot_vol_corr.toFixed(2)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Curvature</span><span className="mono text-slate-300">{(mr.curvature * 100).toFixed(2)}%</span></div>
      </div>
    </Section>
  );
}

// ============ Implied PDF Panel ============
export function ImpliedPDFPanel({ data }) {
  if (!data?.implied_pdf?.strike_probabilities?.length) return null;
  const pdf = data.implied_pdf;
  const probs = pdf.strike_probabilities.filter(p => p.probability > 0);
  if (!probs.length) return null;

  const maxProb = Math.max(...probs.map(p => p.probability));
  const spot = data.spot;

  // Find the mode bar
  const modeBar = probs.reduce((a, b) => a.probability > b.probability ? a : b);

  return (
    <Section title="Implied PDF" badge={pdf.expiry?.slice(5)}>
      <div className="text-[9px] p-1.5 rounded bg-slate-800/50 border border-slate-700/50 mb-1.5">
        <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
          <div><span className="text-slate-500">Mode: </span><span className="mono text-amber-300 font-bold">{fmt(pdf.most_likely_price, 0)}</span></div>
          <div><span className="text-slate-500">Median: </span><span className="mono text-slate-300">{fmt(pdf.median_price, 0)}</span></div>
          <div><span className="text-slate-500">E[Move]: </span><span className="mono text-slate-300">±{pdf.expected_move_pct}%</span></div>
          <div><span className="text-slate-500">Skew: </span><span className={`mono ${pdf.interpretation?.skew === "bullish" ? "text-emerald-400" : pdf.interpretation?.skew === "bearish" ? "text-rose-400" : "text-slate-300"}`}>{pdf.interpretation?.skew}</span></div>
          <div><span className="text-slate-500">P(≤spot): </span><span className="mono text-slate-300">{(pdf.cumulative_below_spot * 100).toFixed(1)}%</span></div>
          <div><span className="text-slate-500">P(1σ): </span><span className="mono text-slate-300">{(pdf.prob_within_1sd * 100).toFixed(1)}%</span></div>
        </div>
      </div>
      {/* Mini PDF chart */}
      <div className="space-y-0.5 max-h-24 overflow-y-auto">
        {probs.slice(0, 20).map((p, i) => (
          <MiniBar key={i} value={p.probability} max={maxProb} label={fmt(p.strike, 0)} color={p.strike >= spot ? "teal" : "rose"} />
        ))}
      </div>
      <div className="text-[8px] text-slate-600 mt-1">Risk-neutral density · {pdf.interpretation?.conviction} conviction</div>
    </Section>
  );
}

// ============ Hedge Impulse Panel ============
export function HedgeImpulsePanel({ data }) {
  if (!data?.hedge_impulse?.curve?.length) return null;
  const hi = data.hedge_impulse;
  const spot = data.spot;

  const regimeColor = hi.regime === "pinned" ? "text-emerald-400" : hi.regime === "expansion" ? "text-rose-400" : hi.regime === "squeeze-up" ? "text-sky-400" : hi.regime === "squeeze-down" ? "text-amber-400" : "text-slate-400";

  // Find impulse range for scaling
  const impulses = hi.curve.map(p => p.impulse).filter(v => v != null && !isNaN(v));
  const maxImp = Math.max(...impulses.map(Math.abs), 1);

  return (
    <Section title="Hedge Impulse" badge={hi.regime}>
      <div className={`text-[9px] p-1.5 rounded border mb-1.5 ${hi.regime === "pinned" ? "bg-emerald-500/10 border-emerald-500/30" : hi.regime === "expansion" ? "bg-rose-500/10 border-rose-500/30" : "bg-slate-800/50 border-slate-700/50"}`}>
        <div className={`font-bold ${regimeColor}`}>{hi.regime?.replace("-", " ").toUpperCase()}</div>
        <div className="text-slate-400 mt-0.5">
          {hi.regime === "pinned" ? "Strong mean-reversion at spot" : hi.regime === "expansion" ? "Negative gamma — breakout likely" : hi.regime === "squeeze-up" ? "Upside acceleration bias" : hi.regime === "squeeze-down" ? "Downside acceleration bias" : "Mixed signals"}
        </div>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px] mb-1">
        <div className="flex justify-between"><span className="text-slate-500">H(spot)</span><span className={`mono font-bold ${hi.impulse_at_spot > 0 ? "text-emerald-400" : "text-rose-400"}`}>{hi.impulse_at_spot?.toFixed(0) ?? "—"}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">k (coupling)</span><span className="mono text-slate-300">{hi.spot_vol_coupling?.toFixed(1)}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Attractor ↑</span><span className="mono text-emerald-400">{hi.nearest_attractor_above ? fmt(hi.nearest_attractor_above, 0) : "—"}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">Attractor ↓</span><span className="mono text-rose-400">{hi.nearest_attractor_below ? fmt(hi.nearest_attractor_below, 0) : "—"}</span></div>
      </div>
      {/* Mini impulse curve */}
      <div className="space-y-0.5 max-h-20 overflow-y-auto">
        {hi.curve.filter((_, i) => i % 2 === 0).map((p, i) => (
          <MiniBar key={i} value={p.impulse} max={maxImp} label={fmt(p.price, 0)} color={p.impulse >= 0 ? "teal" : "rose"} />
        ))}
      </div>
      <div className="text-[8px] text-slate-600 mt-1">H(S) = Γ(S) - (k/S)·V(S) · Positive = mean-reverting</div>
    </Section>
  );
}

// ============ Pressure Cloud Panel ============
export function PressureCloudPanel({ data }) {
  if (!data?.pressure_cloud) return null;
  const pc = data.pressure_cloud;

  const zones = [
    ...pc.stability_zones?.map(z => ({ ...z, type: "stability" })) || [],
    ...pc.acceleration_zones?.map(z => ({ ...z, type: "acceleration" })) || [],
  ].sort((a, b) => b.strength - a.strength);

  if (!zones.length && !pc.regime_edges?.length) return null;

  return (
    <Section title="Pressure Cloud" badge={`${zones.length}`}>
      <div className="space-y-1">
        {zones.slice(0, 4).map((z, i) => (
          <div key={i} className={`text-[9px] p-1 rounded border-l-2 ${z.type === "stability" ? "border-emerald-500 bg-emerald-500/5" : "border-rose-500 bg-rose-500/5"}`}>
            <div className="flex justify-between items-center">
              <span className={`font-bold ${z.type === "stability" ? "text-emerald-400" : "text-rose-400"}`}>
                {z.type === "stability" ? "STABILITY" : "ACCELERATION"}
              </span>
              <span className="text-slate-500">{z.side} · {(z.strength * 100).toFixed(0)}%</span>
            </div>
            <div className="flex gap-2 mt-0.5 text-[8px]">
              <span className="text-slate-500">center: <span className="mono text-slate-300">{fmt(z.center, 0)}</span></span>
              <span className="text-slate-500">trade: <span className={z.trade_type === "long" ? "text-emerald-400" : "text-rose-400"}>{z.trade_type}</span></span>
              <span className="text-slate-500">{z.hedge_type}</span>
            </div>
          </div>
        ))}
        {pc.regime_edges?.length > 0 && (
          <div className="text-[8px] text-slate-500 mt-1">
            Regime edges: {pc.regime_edges.map(e => fmt(e.price, 0)).join(", ")}
          </div>
        )}
      </div>
      <div className="text-[8px] text-slate-600 mt-1">Dealer hedge flow zones · Green = bounce · Red = momentum</div>
    </Section>
  );
}

// ============ Charm Integral Panel ============
export function CharmIntegralPanel({ data }) {
  if (!data?.charm_integral) return null;
  const ci = data.charm_integral;
  if (!ci.total_charm_to_close && ci.total_charm_to_close !== 0) return null;

  const dirColor = ci.direction === "buying" ? "text-emerald-400" : ci.direction === "selling" ? "text-rose-400" : "text-slate-400";

  return (
    <Section title="Charm Integral" badge={ci.expiry?.slice(5)}>
      <div className={`text-[9px] p-1.5 rounded border mb-1.5 ${ci.direction === "buying" ? "bg-emerald-500/10 border-emerald-500/30" : ci.direction === "selling" ? "bg-rose-500/10 border-rose-500/30" : "bg-slate-800/50 border-slate-700/50"}`}>
        <div className={`font-bold ${dirColor}`}>{ci.direction?.toUpperCase()}</div>
        <div className="text-slate-400 mt-0.5">Time decay pressure to close</div>
      </div>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
        <div className="flex justify-between"><span className="text-slate-500">Total</span><span className={`mono font-bold ${dirColor}`}>{ci.total_charm_to_close?.toFixed(0) ?? "—"}</span></div>
        <div className="flex justify-between"><span className="text-slate-500">DTE</span><span className="mono text-slate-300">{ci.days_remaining}d</span></div>
      </div>
      {ci.buckets?.length > 0 && (
        <div className="mt-1 space-y-0.5 max-h-16 overflow-y-auto">
          {ci.buckets.slice(0, 6).map((b, i) => (
            <MiniBar key={i} value={b.cumulative_charm} max={Math.abs(ci.total_charm_to_close) || 1} label={`${b.minutes_remaining}m`} color={b.cumulative_charm >= 0 ? "teal" : "rose"} />
          ))}
        </div>
      )}
      <div className="text-[8px] text-slate-600 mt-1">Cumulative charm exposure · Accelerates near expiry</div>
    </Section>
  );
}
