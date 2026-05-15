import React, { useEffect, useMemo, useState, useCallback, useRef } from "react";
import axios from "axios";
import "@/App.css";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;
const REFRESH_MS = 30000;
const TRINITY = ["^SPX", "SPY", "QQQ"];
const DEFAULT_TICKERS = ["SPY", "QQQ", "^SPX", "IWM", "AAPL", "NVDA", "TSLA", "META", "AMZN", "MSFT"];

// ============ helpers ============
const fmt = (n, d = 2) => (n === null || n === undefined || isNaN(n)) ? "—" : Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
const fmtAbs = (n) => {
  if (n === null || n === undefined || isNaN(n)) return "—";
  const a = Math.abs(n);
  if (a >= 1e9) return (n / 1e9).toFixed(2) + "B";
  if (a >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(1) + "K";
  return n.toFixed(0);
};
const fmtCell = (v) => {
  if (v === null || v === undefined || isNaN(v) || v === 0) return "";
  const a = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  let s;
  if (a >= 1e6) s = (a / 1e6).toFixed(2) + "M";
  else if (a >= 1e3) s = (a / 1e3).toFixed(1) + "K";
  else s = a.toFixed(0);
  return sign + "$" + s;
};
const pctClass = (v) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";
const tagFor = (kind) => ({ king: "tag king", floor: "tag floor", ceiling: "tag ceiling", gate: "tag gate", air: "tag air", fresh: "tag fresh", tested: "tag tested", delivered: "tag delivered", decaying: "tag decaying" }[kind] || "tag");

function cellColor(v, maxAbs, isKing = false, mode = "gex") {
  if (!v || maxAbs === 0) return { bg: "rgba(15, 22, 32, 0.7)", text: "#5a6781" };
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  if (mode === "vex") {
    if (isKing && v > 0) return { bg: `rgba(251, 191, 36, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(219, 39, 119, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(245, 158, 11, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#fcd34d" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(219, 39, 119, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#f9a8d4" }; }
  }
  if (isKing && v > 0) return { bg: `rgba(190, 242, 100, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (isKing && v < 0) return { bg: `rgba(232, 121, 249, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
  if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(45, 212, 191, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a7f3d0" }; }
  else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
}

// ============ Scenario Matrix ============
function ScenarioMatrix({ data }) {
  if (!data?.nodes) return null;
  const { regime, polarity_level, king, vex_flip } = data.nodes;
  const spot = data.spot;
  const scenarios = [];
  if (regime === "positive") {
    scenarios.push({ label: "RANGE DAY", desc: "Dealers dampen volatility. Mean-reversion plays.", bias: "neutral", icon: "◎" });
    if (king && king.strike > spot) scenarios.push({ label: "CEILING CAP", desc: `Price capped near ${fmt(king.strike, 0)}. Fade rallies.`, bias: "bearish", icon: "▽" });
    if (king && king.strike < spot) scenarios.push({ label: "FLOOR SUPPORT", desc: `Support near ${fmt(king.strike, 0)}. Buy dips.`, bias: "bullish", icon: "△" });
  } else if (regime === "negative") {
    scenarios.push({ label: "TREND DAY", desc: "Dealers amplify moves. Momentum trades.", bias: "neutral", icon: "⟶" });
    scenarios.push({ label: "NEGATIVE GEX", desc: "Pro-cyclical hedging. Breakouts accelerate.", bias: "volatile", icon: "⚡" });
  } else {
    scenarios.push({ label: "WHIPSAW", desc: "Mixed signals. Reduce size or sit out.", bias: "caution", icon: "⚠" });
  }
  if (polarity_level) {
    const flipDist = ((polarity_level - spot) / spot * 100).toFixed(1);
    scenarios.push({ label: "GAMMA FLIP", desc: `Flip at ${fmt(polarity_level, 1)} (${flipDist}%). Regime change.`, bias: "key", icon: "⟷" });
  }
  if (vex_flip) {
    const vexDist = ((vex_flip - spot) / spot * 100).toFixed(1);
    scenarios.push({ label: "VEX FLIP", desc: `Vanna flip at ${fmt(vex_flip, 1)} (${vexDist}%).`, bias: "key", icon: "⟳" });
  }
  const biasColor = { bullish: "text-emerald-400 border-emerald-500/40", bearish: "text-rose-400 border-rose-500/40", neutral: "text-sky-400 border-sky-500/40", volatile: "text-amber-400 border-amber-500/40", caution: "text-orange-400 border-orange-500/40", key: "text-yellow-300 border-yellow-500/40" };
  return (
    <div className="panel p-3" data-testid="scenario-matrix">
      <div className="label mb-2">Scenario Matrix</div>
      <div className="space-y-1.5">
        {scenarios.map((s, i) => (
          <div key={i} className={`panel-2 p-2 border ${biasColor[s.bias] || "border-slate-700"}`}>
            <div className="flex items-center gap-1.5">
              <span className="text-xs">{s.icon}</span>
              <span className="text-[10px] font-bold tracking-wider uppercase">{s.label}</span>
            </div>
            <div className="text-[9px] text-slate-400 mt-0.5 leading-snug">{s.desc}</div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ Flip Zone Bar ============
function FlipZoneBar({ spot, polarityLevel, vexFlip }) {
  if (!polarityLevel && !vexFlip) return null;
  return (
    <div className="panel-2 p-2 mb-2 flex gap-4 text-[10px]" data-testid="flip-zone-bar">
      {polarityLevel && (
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-amber-400/60" />
          <span className="text-slate-500">GEX Flip:</span>
          <span className="text-amber-300 font-bold mono">{fmt(polarityLevel, 1)}</span>
          <span className="text-slate-600">({((polarityLevel - spot) / spot * 100).toFixed(2)}%)</span>
        </div>
      )}
      {vexFlip && (
        <div className="flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-pink-500/60" />
          <span className="text-slate-500">VEX Flip:</span>
          <span className="text-pink-300 font-bold mono">{fmt(vexFlip, 1)}</span>
          <span className="text-slate-600">({((vexFlip - spot) / spot * 100).toFixed(2)}%)</span>
        </div>
      )}
    </div>
  );
}

// ============ Stacked Nodes ============
function StackedNodes({ stacked }) {
  if (!stacked || stacked.length === 0) return null;
  return (
    <div className="panel-2 p-2 mb-2" data-testid="stacked-nodes">
      <div className="label mb-1">Stacked Nodes</div>
      <div className="space-y-0.5">
        {stacked.slice(0, 4).map((s, i) => (
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
    </div>
  );
}

// ============ Tug of War ============
function TugOfWar({ zones }) {
  if (!zones || zones.length === 0) return null;
  return (
    <div className="panel-2 p-2 mb-2" data-testid="tug-of-war">
      <div className="label mb-1">Tug-of-War</div>
      <div className="space-y-0.5">
        {zones.slice(0, 3).map((z, i) => (
          <div key={i} className="flex items-center gap-1.5 text-[9px]">
            <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
            <span className="mono text-slate-300">{fmt(z.low, 0)}–{fmt(z.high, 0)}</span>
            <span className="text-emerald-400">+{fmtAbs(z.positive)}</span>
            <span className="text-rose-400">{fmtAbs(z.negative)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

// ============ Grid Heatmap ============
function GridHeatmap({ data, filters, onCellClick, viewMode = "gex" }) {
  const spotRowRef = useRef(null);
  useEffect(() => { if (spotRowRef.current) spotRowRef.current.scrollIntoView({ block: "center", behavior: "auto" }); }, [data?.ticker, data?.mode]);
  if (!data?.grid) return <div className="text-slate-500 text-xs p-4">No grid data</div>;
  const { spot, grid, nodes } = data;
  const expiries = grid.expiries || [];
  let strikes = (grid.strikes || []).slice().sort((a, b) => b - a);
  if (filters?.side === "above") strikes = strikes.filter(s => s > spot);
  if (filters?.side === "below") strikes = strikes.filter(s => s < spot);

  const cellOf = (e, s) => { const g = grid.grid?.[e]; if (!g) return 0; return g[String(Number.isInteger(s) ? s : s)] ?? g[String(s)] ?? g[String(s.toFixed(1))] ?? g[String(parseInt(s))] ?? 0; };
  strikes = strikes.filter(s => expiries.some(e => Math.abs(cellOf(e, s)) > 0));

  // Also filter strikes by lifecycle
  const allStrikes = data.strikes || [];
  if (filters?.lifecycle && filters.lifecycle !== "all") {
    const allowedStrikes = new Set(allStrikes.filter(s => s.lifecycle === filters.lifecycle).map(s => s.strike));
    strikes = strikes.filter(s => allowedStrikes.has(s));
  }

  let maxAbs = 1;
  for (const e of expiries) for (const s of strikes) { const v = cellOf(e, s); if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v); }

  const kingStrike = nodes?.king?.strike;
  const floorSet = new Set((nodes?.floors || []).map(f => f.strike));
  const ceilSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const gkSet = new Set((nodes?.gatekeepers || []).map(f => f.strike));
  const inAir = (s) => (nodes?.air_pockets || []).some(a => s >= a.low && s <= a.high);
  const isStacked = (s) => (nodes?.stacked_nodes || []).some(n => n.strike === s);
  const spotIdx = strikes.findIndex(s => s <= spot);
  const flipStrike = nodes?.polarity_level;
  const flipIdx = flipStrike ? strikes.findIndex(s => s <= flipStrike) : -1;
  const expFmt = (e) => { try { const [, m, d] = e.split("-"); return `${m}-${d}`; } catch { return e; } };

  return (
    <div className="overflow-auto" data-testid="grid-heatmap" style={{ maxHeight: "65vh" }}>
      <table className="border-collapse mono text-[10px]">
        <thead className="sticky top-0 z-10" style={{ background: "var(--panel)" }}>
          <tr>
            <th className="px-2 py-1 text-left text-slate-500 sticky left-0 z-20" style={{ background: "var(--panel)" }}>Strike</th>
            {expiries.map((e) => (<th key={e} className="px-1.5 py-1 text-slate-400 font-normal" style={{ minWidth: 56 }}>{expFmt(e)}</th>))}
            <th className="px-1.5 py-1 text-slate-500 text-left">Tags</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((s, i) => {
            const isKing = s === kingStrike; const isFloor = floorSet.has(s); const isCeil = ceilSet.has(s); const isGate = gkSet.has(s); const airy = inAir(s); const stacked = isStacked(s);
            return (
              <React.Fragment key={s}>
                {i === spotIdx && (
                  <tr ref={spotRowRef}><td colSpan={expiries.length + 2} style={{ padding: 0 }}>
                    <div className="relative" style={{ height: 16 }}>
                      <div className="absolute inset-x-0 top-1/2" style={{ height: 1, background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)", boxShadow: "0 0 6px rgba(94,234,212,0.55)" }} />
                      <div className="absolute left-2 top-0 text-[9px] font-bold tracking-widest text-teal-300 px-1" style={{ background: "var(--panel)", textShadow: "0 0 6px rgba(94,234,212,0.6)" }}>◆ SPOT {fmt(spot, 2)}</div>
                    </div>
                  </td></tr>
                )}
                {i === flipIdx && flipStrike && s !== spot && (
                  <tr><td colSpan={expiries.length + 2} style={{ padding: 0 }}>
                    <div className="relative" style={{ height: 12 }}>
                      <div className="absolute inset-x-0 top-1/2" style={{ height: 1, borderTop: "1px dashed rgba(251,191,36,0.5)" }} />
                      <div className="absolute right-2 top-0 text-[8px] text-amber-400 px-1" style={{ background: "var(--panel)" }}>⟷ FLIP {fmt(flipStrike, 1)}</div>
                    </div>
                  </td></tr>
                )}
                <tr className={`bar-row ${airy ? "opacity-60" : ""}`} data-testid={`grid-row-${s}`}>
                  <td className={`px-1.5 py-0.5 font-bold sticky left-0 z-10 ${isKing ? "text-amber-300" : isFloor ? "text-emerald-400" : isCeil ? "text-rose-400" : isGate ? "text-sky-400" : stacked ? "text-amber-200" : "text-slate-400"}`} style={{ background: "var(--panel)" }}>
                    {fmt(s, s >= 1000 ? 0 : 1)}{stacked && <span className="ml-0.5 text-[7px]">⊕</span>}
                  </td>
                  {expiries.map((e) => {
                    const v = cellOf(e, s); const isKingCell = isKing && Math.abs(v) > 0.6 * maxAbs; const col = cellColor(v, maxAbs, isKingCell, viewMode);
                    return (<td key={e} className="px-0.5 py-0.5 text-center cursor-pointer hover:outline hover:outline-1 hover:outline-teal-400" style={{ background: col.bg, color: col.text, minWidth: 52 }} onClick={() => onCellClick && onCellClick(s, e, v)} title={`K=${s} exp=${e} ${viewMode}=${fmtCell(v)}`}>{fmtCell(v)}</td>);
                  })}
                  <td className="px-1.5 py-0.5"><div className="flex gap-0.5 items-center flex-wrap">
                    {isKing && <span className="tag king">K</span>}{isFloor && <span className="tag floor">FL</span>}{isCeil && <span className="tag ceiling">CE</span>}{isGate && <span className="tag gate">GK</span>}{airy && <span className="tag air">AIR</span>}{stacked && <span className="tag" style={{ color: "#fbbf24", borderColor: "rgba(251,191,36,0.4)", background: "rgba(251,191,36,0.07)" }}>ST</span>}
                  </div></td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============ Bar Heatmap - FIXED with proper scaling ============
function BarHeatmap({ data, filters, compact = true, viewMode = "gex" }) {
  if (!data?.strikes) return null;
  const { spot, strikes, nodes } = data;
  const key = viewMode === "vex" ? "vex" : "gex";

  // Filter strikes
  let filtered = strikes.filter((s) => {
    const val = s[key] || s.gex || 0;
    if (filters?.magMin && Math.abs(val) < filters.magMin) return false;
    if (filters?.lifecycle && filters.lifecycle !== "all" && s.lifecycle !== filters.lifecycle) return false;
    if (filters?.side === "above" && s.strike <= spot) return false;
    if (filters?.side === "below" && s.strike >= spot) return false;
    return true;
  });

  if (!filtered.length) return <div className="text-slate-500 text-xs p-2">No strikes match filters.</div>;

  const sorted = [...filtered].sort((a, b) => b.strike - a.strike);
  const maxAbs = Math.max(...filtered.map(s => Math.abs(s[key] || s.gex || 0)), 1);
  const king = nodes?.king?.strike;
  const fSet = new Set((nodes?.floors || []).map(f => f.strike));
  const cSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const rowH = compact ? 12 : 16;
  const flipStrike = nodes?.polarity_level;
  const barColorPos = viewMode === "vex" ? "rgba(245, 158, 11, 0.7)" : "rgba(45, 212, 191, 0.7)";
  const barColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.7)" : "rgba(168, 85, 247, 0.7)";
  const kingColorPos = viewMode === "vex" ? "rgba(251, 191, 36, 0.9)" : "rgba(190, 242, 100, 0.9)";
  const kingColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.85)" : "rgba(232, 121, 249, 0.85)";

  return (
    <div className="relative">
      {sorted.map((s, i) => {
        const val = s[key] || s.gex || 0;
        const isKing = s.strike === king; const isF = fSet.has(s.strike); const isC = cSet.has(s.strike);
        const pos = val > 0; const w = Math.max(2, (Math.abs(val) / maxAbs) * 45);
        const prev = sorted[i - 1];
        const showSpot = prev && prev.strike > spot && s.strike <= spot;
        const showFlip = flipStrike && prev && prev.strike > flipStrike && s.strike <= flipStrike;
        return (
          <React.Fragment key={s.strike}>
            {showSpot && (
              <div className="flex items-center my-0.5 px-1">
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
                <div className="px-1 text-[8px] tracking-widest text-teal-300">{fmt(spot, 1)}</div>
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
              </div>
            )}
            {showFlip && (
              <div className="flex items-center my-0.5 px-1">
                <div className="flex-1 h-px" style={{ borderTop: "1px dashed rgba(251,191,36,0.5)" }} />
                <div className="px-1 text-[7px] text-amber-400">FLIP</div>
                <div className="flex-1 h-px" style={{ borderTop: "1px dashed rgba(251,191,36,0.5)" }} />
              </div>
            )}
            <div className="bar-row flex items-center text-[9px] mono px-1" style={{ height: rowH }}>
              <div className="flex-1 flex justify-end pr-0.5" style={{ minWidth: 0 }}>
                {!pos && <div style={{ width: `${w}%`, height: 8, borderRadius: 2, background: isKing ? kingColorNeg : barColorNeg }} />}
              </div>
              <div className={`w-12 text-center ${isKing ? "text-amber-300 font-bold" : isF ? "text-emerald-400" : isC ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.strike, 0)}</div>
              <div className="flex-1 flex pl-0.5" style={{ minWidth: 0 }}>
                {pos && <div style={{ width: `${w}%`, height: 8, borderRadius: 2, background: isKing ? kingColorPos : barColorPos }} />}
              </div>
            </div>
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ============ Pattern Card ============
function PatternCard({ p }) {
  const biasColor = { bearish: "text-rose-400 border-rose-500/40", bullish: "text-emerald-400 border-emerald-500/40", reversion: "text-amber-300 border-amber-500/40", trap: "text-fuchsia-400 border-fuchsia-500/40", "do not trade": "text-slate-500 border-slate-600", resistance: "text-rose-400 border-rose-500/40", support: "text-emerald-400 border-emerald-500/40" }[p.bias] || "text-slate-300 border-slate-700";
  return (
    <div className={`panel-2 p-2 border ${biasColor}`} data-testid={`pattern-${p.name.toLowerCase().replace(/\s+/g, "-")}`}>
      <div className="flex justify-between items-baseline">
        <div className="text-[11px] font-bold tracking-wide uppercase">{p.name}</div>
        <div className="text-[9px] uppercase tracking-widest opacity-70">{p.bias}</div>
      </div>
      <div className="h-1 mt-1 mb-1 bg-slate-800 rounded"><div className="h-full rounded" style={{ width: `${(p.severity * 100).toFixed(0)}%`, background: "currentColor", opacity: 0.6 }} /></div>
      <div className="text-[10px] text-slate-400 leading-snug">{p.note}</div>
    </div>
  );
}

// ============ Velocity Gauge ============
function VelocityGauge({ velocity }) {
  if (!velocity) return null;
  const score = velocity.velocity_score || 0;
  const warming = (velocity.snapshots_count || 0) < 3;
  const angle = score * 180 - 90;
  const color = warming ? "#64748b" : score > 0.4 ? "#ef4444" : score > 0.2 ? "#fbbf24" : "#34d399";
  return (
    <div className="panel-2 p-2" data-testid="velocity-gauge">
      <div className="label mb-1">Velocity</div>
      <div className="flex items-center gap-2">
        <svg viewBox="0 0 100 60" width="80" height="48">
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="6" />
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={color} strokeWidth="6" strokeDasharray={`${score * 125} 200`} strokeLinecap="round" />
          <line x1="50" y1="55" x2={50 + 35 * Math.cos((angle - 90) * Math.PI / 180)} y2={55 + 35 * Math.sin((angle - 90) * Math.PI / 180)} stroke={color} strokeWidth="2" />
          <circle cx="50" cy="55" r="3" fill={color} />
        </svg>
        <div>
          <div className="text-lg font-bold mono" style={{ color }}>{warming ? "…" : (score * 100).toFixed(0)}</div>
          <div className="text-[8px] uppercase tracking-widest text-slate-500">{warming ? "warming" : "rate"}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-1 mt-1 text-[9px]">
        <div><div className="label">Floor</div><div className={velocity.rolling_floor === "rolling_up" ? "text-emerald-400" : velocity.rolling_floor === "rolling_down" ? "text-rose-400" : "text-slate-400"}>{(velocity.rolling_floor || "stable").replace("_", " ")}</div></div>
        <div><div className="label">Ceiling</div><div className={velocity.rolling_ceiling === "rolling_up" ? "text-emerald-400" : velocity.rolling_ceiling === "rolling_down" ? "text-rose-400" : "text-slate-400"}>{(velocity.rolling_ceiling || "stable").replace("_", " ")}</div></div>
      </div>
    </div>
  );
}

// ============ Top Movers ============
function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let mounted = true;
    const f = async () => { try { const res = await axios.get(`${API}/movers?limit=10`); if (mounted) setRows(res.data.results || []); } catch (e) { /* noop */ } };
    f(); const id = setInterval(f, 60000); return () => { mounted = false; clearInterval(id); };
  }, []);
  return (
    <div className="panel p-2" data-testid="movers-panel">
      <div className="label mb-1">Top Movers</div>
      <div className="flex flex-col gap-0.5 text-[10px]">
        {rows.length === 0 && <div className="text-slate-500">…</div>}
        {rows.map((r) => (
          <button key={r.ticker} data-testid={`mover-${r.ticker}`} onClick={() => onPick && onPick(r.ticker)} className="flex justify-between items-center px-1.5 py-0.5 hover:bg-slate-800/40 rounded">
            <span className="font-bold w-10 text-left">{r.ticker}</span>
            <span className="mono text-slate-400 w-16 text-right">${fmt(r.close, 2)}</span>
            <span className={`mono w-12 text-right ${pctClass(r.pct)}`}>{r.pct >= 0 ? "+" : ""}{r.pct}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ============ Nodes Table ============
function NodesTable({ data, viewMode = "gex" }) {
  const [sortKey, setSortKey] = useState("mag");
  const [sortDir, setSortDir] = useState("desc");
  if (!data?.nodes) return null;
  const spot = data.spot;
  const key = viewMode === "vex" ? "vex" : "gex";
  const all = (data.strikes || []).map((s) => {
    const role = s.strike === data.nodes.king?.strike ? "King" : data.nodes.floors?.some(f => f.strike === s.strike) ? "Floor" : data.nodes.ceilings?.some(f => f.strike === s.strike) ? "Ceiling" : data.nodes.gatekeepers?.some(f => f.strike === s.strike) ? "Gate" : null;
    return { ...s, role, mag: Math.abs(s[key] || s.gex || 0), val: s[key] || s.gex || 0, dist: Math.abs(s.strike - spot) / spot * 100 };
  }).filter(s => s.role || s.mag > 0);
  const sorted = [...all].sort((a, b) => { const va = a[sortKey], vb = b[sortKey]; if (va == null) return 1; if (vb == null) return -1; return sortDir === "desc" ? vb - va : va - vb; });
  const head = (k, l) => (<th className="text-left text-[9px] uppercase tracking-widest text-slate-500 font-normal px-1.5 py-0.5 cursor-pointer hover:text-teal-400" onClick={() => { setSortKey(k); setSortDir(d => sortKey === k && d === "desc" ? "asc" : "desc"); }}>{l}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}</th>);
  return (
    <div className="panel p-2" data-testid="nodes-table">
      <div className="label mb-1">Nodes {viewMode === "vex" ? "(VEX)" : "(GEX)"}</div>
      <div className="overflow-y-auto" style={{ maxHeight: 220 }}>
        <table className="w-full text-[10px] mono">
          <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
            <tr>{head("strike", "K")}<th className="text-left text-[9px] uppercase tracking-widest text-slate-500 font-normal px-1.5 py-0.5">R</th>{head("mag", "|V|")}{head("val", "Net")}{head("dist", "Δ%")}{head("taps", "T")}<th className="text-left text-[9px] uppercase tracking-widest text-slate-500 font-normal px-1.5 py-0.5">Life</th></tr>
          </thead>
          <tbody>
            {sorted.slice(0, 25).map((s) => (
              <tr key={s.strike} className="bar-row border-t border-slate-800/60">
                <td className="px-1.5 py-0.5 font-bold text-slate-200">{fmt(s.strike, 0)}</td>
                <td className="px-1.5 py-0.5">{s.role && <span className={`tag ${s.role === "King" ? "king" : s.role === "Floor" ? "floor" : s.role === "Ceiling" ? "ceiling" : "gate"}`}>{s.role[0]}</span>}</td>
                <td className="px-1.5 py-0.5 text-slate-300">{fmtAbs(s.mag)}</td>
                <td className={`px-1.5 py-0.5 ${s.val > 0 ? "text-emerald-400" : "text-rose-400"}`}>{s.val > 0 ? "+" : ""}{fmtAbs(s.val)}</td>
                <td className="px-1.5 py-0.5 text-slate-500">{s.dist.toFixed(1)}%</td>
                <td className="px-1.5 py-0.5 text-slate-500">{s.taps}</td>
                <td className="px-1.5 py-0.5"><span className={tagFor(s.lifecycle)}>{s.lifecycle}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============ Drilldown ============
function Drilldown({ ticker, expiry, strike, onClose }) {
  const [data, setData] = useState(null); const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!ticker) return; setLoading(true);
    const params = new URLSearchParams(); if (expiry) params.set("expiry", expiry); if (strike) params.set("strike", strike);
    axios.get(`${API}/contract/${encodeURIComponent(ticker)}?${params.toString()}`).then(r => setData(r.data)).catch(() => setData(null)).finally(() => setLoading(false));
  }, [ticker, expiry, strike]);
  if (!data && !loading) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div className="panel p-3 max-w-3xl w-[90%] max-h-[70vh] overflow-auto" onClick={(e) => e.stopPropagation()} data-testid="drilldown-modal">
        <div className="flex justify-between items-center mb-2">
          <div><div className="label">Drilldown</div><div className="text-sm font-bold">{ticker} {strike ? `· ${strike}` : ""} {expiry ? `· ${expiry}` : ""}</div></div>
          <button onClick={onClose} className="btn" data-testid="drilldown-close">✕</button>
        </div>
        {loading && <div className="text-slate-500">loading…</div>}
        {data && (<div>
          <div className="text-[10px] text-slate-500 mb-1">Spot {fmt(data.spot, 2)} · {data.count} contracts · {data.data_source}</div>
          {data.count === 0 ? <div className="text-slate-500 text-xs py-4 text-center">No contracts here.</div> : (
          <table className="w-full text-[10px] mono">
            <thead className="text-slate-500 text-[9px] uppercase tracking-widest"><tr><th className="text-left px-1.5 py-0.5">Type</th><th className="text-left px-1.5 py-0.5">K</th><th className="text-left px-1.5 py-0.5">Exp</th><th className="text-right px-1.5 py-0.5">OI</th><th className="text-right px-1.5 py-0.5">Vol</th><th className="text-right px-1.5 py-0.5">IV</th><th className="text-right px-1.5 py-0.5">GEX</th><th className="text-left px-1.5 py-0.5">Src</th></tr></thead>
            <tbody>{data.rows.map((r, i) => (
              <tr key={i} className="bar-row border-t border-slate-800/60">
                <td className={`px-1.5 py-0.5 ${r.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{r.type}</td>
                <td className="px-1.5 py-0.5 font-bold">{fmt(r.strike, 0)}</td>
                <td className="px-1.5 py-0.5 text-slate-400">{r.expiry}</td>
                <td className="px-1.5 py-0.5 text-right">{fmt(r.oi, 0)}</td>
                <td className="px-1.5 py-0.5 text-right text-slate-500">{fmt(r.volume, 0)}</td>
                <td className="px-1.5 py-0.5 text-right text-slate-400">{(r.iv * 100).toFixed(1)}%</td>
                <td className={`px-1.5 py-0.5 text-right ${r.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{fmtAbs(r.gex)}</td>
                <td className="px-1.5 py-0.5 text-[9px] text-slate-600">{r.oi_source}</td>
              </tr>
            ))}</tbody>
          </table>)}
        </div>)}
      </div>
    </div>
  );
}

// ============ Flowseeker with Demo Data ============
function Flowseeker({ ticker }) {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("idle");
  const [filter, setFilter] = useState({ unusual: false, sweep: false, block: false, side: "all" });
  const [sessionInfo, setSessionInfo] = useState(null);
  const [errMsg, setErrMsg] = useState(null);
  const [overrideWindow, setOverrideWindow] = useState(false);
  const [duration, setDuration] = useState(120);
  const [demoMode, setDemoMode] = useState(false);
  const esRef = useRef(null);
  const demoIntervalRef = useRef(null);

  // Generate demo flow events
  const generateDemoEvent = useCallback(() => {
    const strikes = [740, 742, 745, 748, 750, 752, 755];
    const types = ["call", "put"];
    const sides = ["B", "S"];
    const strike = strikes[Math.floor(Math.random() * strikes.length)];
    const type = types[Math.floor(Math.random() * types.length)];
    const size = Math.floor(Math.random() * 800) + 10;
    const price = (Math.random() * 10 + 0.5).toFixed(2);
    const notional = parseFloat(price) * size * 100;
    return {
      ts: Date.now() * 1e6,
      symbol: `${ticker}  260515${type === "call" ? "C" : "P"}${String(strike * 1000).padStart(8, "0")}`,
      underlying: ticker,
      strike, expiry: "2026-05-15", type,
      price: parseFloat(price), size,
      side: sides[Math.floor(Math.random() * sides.length)],
      notional,
      unusual: size >= 100 || notional >= 50000,
      sweep: size >= 250,
      block: size >= 500,
    };
  }, [ticker]);

  const startDemo = useCallback(() => {
    setStatus("live"); setEvents([]); setErrMsg(null); setSessionInfo({ session_id: "demo", auto_stop_at: new Date(Date.now() + duration * 1000).toISOString() });
    demoIntervalRef.current = setInterval(() => {
      setEvents(prev => [generateDemoEvent(), ...prev].slice(0, 250));
    }, 800 + Math.random() * 1200);
  }, [duration, generateDemoEvent]);

  const stopDemo = useCallback(() => {
    if (demoIntervalRef.current) { clearInterval(demoIntervalRef.current); demoIntervalRef.current = null; }
    setStatus("stopped");
  }, []);

  const start = useCallback(() => {
    if (esRef.current) return;
    // Try real connection first
    setStatus("connecting");
    setEvents([]); setErrMsg(null); setSessionInfo(null);
    const url = `${API}/flow/${encodeURIComponent(ticker)}?max_seconds=${duration}&enforce_window=${!overrideWindow}`;
    const es = new EventSource(url);
    esRef.current = es;
    es.addEventListener("ready", (e) => { try { setSessionInfo(JSON.parse(e.data)); } catch { /* noop */ } setStatus("live"); });
    es.addEventListener("end", () => { setStatus("ended"); es.close(); esRef.current = null; });
    es.addEventListener("warning", (e) => { try { const m = JSON.parse(e.data || "{}"); setErrMsg(m.hint || m.error); } catch { /* noop */ } setStatus("error"); es.close(); esRef.current = null; });
    es.addEventListener("error", (e) => { try { const m = JSON.parse(e.data || "{}"); if (m.error) setErrMsg(m.error); } catch { /* noop */ } setStatus("error"); es.close(); esRef.current = null; });
    es.onmessage = (ev) => { try { const msg = JSON.parse(ev.data); setEvents(prev => [msg, ...prev].slice(0, 250)); } catch { /* noop */ } };
    // If no event after 3s, switch to demo
    setTimeout(() => {
      if (status === "connecting") { es.close(); esRef.current = null; setDemoMode(true); startDemo(); }
    }, 3000);
  }, [ticker, duration, overrideWindow, startDemo, status]);

  const stop = useCallback(async () => {
    if (demoMode) { stopDemo(); return; }
    try { await axios.post(`${API}/live/tape/stop`); } catch { /* noop */ }
    esRef.current?.close(); esRef.current = null; setStatus("stopped");
  }, [demoMode, stopDemo]);

  useEffect(() => () => { esRef.current?.close(); if (demoIntervalRef.current) clearInterval(demoIntervalRef.current); }, []);

  const filtered = events.filter(e => {
    if (filter.unusual && !e.unusual) return false;
    if (filter.sweep && !e.sweep) return false;
    if (filter.block && !e.block) return false;
    if (filter.side !== "all") { if (filter.side === "calls" && e.type !== "call") return false; if (filter.side === "puts" && e.type !== "put") return false; }
    return true;
  });

  return (
    <div className="panel p-3" data-testid="flowseeker-panel">
      <div className="flex justify-between items-center mb-2">
        <div>
          <div className="label">Flowseeker · {demoMode ? "Demo Mode" : "Live OPRA"}</div>
          <div className="text-[10px] text-slate-500">{ticker} · <span className={status === "live" ? "text-teal-400" : status === "error" ? "text-rose-400" : "text-slate-400"}>{status}</span> · {filtered.length}/{events.length} trades</div>
          {errMsg && <div className="text-[10px] text-rose-400 mt-0.5">⚠ {errMsg}</div>}
          {demoMode && <div className="text-[9px] text-amber-400/70 mt-0.5">Demo mode — simulated flow data. Connect Databento Live for real data.</div>}
        </div>
        <div className="flex flex-col items-end gap-1">
          <div className="flex gap-1.5 items-center text-[9px] text-slate-500">
            <label className="flex items-center gap-1">dur
              <select data-testid="flow-duration" value={duration} onChange={e => setDuration(Number(e.target.value))} className="bg-slate-900 border border-slate-700 px-1 rounded text-slate-200" disabled={status === "live"}>
                <option value={60}>1m</option><option value={120}>2m</option><option value={300}>5m</option>
              </select>
            </label>
            <label className="flex items-center gap-1"><input type="checkbox" data-testid="flow-override-window" checked={overrideWindow} onChange={e => setOverrideWindow(e.target.checked)} disabled={status === "live"} />override</label>
            <label className="flex items-center gap-1"><input type="checkbox" checked={demoMode} onChange={e => { setDemoMode(e.target.checked); if (!e.target.checked && status === "live") stopDemo(); }} />demo</label>
          </div>
          <div className="flex gap-1.5">
            {status !== "live" && status !== "connecting" && (<button data-testid="flow-start" onClick={() => demoMode ? startDemo() : start()} className="btn">▶ start</button>)}
            {status === "live" && (<button data-testid="flow-stop" onClick={stop} className="btn">■ stop</button>)}
          </div>
        </div>
      </div>
      <div className="flex gap-1.5 mb-2 text-[10px] flex-wrap">
        <button data-testid="flow-filter-unusual" onClick={() => setFilter(f => ({ ...f, unusual: !f.unusual }))} className={`btn ${filter.unusual ? "active" : ""}`}>unusual</button>
        <button data-testid="flow-filter-sweep" onClick={() => setFilter(f => ({ ...f, sweep: !f.sweep }))} className={`btn ${filter.sweep ? "active" : ""}`}>sweep</button>
        <button data-testid="flow-filter-block" onClick={() => setFilter(f => ({ ...f, block: !f.block }))} className={`btn ${filter.block ? "active" : ""}`}>block</button>
        {["all", "calls", "puts"].map(s => (<button key={s} onClick={() => setFilter(f => ({ ...f, side: s }))} className={`btn ${filter.side === s ? "active" : ""}`}>{s}</button>))}
      </div>
      <div className="overflow-auto" style={{ maxHeight: "55vh" }}>
        <table className="w-full text-[9px] mono">
          <thead className="sticky top-0 text-slate-500 text-[9px] uppercase tracking-widest" style={{ background: "var(--panel)" }}>
            <tr><th className="text-left px-1.5 py-0.5">Time</th><th className="text-left px-1.5 py-0.5">Type</th><th className="text-left px-1.5 py-0.5">K</th><th className="text-left px-1.5 py-0.5">Exp</th><th className="text-right px-1.5 py-0.5">Px</th><th className="text-right px-1.5 py-0.5">Sz</th><th className="text-right px-1.5 py-0.5">$</th><th className="text-left px-1.5 py-0.5">SD</th><th className="text-left px-1.5 py-0.5">Flag</th></tr>
          </thead>
          <tbody>
            {filtered.slice(0, 100).map((e, i) => (
              <tr key={i} className="bar-row border-t border-slate-800/40">
                <td className="px-1.5 py-0.5 text-slate-500">{new Date(e.ts / 1e6).toLocaleTimeString()}</td>
                <td className={`px-1.5 py-0.5 ${e.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{e.type}</td>
                <td className="px-1.5 py-0.5 font-bold">{fmt(e.strike, 0)}</td>
                <td className="px-1.5 py-0.5 text-slate-400">{e.expiry}</td>
                <td className="px-1.5 py-0.5 text-right">${fmt(e.price, 2)}</td>
                <td className="px-1.5 py-0.5 text-right">{fmt(e.size, 0)}</td>
                <td className="px-1.5 py-0.5 text-right text-amber-300">${fmtAbs(e.notional)}</td>
                <td className="px-1.5 py-0.5 text-slate-500">{e.side}</td>
                <td className="px-1.5 py-0.5">{e.block ? <span className="tag king">BLK</span> : e.sweep ? <span className="tag ceiling">SWP</span> : e.unusual ? <span className="tag tested">UNU</span> : null}</td>
              </tr>
            ))}
            {filtered.length === 0 && (<tr><td colSpan={9} className="text-center text-slate-500 py-4 text-[10px]">{status === "idle" || status === "stopped" || status === "ended" ? "Press ▶ start to stream. Enable demo mode for simulated data." : "waiting…"}</td></tr>)}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============ Live Spot ============
function useLiveSpot(ticker, enabled = true, intervalMs = 5000) {
  const [spot, setSpot] = useState(null);
  useEffect(() => {
    if (!enabled || !ticker) return;
    let mounted = true;
    const f = async () => { if (typeof document !== "undefined" && document.visibilityState === "hidden") return; try { const res = await axios.get(`${API}/spot/${encodeURIComponent(ticker)}`); if (mounted) setSpot(res.data); } catch { /* noop */ } };
    f(); const id = setInterval(f, intervalMs); return () => { mounted = false; clearInterval(id); };
  }, [ticker, enabled, intervalMs]);
  return spot;
}

// ============ MAIN APP ============
export default function App() {
  const [ticker, setTicker] = useState("SPY");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [expiries, setExpiries] = useState(4);
  const [mode, setMode] = useState("day");
  const [view, setView] = useState("grid");
  const [viewMode, setViewMode] = useState("gex");
  const [page, setPage] = useState("heatseeker");
  const [trinityData, setTrinityData] = useState(null);
  const [trinityLoading, setTrinityLoading] = useState(false);
  const [filters, setFilters] = useState({ magMin: 0, lifecycle: "all", side: "all" });
  const [dte, setDte] = useState(null);
  const [customTicker, setCustomTicker] = useState("");
  const [drilldown, setDrilldown] = useState(null);
  const lastRefresh = useRef(null);

  const fetchHeatmap = useCallback(async (t, m) => {
    setLoading(true); setErr(null);
    try { const params = new URLSearchParams(); params.set("expiries", expiries); params.set("mode", m); if (dte !== null) params.set("dte", dte); const res = await axios.get(`${API}/heatmap/${encodeURIComponent(t)}?${params.toString()}`, { timeout: 90000 }); setData(res.data); lastRefresh.current = new Date(); } catch (e) { setErr(e.response?.data?.detail || e.message); } finally { setLoading(false); }
  }, [expiries, dte]);

  const fetchTrinity = useCallback(async (m) => {
    setTrinityLoading(true);
    try { const params = new URLSearchParams(); params.set("tickers", TRINITY.join(",")); params.set("mode", m); if (dte !== null) params.set("dte", dte); const res = await axios.get(`${API}/trinity?${params.toString()}`, { timeout: 120000 }); setTrinityData(res.data); } catch (e) { console.error(e); } finally { setTrinityLoading(false); }
  }, [dte]);

  useEffect(() => {
    if (page === "trinity") { fetchTrinity(mode); const id = setInterval(() => fetchTrinity(mode), REFRESH_MS); return () => clearInterval(id); }
    else if (page === "heatseeker") { fetchHeatmap(ticker, mode); const id = setInterval(() => fetchHeatmap(ticker, mode), REFRESH_MS); return () => clearInterval(id); }
  }, [ticker, mode, page, fetchHeatmap, fetchTrinity]);

  const livespot = useLiveSpot(ticker, page === "heatseeker", 5000);
  const spotDelta = (livespot && data?.spot) ? (livespot.spot - data.spot) : 0;
  const regimeColor = data?.nodes?.regime === "positive" ? "text-emerald-400" : data?.nodes?.regime === "negative" ? "text-rose-400" : "text-slate-400";

  return (
    <div className="App min-h-screen" style={{ background: "var(--bg)" }}>
      {/* HEADER */}
      <header className="border-b border-slate-800 px-3 py-1.5 flex items-center justify-between sticky top-0 z-30" style={{ background: "rgba(7,9,13,0.96)", backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-3">
          <div className="flex items-baseline gap-1.5">
            <span className="text-xs font-bold tracking-widest text-teal-300">CONFLUENCE DECODER</span>
            <span className="text-[9px] text-slate-500">/ Skylit-style</span>
          </div>
          <div className="dotted-divider w-4" />
          <div className="flex gap-0.5">
            <button data-testid="page-heatseeker" onClick={() => setPage("heatseeker")} className={`btn ${page === "heatseeker" ? "active" : ""}`} style={{padding:"4px 8px",fontSize:"11px"}}>◆ HEAT</button>
            <button data-testid="page-trinity" onClick={() => setPage("trinity")} className={`btn ${page === "trinity" ? "active" : ""}`} style={{padding:"4px 8px",fontSize:"11px"}}>△ TRINITY</button>
            <button data-testid="page-flowseeker" onClick={() => setPage("flowseeker")} className={`btn ${page === "flowseeker" ? "active" : ""}`} style={{padding:"4px 8px",fontSize:"11px"}}>⟶ FLOW</button>
          </div>
          <div className="dotted-divider w-4" />
          <div className="flex gap-0.5" data-testid="mode-toggle">
            <button onClick={() => setMode("day")} className={`btn ${mode === "day" ? "active" : ""}`} style={{padding:"4px 8px",fontSize:"11px"}}>Day</button>
            <button onClick={() => setMode("swing")} className={`btn ${mode === "swing" ? "active" : ""}`} style={{padding:"4px 8px",fontSize:"11px"}}>Swing</button>
          </div>
        </div>
        <div className="flex items-center gap-2 text-[10px] text-slate-500">
          <BudgetMeter />
          <span className="text-[9px] uppercase tracking-widest text-slate-600">{data?.data_source || ""}</span>
          {loading && <span className="text-teal-400 flash-pulse">●</span>}
          {!loading && lastRefresh.current && <span className="text-slate-600">{lastRefresh.current.toLocaleTimeString()}</span>}
        </div>
      </header>

      {/* TICKER STRIP */}
      {page !== "trinity" && (
        <div className="px-3 py-1.5 border-b border-slate-800/70 flex items-center gap-1.5 flex-wrap">
          {DEFAULT_TICKERS.map(t => (<button key={t} data-testid={`ticker-btn-${t}`} onClick={() => setTicker(t)} className={`btn ${ticker === t ? "active" : ""}`} style={{padding:"3px 8px",fontSize:"11px"}}>{t.replace("^", "")}</button>))}
          <input type="text" value={customTicker} onChange={(e) => setCustomTicker(e.target.value.toUpperCase())} onKeyDown={(e) => { if (e.key === "Enter" && customTicker) setTicker(customTicker); }} placeholder="add…" data-testid="custom-ticker-input" className="bg-slate-900 border border-slate-700 rounded px-1.5 py-0.5 text-[10px] text-slate-200 w-20 focus:outline-none focus:border-teal-500" />
        </div>
      )}

      {/* TRINITY VIEW - FIXED: compact, all 3 visible */}
      {page === "trinity" && (
        <div className="p-3" data-testid="trinity-view">
          {trinityLoading && <div className="text-slate-500 text-xs mb-2">Loading Trinity…</div>}
          {trinityData && (
            <>
              <div className="panel p-2 mb-2 flex justify-between items-center">
                <div className="flex items-center gap-4">
                  <div>
                    <div className="label">Verdict</div>
                    <div className={`text-lg font-bold uppercase tracking-wider ${trinityData.alignment.verdict === "full_alignment" ? "text-emerald-400" : trinityData.alignment.verdict === "partial_alignment" ? "text-amber-300" : "text-rose-400"}`}>{trinityData.alignment.verdict.replace(/_/g, " ")}</div>
                  </div>
                  <div className="dotted-divider h-8" style={{width:1}} />
                  <div>
                    <div className="label">Regime</div>
                    <div className="text-sm mono"><span className={trinityData.alignment.regime === "positive" ? "text-emerald-400" : trinityData.alignment.regime === "negative" ? "text-rose-400" : "text-slate-400"}>{trinityData.alignment.regime}</span> <span className="text-slate-500">· {(trinityData.alignment.confluence * 100).toFixed(0)}%</span></div>
                  </div>
                </div>
                <div className="text-[9px] text-slate-500 max-w-xs text-right">
                  {trinityData.alignment.verdict === "full_alignment" && "All three agree. Highest conviction."}
                  {trinityData.alignment.verdict === "partial_alignment" && "Two-of-three. Reduced size."}
                  {trinityData.alignment.verdict === "divergence" && "Disagreement. Wait."}
                </div>
              </div>
              <div className="grid grid-cols-3 gap-2">
                {TRINITY.map((t) => {
                  const d = trinityData.tickers[t];
                  if (!d || d.error) return <div key={t} className="panel p-2 text-rose-400 text-[10px]">{t}: {d?.error || "no data"}</div>;
                  return (
                    <div key={t} className="panel p-2" data-testid={`trinity-panel-${t}`}>
                      <div className="flex justify-between items-baseline mb-1">
                        <div className="font-bold text-xs">{t.replace("^", "")}</div>
                        <div className="text-[9px] mono text-slate-400">spot {fmt(d.spot, 1)} · {d.nodes?.regime}γ</div>
                      </div>
                      <div className="mb-1"><BarHeatmap data={d} filters={{}} compact viewMode={viewMode} /></div>
                      <div className="flex flex-wrap gap-0.5">
                        {(d.patterns || []).slice(0, 3).map((p, i) => (<span key={i} className="text-[8px] px-1 py-px border border-slate-700 rounded uppercase tracking-wider text-slate-400">{p.name}</span>))}
                      </div>
                      <button className="text-[8px] text-teal-400 underline mt-1" onClick={() => { setTicker(t); setPage("heatseeker"); }}>focus →</button>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* HEATSEEKER */}
      {page === "heatseeker" && (
        <div className="grid grid-cols-12 gap-2 p-3">
          <aside className="col-span-3 space-y-2">
            <div className="panel p-2" data-testid="ticker-summary">
              <div className="flex justify-between items-baseline">
                <div className="text-sm font-bold tracking-wider">{ticker.replace("^", "")}</div>
                <div className={`text-[10px] uppercase tracking-widest ${regimeColor}`}>{data?.nodes?.regime || "—"} γ</div>
              </div>
              <div className="text-xl mono mt-0.5" data-testid="spot-price">
                ${fmt(livespot?.spot ?? data?.spot, 2)}
                {livespot && data?.spot && Math.abs(spotDelta) > 0.01 && (<span className={`ml-1 text-[10px] ${spotDelta > 0 ? "text-emerald-400" : "text-rose-400"}`} data-testid="spot-delta">{spotDelta > 0 ? "▲" : "▼"}{Math.abs(spotDelta).toFixed(2)}</span>)}
                {livespot && <span className="ml-1 text-[8px] text-teal-500 flash-pulse">●</span>}
              </div>
              <div className="text-[9px] text-slate-500">{data?.expiries_used?.length ? `${data.expiries_used.length} exp · ${data.expiries_used[0]} → ${data.expiries_used.slice(-1)[0]}` : ""}</div>
              {err && <div className="text-rose-400 text-[10px] mt-1">{err}</div>}
              <div className="dotted-divider my-2" />
              <div className="grid grid-cols-2 gap-1 text-[10px]">
                <div><div className="label">King</div><div className="mono text-amber-300">{fmt(data?.nodes?.king?.strike, 0)}</div></div>
                <div><div className="label">|GEX|</div><div className="mono">{fmtAbs(data?.nodes?.king?.gex)}</div></div>
                <div><div className="label">Floor</div><div className="mono text-emerald-400">{fmt(data?.nodes?.floors?.[0]?.strike, 0) || "—"}</div></div>
                <div><div className="label">Ceil</div><div className="mono text-rose-400">{fmt(data?.nodes?.ceilings?.[0]?.strike, 0) || "—"}</div></div>
              </div>
            </div>

            <div className="panel p-2" data-testid="filter-panel">
              <div className="label mb-1">Filters</div>
              <div className="space-y-1.5 text-[10px]">
                <div><div className="text-slate-500 mb-0.5">View</div>
                  <div className="flex gap-0.5"><button onClick={() => setView("grid")} data-testid="view-grid" className={`btn flex-1 ${view === "grid" ? "active" : ""}`} style={{padding:"3px 6px",fontSize:"10px"}}>Grid</button><button onClick={() => setView("bar")} data-testid="view-bar" className={`btn flex-1 ${view === "bar" ? "active" : ""}`} style={{padding:"3px 6px",fontSize:"10px"}}>Bars</button></div>
                </div>
                <div><div className="text-slate-500 mb-0.5">Exposure</div>
                  <div className="flex gap-0.5"><button onClick={() => setViewMode("gex")} className={`btn flex-1 ${viewMode === "gex" ? "active" : ""}`} style={{padding:"3px 6px",fontSize:"10px"}}>GEX</button><button onClick={() => setViewMode("vex")} className={`btn flex-1 ${viewMode === "vex" ? "active" : ""}`} style={{padding:"3px 6px",fontSize:"10px"}}>VEX</button></div>
                </div>
                <div><div className="text-slate-500 mb-0.5">DTE</div>
                  <div className="flex gap-0.5">{[{l:"0DTE",v:0},{l:"1DTE",v:1},{l:"W",v:7},{l:"All",v:null}].map(({l,v}) => (<button key={l} onClick={() => setDte(v)} data-testid={`dte-${l.toLowerCase()}`} className={`btn flex-1 ${dte === v ? "active" : ""}`} style={{padding:"3px 4px",fontSize:"10px"}}>{l}</button>))}</div>
                </div>
                <div><div className="text-slate-500 mb-0.5">Expiries</div>
                  <div className="flex gap-0.5">{[2,4,6,8,12].map(n => (<button key={n} onClick={() => setExpiries(n)} className={`btn flex-1 ${expiries === n ? "active" : ""}`} style={{padding:"3px 4px",fontSize:"10px"}}>{n}</button>))}</div>
                </div>
                <div><div className="text-slate-500 mb-0.5">Side</div>
                  <div className="flex gap-0.5">{["all","above","below"].map(s => (<button key={s} onClick={() => setFilters(f => ({ ...f, side: s }))} className={`btn flex-1 ${filters.side === s ? "active" : ""}`} style={{padding:"3px 4px",fontSize:"10px"}}>{s}</button>))}</div>
                </div>
                <div><div className="text-slate-500 mb-0.5">Lifecycle</div>
                  <div className="flex gap-0.5 flex-wrap">{["all","fresh","tested","delivered","decaying"].map(s => (<button key={s} onClick={() => setFilters(f => ({ ...f, lifecycle: s }))} className={`btn ${filters.lifecycle === s ? "active" : ""}`} style={{padding:"2px 6px",fontSize:"9px"}}>{s}</button>))}</div>
                </div>
              </div>
            </div>
            <Movers onPick={(t) => setTicker(t)} />
          </aside>

          <main className="col-span-6">
            <FlipZoneBar spot={data?.spot} polarityLevel={data?.nodes?.polarity_level} vexFlip={data?.nodes?.vex_flip} />
            <StackedNodes stacked={data?.nodes?.stacked_nodes} />
            <TugOfWar zones={data?.nodes?.tug_of_war} />
            <div className="panel p-2" data-testid="main-heatmap">
              <div className="flex justify-between items-center mb-1">
                <div>
                  <div className="label">Heatseeker · {viewMode === "vex" ? "VEX" : "GEX"} {view === "grid" ? "Grid" : "Bars"}</div>
                  <div className="text-[9px] text-slate-500">{viewMode === "vex" ? "Amber=+vanna · Pink=-vanna · Yellow=King" : "Teal=Pika(+) · Purple=Barney(-) · Yellow=King"}</div>
                </div>
                <div className="flex gap-1 text-[9px]"><span className="tag king">K</span><span className="tag floor">FL</span><span className="tag ceiling">CE</span><span className="tag gate">GK</span><span className="tag air">AIR</span></div>
              </div>
              {data ? (view === "grid" ? <GridHeatmap data={data} filters={filters} onCellClick={(s, e) => setDrilldown({ ticker, expiry: e, strike: s })} viewMode={viewMode} /> : <BarHeatmap data={data} filters={filters} compact={false} viewMode={viewMode} />) : (<div className="text-slate-500 text-xs p-4 text-center">Loading…</div>)}
            </div>
          </main>

          <aside className="col-span-3 space-y-2">
            <div className="panel p-2" data-testid="patterns-panel">
              <div className="label mb-1">Patterns</div>
              <div className="space-y-1">{data?.patterns?.length ? data.patterns.map((p, i) => <PatternCard key={i} p={p} />) : (<div className="text-slate-500 text-[10px]">No textbook pattern.</div>)}</div>
            </div>
            <ScenarioMatrix data={data} />
            <VelocityGauge velocity={data?.velocity} />
            {data && <NodesTable data={data} viewMode={viewMode} />}
            {data?.nodes?.air_pockets?.length > 0 && (
              <div className="panel p-2" data-testid="air-pockets-panel">
                <div className="label mb-1">Air Pockets</div>
                <div className="space-y-0.5 text-[10px]">{data.nodes.air_pockets.map((a, i) => (<div key={i} className="flex justify-between text-slate-400"><span className="mono">{fmt(a.low, 0)}–{fmt(a.high, 0)}</span><span className="text-slate-500">w{a.width}</span></div>))}</div>
              </div>
            )}
          </aside>
        </div>
      )}

      {page === "flowseeker" && (<div className="p-3"><Flowseeker ticker={ticker} /></div>)}
      {drilldown && <Drilldown {...drilldown} onClose={() => setDrilldown(null)} />}
      <footer className="border-t border-slate-800 px-3 py-1.5 text-[9px] text-slate-600 flex justify-between">
        <span>Databento OPRA (OI) · yfinance (IV) · Polygon (aggs). GEX/VEX via Black-Scholes.</span>
        <span>Confluence Decoder · {new Date().getFullYear()}</span>
      </footer>
    </div>
  );
}
