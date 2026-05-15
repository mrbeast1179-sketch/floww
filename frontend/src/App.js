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

const tagFor = (kind) => ({
  king: "tag king", floor: "tag floor", ceiling: "tag ceiling", gate: "tag gate", air: "tag air",
  fresh: "tag fresh", tested: "tag tested", delivered: "tag delivered", decaying: "tag decaying",
}[kind] || "tag");

// Skylit-style color scale: positive (Pika) = cyan/teal, negative (Barney) = purple/violet
// King highlights pop yellow-green. VEX uses warmer tones (amber/pink). Charm uses cyan/violet.
function cellColor(v, maxAbs, isKing = false, mode = "gex") {
  if (!v || maxAbs === 0) return { bg: "rgba(15, 22, 32, 0.7)", text: "#5a6781" };
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  if (mode === "charm") {
    if (isKing && v > 0) return { bg: `rgba(34, 211, 238, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (isKing && v < 0) return { bg: `rgba(168, 85, 247, ${0.55 + 0.4 * norm})`, text: "#0b1320" };
    if (v > 0) { const alpha = 0.15 + 0.7 * norm; return { bg: `rgba(34, 211, 238, ${alpha})`, text: norm > 0.5 ? "#0b1320" : "#a5f3fc" }; }
    else { const alpha = 0.18 + 0.7 * norm; return { bg: `rgba(168, 85, 247, ${alpha})`, text: norm > 0.5 ? "#fdf4ff" : "#e9d5ff" }; }
  }
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

// ============ Skylit-style 2D Grid Heatmap ============
function GridHeatmap({ data, filters, onCellClick, viewMode = "gex" }) {
  const spotRowRef = useRef(null);
  useEffect(() => {
    if (spotRowRef.current) {
      spotRowRef.current.scrollIntoView({ block: "center", behavior: "auto" });
    }
  }, [data?.ticker, data?.mode]);

  if (!data?.grid) return <div className="text-slate-500 text-xs p-4">No grid data</div>;
  const { spot, grid, charm_grid, nodes } = data;
  const expiries = grid.expiries || [];
  let strikes = (grid.strikes || []).slice().sort((a, b) => b - a); // descending
  if (filters?.side === "above") strikes = strikes.filter(s => s > spot);
  if (filters?.side === "below") strikes = strikes.filter(s => s < spot);

  // Helper to look up grid cell with key fallback (handles both "739" and "739.0")
  const cellOf = (e, s) => {
    const g = (viewMode === "charm" ? charm_grid : grid.grid) || {};
    const ge = g[e];
    if (!ge) return 0;
    return ge[String(Number.isInteger(s) ? s : s)] ?? ge[String(s)] ?? ge[String(s.toFixed(1))] ?? ge[String(parseInt(s))] ?? 0;
  };

  // Hide rows where ALL cells are zero/empty across visible expiries
  strikes = strikes.filter(s => expiries.some(e => Math.abs(cellOf(e, s)) > 0));

  // Filter by lifecycle
  if (filters?.lifecycle && filters.lifecycle !== "all") {
    const lifecycleStrikes = new Set(
      (data.strikes || [])
        .filter(s => s.lifecycle === filters.lifecycle)
        .map(s => s.strike)
    );
    strikes = strikes.filter(s => lifecycleStrikes.has(s));
  }

  // global maxAbs across visible cells
  let maxAbs = 1;
  for (const e of expiries) {
    for (const s of strikes) {
      const v = cellOf(e, s);
      if (Math.abs(v) > maxAbs) maxAbs = Math.abs(v);
    }
  }

  const kingStrike = nodes?.king?.strike;
  const floorSet = new Set((nodes?.floors || []).map(f => f.strike));
  const ceilSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const gkSet = new Set((nodes?.gatekeepers || []).map(f => f.strike));
  const inAir = (s) => (nodes?.air_pockets || []).some(a => s >= a.low && s <= a.high);

  // spot insertion: find where to put the spot line
  const spotIdx = strikes.findIndex(s => s <= spot);

  const expFmt = (e) => { try { const [, m, d] = e.split("-"); return `${m}-${d}`; } catch { return e; } };

  return (
    <div className="overflow-auto" data-testid="grid-heatmap" style={{ maxHeight: "75vh" }}>
      <table className="border-collapse mono text-[10px]">
        <thead className="sticky top-0 z-10" style={{ background: "var(--panel)" }}>
          <tr>
            <th className="px-2 py-1 text-left text-slate-500 sticky left-0 z-20" style={{ background: "var(--panel)" }}>Strike</th>
            {expiries.map((e) => (
              <th key={e} className="px-2 py-1 text-slate-400 font-normal" style={{ minWidth: 64 }}>{expFmt(e)}</th>
            ))}
            <th className="px-2 py-1 text-slate-500 text-left">Tags</th>
          </tr>
        </thead>
        <tbody>
          {strikes.map((s, i) => {
            const isKing = s === kingStrike;
            const isFloor = floorSet.has(s);
            const isCeil = ceilSet.has(s);
            const isGate = gkSet.has(s);
            const airy = inAir(s);

            return (
              <React.Fragment key={s}>
                {i === spotIdx && (
                  <tr ref={spotRowRef}>
                    <td colSpan={expiries.length + 2} style={{ padding: 0 }}>
                      <div className="relative" style={{ height: 18 }}>
                        <div className="absolute inset-x-0 top-1/2" style={{ height: 1, background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)", boxShadow: "0 0 6px rgba(94,234,212,0.55)" }} />
                        <div className="absolute left-2 top-0 text-[10px] font-bold tracking-widest text-teal-300 px-1" style={{ background: "var(--panel)", textShadow: "0 0 6px rgba(94,234,212,0.6)" }}>
                          ◆ SPOT {fmt(spot, 2)}
                        </div>
                      </div>
                    </td>
                  </tr>
                )}
                <tr
                  className={`bar-row ${airy ? "opacity-65" : ""}`}
                  data-testid={`grid-row-${s}`}
                >
                  <td
                    className={`px-2 py-1 font-bold sticky left-0 z-10 ${isKing ? "text-amber-300" : isFloor ? "text-emerald-400" : isCeil ? "text-rose-400" : isGate ? "text-sky-400" : "text-slate-400"}`}
                    style={{ background: "var(--panel)" }}
                  >
                    {fmt(s, s >= 1000 ? 0 : 1)}
                  </td>
                  {expiries.map((e) => {
                    const v = cellOf(e, s);
                    const isKingCell = isKing && Math.abs(v) > 0.6 * maxAbs;
                    const col = cellColor(v, maxAbs, isKingCell, viewMode);
                    return (
                      <td
                        key={e}
                        className="px-1 py-1 text-center cursor-pointer hover:outline hover:outline-1 hover:outline-teal-400"
                        style={{ background: col.bg, color: col.text, minWidth: 60 }}
                        onClick={() => onCellClick && onCellClick(s, e, v)}
                        title={`strike ${s} · exp ${e} · ${viewMode === "charm" ? "charm" : "gex"} ${fmtCell(v)}`}
                      >
                        {fmtCell(v)}
                      </td>
                    );
                  })}
                  <td className="px-2 py-1">
                    <div className="flex gap-1 items-center">
                      {isKing && <span className="tag king">KING</span>}
                      {isFloor && <span className="tag floor">FLR</span>}
                      {isCeil && <span className="tag ceiling">CEIL</span>}
                      {isGate && <span className="tag gate">GATE</span>}
                      {airy && <span className="tag air">AIR</span>}
                    </div>
                  </td>
                </tr>
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ============ Horizontal Bar Heatmap (compact summary) ============
function BarHeatmap({ data, filters, compact = true, viewMode = "gex" }) {
  if (!data?.strikes) return null;
  const { spot, strikes, nodes } = data;
  const key = viewMode === "vex" ? "vex" : viewMode === "charm" ? "charm" : "gex";
  const filtered = strikes.filter((s) => {
    const val = s[key] || s.gex || 0;
    if (filters?.magMin && Math.abs(val) < filters.magMin) return false;
    if (filters?.lifecycle && filters.lifecycle !== "all" && s.lifecycle !== filters.lifecycle) return false;
    if (filters?.side === "above" && s.strike <= spot) return false;
    if (filters?.side === "below" && s.strike >= spot) return false;
    return true;
  });
  if (!filtered.length) return <div className="text-slate-500 text-xs p-4">No strikes match filters.</div>;
  const sorted = [...filtered].sort((a, b) => b.strike - a.strike);
  const maxAbs = Math.max(...filtered.map(s => Math.abs(s[key] || s.gex || 0)), 1);
  const king = nodes?.king?.strike;
  const fSet = new Set((nodes?.floors || []).map(f => f.strike));
  const cSet = new Set((nodes?.ceilings || []).map(f => f.strike));
  const rowH = compact ? 14 : 18;
  const barColorPos = viewMode === "vex" ? "rgba(245, 158, 11, 0.7)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.7)" : "rgba(45, 212, 191, 0.7)";
  const barColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.7)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.7)" : "rgba(168, 85, 247, 0.7)";
  const kingColorPos = viewMode === "vex" ? "rgba(251, 191, 36, 0.9)" : viewMode === "charm" ? "rgba(34, 211, 238, 0.9)" : "rgba(190, 242, 100, 0.9)";
  const kingColorNeg = viewMode === "vex" ? "rgba(219, 39, 119, 0.85)" : viewMode === "charm" ? "rgba(168, 85, 247, 0.85)" : "rgba(232, 121, 249, 0.85)";

  return (
    <div className="relative" style={{ paddingTop: 4, paddingBottom: 4 }}>
      {sorted.map((s, i) => {
        const isKing = s.strike === king;
        const isF = fSet.has(s.strike);
        const isC = cSet.has(s.strike);
        const val = s[key] || s.gex || 0;
        const pos = val > 0;
        const w = Math.max(2, (Math.abs(val) / maxAbs) * 48);
        const prev = sorted[i - 1];
        const showSpot = prev && prev.strike > spot && s.strike <= spot;
        return (
          <React.Fragment key={s.strike}>
            {showSpot && (
              <div className="flex items-center my-1 px-2">
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
                <div className="px-1 text-[9px] tracking-widest text-teal-300">{fmt(spot, 1)}</div>
                <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
              </div>
            )}
            <div className="bar-row flex items-center text-[10px] mono px-1" style={{ height: rowH }}>
              <div className="flex-1 flex justify-end pr-1">
                {!pos && <div style={{ width: `${w}%`, height: 10, borderRadius: 2,
                  background: isKing ? kingColorNeg : barColorNeg }} />}
              </div>
              <div className={`w-14 text-center ${isKing ? "text-amber-300 font-bold" : isF ? "text-emerald-400" : isC ? "text-rose-400" : "text-slate-400"}`}>{fmt(s.strike, 0)}</div>
              <div className="flex-1 flex pl-1">
                {pos && <div style={{ width: `${w}%`, height: 10, borderRadius: 2,
                  background: isKing ? kingColorPos : barColorPos }} />}
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

// ============ Velocity Gauge ============
function VelocityGauge({ velocity }) {
  if (!velocity) return null;
  const score = velocity.velocity_score || 0;
  const warming = (velocity.snapshots_count || 0) < 3;
  const angle = score * 180 - 90;
  const color = warming ? "#64748b" : score > 0.4 ? "#ef4444" : score > 0.2 ? "#fbbf24" : "#34d399";
  return (
    <div className="panel-2 p-3" data-testid="velocity-gauge">
      <div className="label mb-2">Velocity Mode</div>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 100 60" width="100" height="60">
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="6" />
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={color} strokeWidth="6"
            strokeDasharray={`${score * 125} 200`} strokeLinecap="round" />
          <line x1="50" y1="55" x2={50 + 35 * Math.cos((angle - 90) * Math.PI / 180)} y2={55 + 35 * Math.sin((angle - 90) * Math.PI / 180)} stroke={color} strokeWidth="2" />
          <circle cx="50" cy="55" r="3" fill={color} />
        </svg>
        <div>
          <div className="text-2xl font-bold mono" style={{ color }}>{warming ? "…" : (score * 100).toFixed(0)}</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">{warming ? "warming up" : "rate of change"}</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
        <div>
          <div className="label">Floor</div>
          <div className={velocity.rolling_floor === "rolling_up" ? "text-emerald-400" : velocity.rolling_floor === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_floor || "stable").replace("_", " ")}
          </div>
        </div>
        <div>
          <div className="label">Ceiling</div>
          <div className={velocity.rolling_ceiling === "rolling_up" ? "text-emerald-400" : velocity.rolling_ceiling === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_ceiling || "stable").replace("_", " ")}
          </div>
        </div>
      </div>
      {velocity.floor_sequence?.length > 1 && (
        <div className="mt-2 text-[10px] text-slate-500">Floors: {velocity.floor_sequence.slice(0, 4).map(s => fmt(s, 0)).join(" → ")}</div>
      )}
      {velocity.ceiling_sequence?.length > 1 && (
        <div className="text-[10px] text-slate-500">Ceilings: {velocity.ceiling_sequence.slice(0, 4).map(s => fmt(s, 0)).join(" → ")}</div>
      )}
    </div>
  );
}

// ============ Top Movers ============
function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  useEffect(() => {
    let mounted = true;
    const f = async () => {
      try {
        const res = await axios.get(`${API}/movers?limit=12`);
        if (mounted) setRows(res.data.results || []);
      } catch (e) { /* noop */ }
    };
    f();
    const id = setInterval(f, 60000);
    return () => { mounted = false; clearInterval(id); };
  }, []);
  return (
    <div className="panel p-3" data-testid="movers-panel">
      <div className="label mb-2">Top Movers (prev session %)</div>
      <div className="flex flex-col gap-1 text-[11px]">
        {rows.length === 0 && <div className="text-slate-500">…</div>}
        {rows.map((r) => (
          <button key={r.ticker} data-testid={`mover-${r.ticker}`} onClick={() => onPick && onPick(r.ticker)}
            className="flex justify-between items-center px-2 py-1 hover:bg-slate-800/40 rounded">
            <span className="font-bold w-14 text-left">{r.ticker}</span>
            <span className="mono text-slate-400 w-20 text-right">${fmt(r.close, 2)}</span>
            <span className={`mono w-16 text-right ${pctClass(r.pct)}`}>{r.pct >= 0 ? "+" : ""}{r.pct}%</span>
          </button>
        ))}
      </div>
    </div>
  );
}

// ============ Nodes Table ============
function NodesTable({ data }) {
  const [sortKey, setSortKey] = useState("mag");
  const [sortDir, setSortDir] = useState("desc");
  if (!data?.nodes) return null;
  const spot = data.spot;
  const all = (data.strikes || []).map((s) => {
    const role = s.strike === data.nodes.king?.strike ? "King"
      : data.nodes.floors?.some(f => f.strike === s.strike) ? "Floor"
      : data.nodes.ceilings?.some(f => f.strike === s.strike) ? "Ceiling"
      : data.nodes.gatekeepers?.some(f => f.strike === s.strike) ? "Gatekeeper"
      : null;
    return { ...s, role, mag: Math.abs(s.gex), dist: Math.abs(s.strike - spot) / spot * 100 };
  }).filter(s => s.role || s.mag > 0);
  const sorted = [...all].sort((a, b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortDir === "desc" ? vb - va : va - vb;
  });
  const head = (k, l) => (
    <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1 cursor-pointer hover:text-teal-400"
      onClick={() => { setSortKey(k); setSortDir(d => sortKey === k && d === "desc" ? "asc" : "desc"); }}>
      {l}{sortKey === k ? (sortDir === "desc" ? " ↓" : " ↑") : ""}
    </th>
  );
  return (
    <div className="panel p-3" data-testid="nodes-table">
      <div className="label mb-2">Structural Nodes</div>
      <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
        <table className="w-full text-[11px] mono">
          <thead className="sticky top-0" style={{ background: "var(--panel)" }}>
            <tr>
              {head("strike", "Strike")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Role</th>
              {head("mag", "|GEX|")}
              {head("gex", "Net")}
              {head("dist", "Δ Spot")}
              {head("taps", "Taps")}
              <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1">Life</th>
            </tr>
          </thead>
          <tbody>
            {sorted.slice(0, 30).map((s) => (
              <tr key={s.strike} className="bar-row border-t border-slate-800/60">
                <td className="px-2 py-1 font-bold text-slate-200">{fmt(s.strike, 0)}</td>
                <td className="px-2 py-1">
                  {s.role && <span className={`tag ${s.role === "King" ? "king" : s.role === "Floor" ? "floor" : s.role === "Ceiling" ? "ceiling" : "gate"}`}>{s.role}</span>}
                </td>
                <td className="px-2 py-1 text-slate-300">{fmtAbs(s.mag)}</td>
                <td className={`px-2 py-1 ${s.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{s.gex > 0 ? "+" : ""}{fmtAbs(s.gex)}</td>
                <td className="px-2 py-1 text-slate-500">{s.dist.toFixed(2)}%</td>
                <td className="px-2 py-1 text-slate-500">{s.taps}</td>
                <td className="px-2 py-1"><span className={tagFor(s.lifecycle)}>{s.lifecycle}</span></td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============ Drilldown panel ============
function Drilldown({ ticker, expiry, strike, onClose }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (!ticker) return;
    setLoading(true);
    const params = new URLSearchParams();
    if (expiry) params.set("expiry", expiry);
    if (strike) params.set("strike", strike);
    axios.get(`${API}/contract/${encodeURIComponent(ticker)}?${params.toString()}`)
      .then(r => setData(r.data))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [ticker, expiry, strike]);
  if (!data && !loading) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" style={{ background: "rgba(0,0,0,0.7)" }} onClick={onClose}>
      <div className="panel p-4 max-w-4xl w-[90%] max-h-[80vh] overflow-auto" onClick={(e) => e.stopPropagation()} data-testid="drilldown-modal">
        <div className="flex justify-between items-center mb-3">
          <div>
            <div className="label">Contract Drilldown</div>
            <div className="text-lg font-bold">{ticker} {strike ? `· ${strike}` : ""} {expiry ? `· ${expiry}` : ""}</div>
          </div>
          <button onClick={onClose} className="btn" data-testid="drilldown-close">close ✕</button>
        </div>
        {loading && <div className="text-slate-500">loading…</div>}
        {data && (
          <div>
            <div className="text-[11px] text-slate-500 mb-2">Spot {fmt(data.spot, 2)} · {data.count} contracts · source {data.data_source}</div>
            {data.count === 0 ? (
              <div className="text-slate-500 text-xs py-8 text-center">
                No contracts at this strike × expiry combination.
                <div className="text-[10px] text-slate-600 mt-1">(Empty cells = no OI or no IV data available for this leg.)</div>
              </div>
            ) : (
            <table className="w-full text-[11px] mono">
              <thead className="text-slate-500 text-[10px] uppercase tracking-widest">
                <tr>
                  <th className="text-left px-2 py-1">Type</th>
                  <th className="text-left px-2 py-1">Strike</th>
                  <th className="text-left px-2 py-1">Expiry</th>
                  <th className="text-right px-2 py-1">OI</th>
                  <th className="text-right px-2 py-1">Volume</th>
                  <th className="text-right px-2 py-1">IV</th>
                  <th className="text-right px-2 py-1">Δ</th>
                  <th className="text-right px-2 py-1">Γ</th>
                  <th className="text-right px-2 py-1">GEX</th>
                  <th className="text-left px-2 py-1">Src</th>
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => (
                  <tr key={i} className="bar-row border-t border-slate-800/60">
                    <td className={`px-2 py-1 ${r.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{r.type}</td>
                    <td className="px-2 py-1 font-bold">{fmt(r.strike, 0)}</td>
                    <td className="px-2 py-1 text-slate-400">{r.expiry}</td>
                    <td className="px-2 py-1 text-right">{fmt(r.oi, 0)}</td>
                    <td className="px-2 py-1 text-right text-slate-500">{fmt(r.volume, 0)}</td>
                    <td className="px-2 py-1 text-right text-slate-400">{(r.iv * 100).toFixed(1)}%</td>
                    <td className="px-2 py-1 text-right text-slate-400">{r.delta?.toFixed(3)}</td>
                    <td className="px-2 py-1 text-right text-slate-500">{r.gamma?.toFixed(5)}</td>
                    <td className={`px-2 py-1 text-right ${r.gex > 0 ? "text-emerald-400" : "text-rose-400"}`}>{fmtAbs(r.gex)}</td>
                    <td className="px-2 py-1 text-[10px] text-slate-600">{r.oi_source}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

// ============ Flowseeker ============
function Flowseeker({ ticker }) {
  const [events, setEvents] = useState([]);
  const [status, setStatus] = useState("idle");
  const [warning, setWarning] = useState(null);
  const [licenseError, setLicenseError] = useState(false);
  const [filter, setFilter] = useState({ unusual: false, sweep: false, block: false, side: "all" });
  const [sessionInfo, setSessionInfo] = useState(null);
  const [errMsg, setErrMsg] = useState(null);
  const [overrideWindow, setOverrideWindow] = useState(false);
  const [duration, setDuration] = useState(120);
  const esRef = useRef(null);

  const start = useCallback(() => {
    if (esRef.current) return;
    setStatus("connecting");
    setEvents([]); setErrMsg(null); setSessionInfo(null); setWarning(null); setLicenseError(false);
    const url = `${API}/flow/${encodeURIComponent(ticker)}?max_seconds=${duration}&enforce_window=${!overrideWindow}`;
    const es = new EventSource(url);
    esRef.current = es;
    es.addEventListener("ready", (e) => {
      try { setSessionInfo(JSON.parse(e.data)); } catch { /* noop */ }
      setStatus("live");
    });
    es.addEventListener("end", () => { setStatus("ended"); es.close(); esRef.current = null; });
    es.addEventListener("warning", (e) => {
      try {
        const m = JSON.parse(e.data || "{}");
        setWarning(m);
        setLicenseError(true);
      } catch { /* noop */ }
    });
    es.addEventListener("error", (e) => {
      try {
        const m = JSON.parse(e.data || "{}");
        if (m.error) setErrMsg(m.error);
        if (m.hint) setLicenseError(true);
      } catch { /* noop */ }
      setStatus("error"); es.close(); esRef.current = null;
    });
    es.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        setEvents((prev) => [msg, ...prev].slice(0, 250));
      } catch { /* noop */ }
    };
  }, [ticker, duration, overrideWindow]);

  const stop = useCallback(async () => {
    try { await axios.post(`${API}/live/tape/stop`); } catch { /* noop */ }
    esRef.current?.close();
    esRef.current = null;
    setStatus("stopped");
  }, []);

  useEffect(() => () => esRef.current?.close(), []);

  const filtered = events.filter(e => {
    if (filter.unusual && !e.unusual) return false;
    if (filter.sweep && !e.sweep) return false;
    if (filter.block && !e.block) return false;
    if (filter.side !== "all") {
      if (filter.side === "calls" && e.type !== "call") return false;
      if (filter.side === "puts" && e.type !== "put") return false;
    }
    return true;
  });

  return (
    <div className="panel p-3" data-testid="flowseeker-panel">
      <div className="flex justify-between items-center mb-3">
        <div>
          <div className="label">Flowseeker · Live OPRA trades</div>
          <div className="text-xs text-slate-500">{ticker} · status <span className={status === "live" ? "text-teal-400" : status === "error" ? "text-rose-400" : "text-slate-400"}>{status}</span> · {filtered.length}/{events.length} trades</div>
          {sessionInfo?.auto_stop_at && (
            <div className="text-[10px] text-slate-600">session {sessionInfo.session_id} · auto-stop {new Date(sessionInfo.auto_stop_at).toLocaleTimeString()}</div>
          )}
          {errMsg && <div className="text-[11px] text-rose-400 mt-1">⚠ {errMsg}</div>}
          {licenseError && (warning || errMsg) && (
            <div className="mt-2 p-3 border border-amber-500/50 rounded bg-amber-500/10" data-testid="flow-license-warning">
              <div className="text-amber-300 text-xs font-bold mb-1">⚠ OPRA Live License Issue</div>
              <div className="text-amber-200/80 text-[11px] leading-snug">
                {warning?.hint || errMsg || "Flowseeker requires a Databento Live OPRA.PILLAR license (separate from Historical data)."}
              </div>
              <div className="text-[10px] text-amber-400/60 mt-1">
                Check your Databento dashboard → Licenses. Historical access ≠ Live streaming.
              </div>
            </div>
          )}
        </div>
        <div className="flex flex-col items-end gap-2">
          <div className="flex gap-2 items-center text-[10px] text-slate-500">
            <label className="flex items-center gap-1">duration
              <select data-testid="flow-duration" value={duration} onChange={e => setDuration(Number(e.target.value))} className="bg-slate-900 border border-slate-700 px-1 rounded text-slate-200" disabled={status === "live"}>
                <option value={60}>1m</option>
                <option value={120}>2m</option>
                <option value={300}>5m</option>
                <option value={600}>10m</option>
              </select>
            </label>
            <label className="flex items-center gap-1">
              <input type="checkbox" data-testid="flow-override-window" checked={overrideWindow} onChange={e => setOverrideWindow(e.target.checked)} disabled={status === "live"} />
              override window
            </label>
          </div>
          <div className="flex gap-2">
            {status !== "live" && status !== "connecting" && (
              <button data-testid="flow-start" onClick={start} className="btn">▶ start ({duration}s)</button>
            )}
            {(status === "live" || status === "connecting") && (
              <button data-testid="flow-stop" onClick={stop} className="btn">■ stop</button>
            )}
          </div>
        </div>
      </div>
      <div className="flex gap-2 mb-3 text-[11px] flex-wrap">
        <button data-testid="flow-filter-unusual" onClick={() => setFilter(f => ({ ...f, unusual: !f.unusual }))} className={`btn ${filter.unusual ? "active" : ""}`}>unusual</button>
        <button data-testid="flow-filter-sweep" onClick={() => setFilter(f => ({ ...f, sweep: !f.sweep }))} className={`btn ${filter.sweep ? "active" : ""}`}>sweep ≥250</button>
        <button data-testid="flow-filter-block" onClick={() => setFilter(f => ({ ...f, block: !f.block }))} className={`btn ${filter.block ? "active" : ""}`}>block ≥500</button>
        {["all", "calls", "puts"].map(s => (
          <button key={s} onClick={() => setFilter(f => ({ ...f, side: s }))} className={`btn ${filter.side === s ? "active" : ""}`}>{s}</button>
        ))}
      </div>
      <div className="overflow-auto" style={{ maxHeight: "60vh" }}>
        <table className="w-full text-[10px] mono">
          <thead className="sticky top-0 text-slate-500 text-[10px] uppercase tracking-widest" style={{ background: "var(--panel)" }}>
            <tr>
              <th className="text-left px-2 py-1">Time</th>
              <th className="text-left px-2 py-1">Type</th>
              <th className="text-left px-2 py-1">Strike</th>
              <th className="text-left px-2 py-1">Expiry</th>
              <th className="text-right px-2 py-1">Price</th>
              <th className="text-right px-2 py-1">Size</th>
              <th className="text-right px-2 py-1">Notional</th>
              <th className="text-left px-2 py-1">Side</th>
              <th className="text-left px-2 py-1">Flag</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((e, i) => (
              <tr key={i} className="bar-row border-t border-slate-800/40">
                <td className="px-2 py-1 text-slate-500">{new Date(e.ts / 1e6).toLocaleTimeString()}</td>
                <td className={`px-2 py-1 ${e.type === "call" ? "text-emerald-400" : "text-rose-400"}`}>{e.type}</td>
                <td className="px-2 py-1 font-bold">{fmt(e.strike, 0)}</td>
                <td className="px-2 py-1 text-slate-400">{e.expiry}</td>
                <td className="px-2 py-1 text-right">${fmt(e.price, 2)}</td>
                <td className="px-2 py-1 text-right">{fmt(e.size, 0)}</td>
                <td className="px-2 py-1 text-right text-amber-300">${fmtAbs(e.notional)}</td>
                <td className="px-2 py-1 text-slate-500">{e.side}</td>
                <td className="px-2 py-1">
                  {e.block ? <span className="tag king">BLOCK</span> : e.sweep ? <span className="tag ceiling">SWEEP</span> : e.unusual ? <span className="tag tested">UNUSUAL</span> : null}
                </td>
              </tr>
            ))}
            {filtered.length === 0 && (
              <tr><td colSpan={9} className="text-center text-slate-500 py-6 text-[11px]">
                {status === "idle" || status === "stopped" || status === "ended" ? "Press start to stream live OPRA trades (max 2 min/session — Databento cost-aware)." : "waiting for trades…"}
              </td></tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ============ Budget Meter & Live Controls ============
function BudgetMeter({ onStopTape }) {
  const [u, setU] = useState(null);
  const [editing, setEditing] = useState(false);
  const [paidInput, setPaidInput] = useState("SPY");
  const [startInput, setStartInput] = useState("09:00");
  const [stopInput, setStopInput] = useState("10:30");

  const refresh = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/databento/usage`);
      setU(res.data);
      setPaidInput((res.data.paid_tickers || ["SPY"]).join(","));
      setStartInput(res.data.live_window_et?.start_hhmm || "09:00");
      setStopInput(res.data.live_window_et?.stop_hhmm || "10:30");
    } catch (e) { /* noop */ }
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 15000);
    return () => clearInterval(id);
  }, [refresh]);

  const savePolicy = async () => {
    try {
      await axios.post(`${API}/live/policy`, {
        paid_tickers: paidInput.split(",").map(s => s.trim()).filter(Boolean),
        window_start: startInput,
        window_stop: stopInput,
      });
      setEditing(false);
      refresh();
    } catch (e) { /* noop */ }
  };

  if (!u) return null;
  const pct = Math.min(100, u.budget_pct_used || 0);
  const barColor = pct > 80 ? "#ef4444" : pct > 50 ? "#fbbf24" : "#34d399";
  const tapeActive = u.live_tape_state?.live_tape_active;
  const inWindow = u.in_window_now;

  return (
    <div className={`flex items-center gap-3 px-3 py-1 rounded border ${inWindow ? "border-emerald-500/60 bg-emerald-500/5" : "border-slate-800"}`} style={{ background: inWindow ? "rgba(16, 185, 129, 0.04)" : "rgba(15,22,32,0.7)" }} data-testid="budget-meter">
      <div className={`text-[10px] uppercase tracking-widest ${inWindow ? "text-emerald-400" : "text-slate-500"}`}>
        {inWindow ? "● IN-WINDOW" : "○ OFF-WINDOW"}
      </div>
      <div className="flex items-center gap-1">
        <div className="w-24 h-1.5 bg-slate-800 rounded overflow-hidden">
          <div style={{ width: `${pct}%`, height: "100%", background: barColor, transition: "width 400ms" }} />
        </div>
        <span className="mono text-[11px]" style={{ color: barColor }}>${fmt(u.est_total_cost_usd, 2)}</span>
        <span className="text-[10px] text-slate-600">/ ${fmt(u.budget_usd, 0)}</span>
      </div>
      <div className="text-[10px] text-slate-500">
        paid <span className="text-teal-400">{(u.paid_tickers || []).join(",") || "—"}</span> · window <span className="text-slate-400">{u.live_window_et?.start_hhmm}-{u.live_window_et?.stop_hhmm} ET</span>
      </div>
      {tapeActive && (
        <div className="flex items-center gap-1">
          <span className="text-[10px] text-rose-400 flash-pulse">● TAPE LIVE</span>
          <button data-testid="budget-stop-tape" onClick={async () => { await axios.post(`${API}/live/tape/stop`); onStopTape && onStopTape(); refresh(); }} className="text-[10px] underline text-rose-300">stop</button>
        </div>
      )}
      <button data-testid="budget-edit" onClick={() => setEditing(v => !v)} className="text-[10px] underline text-slate-500 hover:text-teal-400">{editing ? "cancel" : "edit"}</button>
      {editing && (
        <div className="absolute right-4 top-12 panel p-3 z-40 w-72" data-testid="budget-edit-panel">
          <div className="label mb-2">Live Policy</div>
          <div className="space-y-2 text-[11px]">
            <div>
              <div className="text-slate-500 mb-1">Paid tickers (comma-sep)</div>
              <input value={paidInput} onChange={e => setPaidInput(e.target.value)} className="w-full bg-slate-900 border border-slate-700 px-2 py-1 rounded text-slate-200" data-testid="paid-tickers-input" />
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <div className="text-slate-500 mb-1">Window start ET</div>
                <input value={startInput} onChange={e => setStartInput(e.target.value)} className="w-full bg-slate-900 border border-slate-700 px-2 py-1 rounded text-slate-200" data-testid="window-start-input" />
              </div>
              <div>
                <div className="text-slate-500 mb-1">Window stop ET</div>
                <input value={stopInput} onChange={e => setStopInput(e.target.value)} className="w-full bg-slate-900 border border-slate-700 px-2 py-1 rounded text-slate-200" data-testid="window-stop-input" />
              </div>
            </div>
            <button onClick={savePolicy} data-testid="save-policy" className="btn w-full active">Save</button>
            <div className="text-[10px] text-slate-600 leading-snug">
              <div>· Paid tickers = only ones that hit Databento OPRA OI (~$0.15/ticker/day cached 24h).</div>
              <div>· Outside window, Live Tape refuses to start.</div>
              <div>· Other tickers stay on free yfinance feed.</div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ============ Live Spot Pulse — recompute GEX feel without burning $$ ============
function useLiveSpot(ticker, enabled = true, intervalMs = 5000) {
  const [spot, setSpot] = useState(null);
  useEffect(() => {
    if (!enabled || !ticker) return;
    let mounted = true;
    const f = async () => {
      if (typeof document !== "undefined" && document.visibilityState === "hidden") return;
      try {
        const res = await axios.get(`${API}/spot/${encodeURIComponent(ticker)}`);
        if (mounted) setSpot(res.data);
      } catch { /* noop */ }
    };
    f();
    const id = setInterval(f, intervalMs);
    return () => { mounted = false; clearInterval(id); };
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
  const [mode, setMode] = useState("day"); // day | swing
  const [view, setView] = useState("grid"); // grid | bar
  const [viewMode, setViewMode] = useState("gex"); // gex | vex
  const [page, setPage] = useState("trinity"); // trinity is default (user preference)
  const [trinityData, setTrinityData] = useState(null);
  const [filters, setFilters] = useState({ magMin: 0, lifecycle: "all", side: "all" });
  const [dte, setDte] = useState(null); // null = All, 0 = 0DTE only, 1 = 1DTE, 7 = within week
  const [customTicker, setCustomTicker] = useState("");
  const [drilldown, setDrilldown] = useState(null);
  const lastRefresh = useRef(null);

  const fetchHeatmap = useCallback(async (t, m) => {
    setLoading(true); setErr(null);
    try {
      const params = new URLSearchParams();
      params.set("expiries", expiries);
      params.set("mode", m);
      if (dte !== null) params.set("dte", dte);
      const res = await axios.get(`${API}/heatmap/${encodeURIComponent(t)}?${params.toString()}`, { timeout: 90000 });
      setData(res.data);
      lastRefresh.current = new Date();
    } catch (e) {
      setErr(e.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [expiries, dte]);

  const fetchTrinity = useCallback(async (m) => {
    try {
      const params = new URLSearchParams();
      params.set("tickers", TRINITY.join(","));
      params.set("mode", m);
      if (dte !== null) params.set("dte", dte);
      const res = await axios.get(`${API}/trinity?${params.toString()}`, { timeout: 120000 });
      setTrinityData(res.data);
    } catch (e) { console.error(e); }
  }, [dte]);

  useEffect(() => {
    if (page === "trinity") {
      fetchTrinity(mode);
      const id = setInterval(() => fetchTrinity(mode), REFRESH_MS);
      return () => clearInterval(id);
    } else if (page === "heatseeker") {
      fetchHeatmap(ticker, mode);
      const id = setInterval(() => fetchHeatmap(ticker, mode), REFRESH_MS);
      return () => clearInterval(id);
    }
  }, [ticker, mode, page, fetchHeatmap, fetchTrinity]);

  const livespot = useLiveSpot(ticker, page === "heatseeker", 5000);
  const spotDelta = (livespot && data?.spot) ? (livespot.spot - data.spot) : 0;
  const regimeColor = data?.nodes?.regime === "positive" ? "text-emerald-400" : data?.nodes?.regime === "negative" ? "text-rose-400" : "text-slate-400";

  return (
    <div className="App min-h-screen" style={{ background: "var(--bg)" }}>
      {/* HEADER */}
      <header className="border-b border-slate-800 px-4 py-2 flex items-center justify-between sticky top-0 z-30" style={{ background: "rgba(7,9,13,0.96)", backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-4">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-bold tracking-widest text-teal-300">CONFLUENCE DECODER</span>
            <span className="text-[10px] text-slate-500">/ Skylit-style Heatseeker</span>
          </div>
          <div className="dotted-divider w-8" />
          <div className="flex gap-1">
            <button data-testid="page-heatseeker" onClick={() => setPage("heatseeker")} className={`btn ${page === "heatseeker" ? "active" : ""}`}>◆ HEATSEEKER</button>
            <button data-testid="page-trinity" onClick={() => setPage("trinity")} className={`btn ${page === "trinity" ? "active" : ""}`}>△ TRINITY</button>
            <button data-testid="page-flowseeker" onClick={() => setPage("flowseeker")} className={`btn ${page === "flowseeker" ? "active" : ""}`}>⟶ FLOWSEEKER</button>
          </div>
          <div className="dotted-divider w-8" />
          <div className="flex gap-1" data-testid="mode-toggle">
            <button onClick={() => setMode("day")} className={`btn ${mode === "day" ? "active" : ""}`}>Day</button>
            <button onClick={() => setMode("swing")} className={`btn ${mode === "swing" ? "active" : ""}`}>Swing</button>
          </div>
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-500">
          <BudgetMeter />
          <span className="text-[10px] uppercase tracking-widest text-slate-600">{data?.data_source || ""}</span>
          <span>· 30s</span>
          {loading && <span className="text-teal-400 flash-pulse">● syncing</span>}
          {!loading && lastRefresh.current && <span className="text-slate-600">{lastRefresh.current.toLocaleTimeString()}</span>}
        </div>
      </header>

      {/* TICKER STRIP (always visible except Flowseeker) */}
      {page !== "trinity" && (
        <div className="px-4 py-2 border-b border-slate-800/70 flex items-center gap-2 flex-wrap">
          {DEFAULT_TICKERS.map(t => (
            <button key={t} data-testid={`ticker-btn-${t}`} onClick={() => setTicker(t)} className={`btn ${ticker === t ? "active" : ""}`}>
              {t.replace("^", "")}
            </button>
          ))}
          <input type="text" value={customTicker} onChange={(e) => setCustomTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key === "Enter" && customTicker) { setTicker(customTicker); }}}
            placeholder="add ticker…" data-testid="custom-ticker-input"
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-28 focus:outline-none focus:border-teal-500" />
        </div>
      )}

      {/* TRINITY VIEW */}
      {page === "trinity" && trinityData && (
        <div className="p-3" data-testid="trinity-view">
          <div className="panel p-2 mb-2 flex justify-between items-center">
            <div className="flex items-center gap-4">
              <div>
                <div className="label">Verdict</div>
                <div className={`text-lg font-bold uppercase tracking-wider ${trinityData.alignment.verdict === "full_alignment" ? "text-emerald-400" : trinityData.alignment.verdict === "partial_alignment" ? "text-amber-300" : "text-rose-400"}`}>
                  {trinityData.alignment.verdict.replace(/_/g, " ")}
                </div>
              </div>
              <div className="dotted-divider h-6" style={{width:1}} />
              <div>
                <div className="label">Regime</div>
                <div className="text-sm mono">
                  <span className={trinityData.alignment.regime === "positive" ? "text-emerald-400" : trinityData.alignment.regime === "negative" ? "text-rose-400" : "text-slate-400"}>{trinityData.alignment.regime}</span>
                  <span className="text-slate-500"> · {(trinityData.alignment.confluence * 100).toFixed(0)}%</span>
                </div>
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
                  <div className="mb-1"><BarHeatmap data={d} filters={{}} compact /></div>
                  <div className="flex flex-wrap gap-0.5">
                    {(d.patterns || []).slice(0, 3).map((p, i) => (
                      <span key={i} className="text-[8px] px-1 py-px border border-slate-700 rounded uppercase tracking-wider text-slate-400">{p.name}</span>
                    ))}
                  </div>
                  <button className="text-[8px] text-teal-400 underline mt-1" onClick={() => { setTicker(t); setPage("heatseeker"); }}>focus →</button>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* HEATSEEKER (single ticker) */}
      {page === "heatseeker" && (
        <div className="grid grid-cols-12 gap-3 p-4">
          <aside className="col-span-3 space-y-3">
            <div className="panel p-3" data-testid="ticker-summary">
              <div className="flex justify-between items-baseline">
                <div className="text-lg font-bold tracking-wider">{ticker.replace("^", "")}</div>
                <div className={`text-xs uppercase tracking-widest ${regimeColor}`}>{data?.nodes?.regime || "—"} γ</div>
              </div>
              <div className="text-2xl mono mt-1" data-testid="spot-price">
                ${fmt(livespot?.spot ?? data?.spot, 2)}
                {livespot && data?.spot && Math.abs(spotDelta) > 0.01 && (
                  <span className={`ml-2 text-xs ${spotDelta > 0 ? "text-emerald-400" : "text-rose-400"}`} data-testid="spot-delta">
                    {spotDelta > 0 ? "▲" : "▼"} {Math.abs(spotDelta).toFixed(2)}
                  </span>
                )}
                {livespot && <span className="ml-2 text-[9px] uppercase tracking-widest text-teal-500 flash-pulse">● live</span>}
              </div>
              <div className="text-[10px] text-slate-500">
                {data?.expiries_used?.length ? `${data.expiries_used.length} exp · ${data.expiries_used[0]} → ${data.expiries_used.slice(-1)[0]}` : ""}
              </div>
              {err && <div className="text-rose-400 text-[11px] mt-2">{err}</div>}
              <div className="dotted-divider my-3" />
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div><div className="label">King</div><div className="mono text-amber-300">{fmt(data?.nodes?.king?.strike, 0)}</div></div>
                <div><div className="label">|GEX|</div><div className="mono">{fmtAbs(data?.nodes?.king?.gex)}</div></div>
                <div><div className="label">Top Floor</div><div className="mono text-emerald-400">{fmt(data?.nodes?.floors?.[0]?.strike, 0) || "—"}</div></div>
                <div><div className="label">Top Ceiling</div><div className="mono text-rose-400">{fmt(data?.nodes?.ceilings?.[0]?.strike, 0) || "—"}</div></div>
                <div><div className="label">Polarity</div><div className="mono text-sky-300">{data?.nodes?.polarity_level ? fmt(data.nodes.polarity_level, 1) : "—"}</div></div>
                <div><div className="label">Gatekeepers</div><div className="mono">{data?.nodes?.gatekeepers?.length || 0}</div></div>
              </div>
            </div>

            <div className="panel p-3" data-testid="filter-panel">
              <div className="label mb-2">Filters / Sort</div>
              <div className="space-y-2 text-[11px]">
                <div>
                  <div className="text-slate-500 mb-1">View</div>
                  <div className="flex gap-1">
                    <button onClick={() => setView("grid")} data-testid="view-grid" className={`btn flex-1 ${view === "grid" ? "active" : ""}`}>2D Grid</button>
                    <button onClick={() => setView("bar")} data-testid="view-bar" className={`btn flex-1 ${view === "bar" ? "active" : ""}`}>Bars</button>
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Exposure</div>
                  <div className="flex gap-1">
                    <button onClick={() => setViewMode("gex")} className={`btn flex-1 ${viewMode === "gex" ? "active" : ""}`}>GEX</button>
                    <button onClick={() => setViewMode("vex")} className={`btn flex-1 ${viewMode === "vex" ? "active" : ""}`}>VEX</button>
                    <button onClick={() => setViewMode("charm")} className={`btn flex-1 ${viewMode === "charm" ? "active" : ""}`}>Charm</button>
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">DTE Filter</div>
                  <div className="flex gap-1">
                    {[{l:"0DTE",v:0},{l:"1DTE",v:1},{l:"Week",v:7},{l:"All",v:null}].map(({l,v}) => (
                      <button key={l} onClick={() => setDte(v)} data-testid={`dte-${l.toLowerCase()}`} className={`btn flex-1 ${dte === v ? "active" : ""}`}>{l}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Expiries</div>
                  <div className="flex gap-1">
                    {[2, 4, 6, 8, 12].map(n => (
                      <button key={n} onClick={() => setExpiries(n)} className={`btn flex-1 ${expiries === n ? "active" : ""}`}>{n}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Side</div>
                  <div className="flex gap-1">
                    {["all", "above", "below"].map(s => (
                      <button key={s} onClick={() => setFilters(f => ({ ...f, side: s }))} className={`btn flex-1 ${filters.side === s ? "active" : ""}`}>{s}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Lifecycle</div>
                  <div className="flex gap-1 flex-wrap">
                    {["all", "fresh", "tested", "delivered", "decaying"].map(s => (
                      <button key={s} onClick={() => setFilters(f => ({ ...f, lifecycle: s }))} className={`btn ${filters.lifecycle === s ? "active" : ""}`}>{s}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Min |GEX|</div>
                  <input type="range" min="0" max={Math.abs(data?.nodes?.king?.gex || 1e9)} step={1e7}
                    value={filters.magMin} onChange={(e) => setFilters(f => ({ ...f, magMin: Number(e.target.value) }))}
                    className="w-full" />
                  <div className="text-[10px] text-slate-500 mono">{fmtAbs(filters.magMin)}</div>
                </div>
              </div>
            </div>

            <Movers onPick={(t) => setTicker(t)} />
          </aside>

          <main className="col-span-6">
            <div className="panel p-3" data-testid="main-heatmap">
              <div className="flex justify-between items-center mb-2">
                <div>
                  <div className="label">Heatseeker · {viewMode === "vex" ? "VEX" : viewMode === "charm" ? "Charm" : "GEX"} {view === "grid" ? "Grid (Strike × Expiry)" : "Bars"}</div>
                  <div className="text-[10px] text-slate-500">{viewMode === "vex" ? "Amber = positive vanna · Pink = negative vanna · Yellow = King" : viewMode === "charm" ? "Cyan = positive charm (delta decay up) · Violet = negative charm · King highlight" : "Teal (Pika) = positive γ · Purple (Barney) = negative · Yellow-green = King · click any cell to drill"}</div>
                </div>
                <div className="flex gap-2 text-[10px]">
                  <span className="tag king">KING</span>
                  <span className="tag floor">FLOOR</span>
                  <span className="tag ceiling">CEIL</span>
                  <span className="tag gate">GATE</span>
                  <span className="tag air">AIR</span>
                </div>
              </div>
              {data ? (
                view === "grid"
                  ? <GridHeatmap data={data} filters={filters} onCellClick={(s, e) => setDrilldown({ ticker, expiry: e, strike: s })} viewMode={viewMode} />
                  : <BarHeatmap data={data} filters={filters} compact={false} viewMode={viewMode} />
              ) : (
                <div className="text-slate-500 text-xs p-6 text-center">Loading…</div>
              )}
            </div>
          </main>

          <aside className="col-span-3 space-y-3">
            {/* Flip Zone Bar */}
            {(data?.nodes?.polarity_level || data?.nodes?.vex_flip || data?.nodes?.charm_flip || data?.nodes?.max_pain) && (
              <div className="panel-2 p-2 flex gap-3 text-[10px] flex-wrap">
                {data?.nodes?.polarity_level && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-amber-400/60" />
                    <span className="text-slate-500">GEX Flip:</span>
                    <span className="text-amber-300 font-bold mono">{fmt(data.nodes.polarity_level, 1)}</span>
                    <span className="text-slate-600">({((data.nodes.polarity_level - data.spot) / data.spot * 100).toFixed(2)}%)</span>
                  </div>
                )}
                {data?.nodes?.vex_flip && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-pink-500/60" />
                    <span className="text-slate-500">VEX Flip:</span>
                    <span className="text-pink-300 font-bold mono">{fmt(data.nodes.vex_flip, 1)}</span>
                    <span className="text-slate-600">({((data.nodes.vex_flip - data.spot) / data.spot * 100).toFixed(2)}%)</span>
                  </div>
                )}
                {data?.nodes?.charm_flip && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-cyan-400/60" />
                    <span className="text-slate-500">Charm Flip:</span>
                    <span className="text-cyan-300 font-bold mono">{fmt(data.nodes.charm_flip, 1)}</span>
                    <span className="text-slate-600">({((data.nodes.charm_flip - data.spot) / data.spot * 100).toFixed(2)}%)</span>
                  </div>
                )}
                {data?.nodes?.max_pain && (
                  <div className="flex items-center gap-1.5">
                    <span className="w-2 h-2 rounded-full bg-orange-400/60" />
                    <span className="text-slate-500">Max Pain:</span>
                    <span className="text-orange-300 font-bold mono">{fmt(data.nodes.max_pain, 1)}</span>
                    <span className="text-slate-600">({((data.nodes.max_pain - data.spot) / data.spot * 100).toFixed(2)}%)</span>
                  </div>
                )}
              </div>
            )}

            {/* Stacked Nodes */}
            {data?.nodes?.stacked_nodes?.length > 0 && (
              <div className="panel-2 p-2">
                <div className="label mb-1">Stacked Nodes</div>
                <div className="space-y-0.5">
                  {data.nodes.stacked_nodes.slice(0, 4).map((s: any, i: number) => (
                    <div key={i} className="flex items-center gap-1.5 text-[9px]">
                      <span className="mono text-slate-300 w-12">{fmt(s.strike, 0)}</span>
                      <div className="flex-1 flex gap-0.5 items-center h-2">
                        <div className="h-full rounded-l bg-teal-500/70" style={{width: `${s.call_pct * 100}%`}} />
                        <div className="h-full rounded-r bg-purple-500/70" style={{width: `${s.put_pct * 100}%`}} />
                      </div>
                      <span className="text-teal-400 w-6 text-right">{Math.round(s.call_pct * 100)}</span>
                      <span className="text-purple-400 w-6 text-right">{Math.round(s.put_pct * 100)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Tug of War */}
            {data?.nodes?.tug_of_war?.length > 0 && (
              <div className="panel-2 p-2">
                <div className="label mb-1">Tug-of-War</div>
                <div className="space-y-0.5">
                  {data.nodes.tug_of_war.slice(0, 3).map((z: any, i: number) => (
                    <div key={i} className="flex items-center gap-1.5 text-[9px]">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400/60" />
                      <span className="mono text-slate-300">{fmt(z.low, 0)}–{fmt(z.high, 0)}</span>
                      <span className="text-emerald-400">+{fmtAbs(z.positive)}</span>
                      <span className="text-rose-400">{fmtAbs(z.negative)}</span>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Scenario Matrix */}
            <div className="panel-2 p-2">
              <div className="label mb-1">Scenario</div>
              <div className="space-y-1">
                {data?.nodes?.regime === "positive" && (
                  <>
                    <div className="text-[9px] text-sky-400 font-bold">◎ RANGE DAY</div>
                    <div className="text-[8px] text-slate-400">Dealers dampen vol. Mean-reversion.</div>
                    {data?.nodes?.king?.strike > data?.spot && (
                      <div className="text-[8px] text-rose-400">▽ Ceiling at {fmt(data.nodes.king.strike, 0)}</div>
                    )}
                    {data?.nodes?.king?.strike < data?.spot && (
                      <div className="text-[8px] text-emerald-400">△ Floor at {fmt(data.nodes.king.strike, 0)}</div>
                    )}
                  </>
                )}
                {data?.nodes?.regime === "negative" && (
                  <>
                    <div className="text-[9px] text-amber-400 font-bold">⚡ TREND DAY</div>
                    <div className="text-[8px] text-slate-400">Dealers amplify moves. Momentum.</div>
                  </>
                )}
                {data?.nodes?.regime === "neutral" && (
                  <>
                    <div className="text-[9px] text-orange-400 font-bold">⚠ WHIPSAW</div>
                    <div className="text-[8px] text-slate-400">Mixed signals. Reduce size.</div>
                  </>
                )}
                {data?.nodes?.polarity_level && (
                  <div className="text-[8px] text-yellow-300">⟷ Flip at {fmt(data.nodes.polarity_level, 1)}</div>
                )}
                {data?.nodes?.total_vega && Math.abs(data.nodes.total_vega) > 1e6 && (
                  <div className="text-[8px] text-slate-500">Vega: {fmtAbs(data.nodes.total_vega)}</div>
                )}
                {data?.nodes?.put_call_ratio && (
                  <div className="text-[8px] text-slate-500">P/C Ratio: <span className={data.nodes.put_call_ratio > 1 ? "text-rose-400" : "text-emerald-400"}>{data.nodes.put_call_ratio.toFixed(2)}</span></div>
                )}
              </div>
            </div>

            {/* Risk Dashboard - GCI/PGR/GDW/CAR from gex-backtesting */}
            {data?.nodes?.risk_metrics && (
              <div className="panel-2 p-2">
                <div className="label mb-1">Risk Dashboard</div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[9px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">GCI</span>
                    <span className={`mono font-bold ${data.nodes.risk_metrics.gci > 0.25 ? "text-rose-400" : data.nodes.risk_metrics.gci > 0.15 ? "text-amber-400" : "text-emerald-400"}`}>
                      {data.nodes.risk_metrics.gci.toFixed(3)}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">PGR</span>
                    <span className={`mono font-bold ${data.nodes.risk_metrics.pgr < 0.3 ? "text-rose-400" : data.nodes.risk_metrics.pgr < 0.5 ? "text-amber-400" : "text-emerald-400"}`}>
                      {(data.nodes.risk_metrics.pgr * 100).toFixed(1)}%
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">GDW</span>
                    <span className="mono text-slate-300">{fmtAbs(data.nodes.risk_metrics.gdw)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">T-Amp</span>
                    <span className="mono text-slate-300">{data.nodes.risk_metrics.time_amp}x</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">CAR Net</span>
                    <span className={`mono font-bold ${data.nodes.risk_metrics.car_net < 0 ? "text-rose-400" : "text-emerald-400"}`}>
                      {data.nodes.risk_metrics.car_net.toFixed(1)}M
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">CAR Gross</span>
                    <span className="mono text-amber-300">{data.nodes.risk_metrics.car_gross.toFixed(1)}M</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Charm Risk</span>
                    <span className={`mono font-bold ${Math.abs(data.nodes.risk_metrics.charm_risk) > 50 ? "text-rose-400" : "text-slate-300"}`}>
                      {data.nodes.risk_metrics.charm_risk.toFixed(1)}M
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Vomma</span>
                    <span className="mono text-slate-300">{fmtAbs(data?.nodes?.total_vomma)}</span>
                  </div>
                </div>
                <div className="mt-1.5 text-[8px] text-slate-600 leading-tight">
                  GCI: gamma concentration (high = fragile). PGR: protective gamma near spot (low = no cushion). 
                  CAR: convexity acceleration risk (vol spike → gamma feedback). Charm: delta decay pressure.
                </div>
              </div>
            )}

            <div className="panel p-3" data-testid="patterns-panel">
              <div className="label mb-2">Patterns Detected</div>
              <div className="space-y-2">
                {data?.patterns?.length ? data.patterns.map((p, i) => <PatternCard key={i} p={p} />) : (
                  <div className="text-slate-500 text-xs">No textbook pattern. A+ setups only.</div>
                )}
              </div>
            </div>

            <VelocityGauge velocity={data?.velocity} />

            {data && <NodesTable data={data} />}

            {data?.nodes?.air_pockets?.length > 0 && (
              <div className="panel p-3" data-testid="air-pockets-panel">
                <div className="label mb-2">Air Pockets</div>
                <div className="space-y-1 text-[11px]">
                  {data.nodes.air_pockets.map((a, i) => (
                    <div key={i} className="flex justify-between text-slate-400">
                      <span className="mono">{fmt(a.low, 0)} – {fmt(a.high, 0)}</span>
                      <span className="text-slate-500">w {a.width} · mid {fmt(a.mid, 0)}</span>
                    </div>
                  ))}
                </div>
                <div className="text-[10px] text-slate-600 mt-2 italic">Pathways, not targets.</div>
              </div>
            )}

            {/* Opportunities - from GEX-Dashboard */}
            {data?.opportunities?.length > 0 && (
              <div className="panel-2 p-2">
                <div className="label mb-1">Trading Opportunities</div>
                <div className="space-y-1.5">
                  {data.opportunities.slice(0, 5).map((o, i) => (
                    <div key={i} className={`text-[9px] p-1.5 rounded border-l-2 ${
                      o.direction === "bullish" ? "border-emerald-500 bg-emerald-500/5" :
                      o.direction === "bearish" ? "border-rose-500 bg-rose-500/5" :
                      "border-amber-500 bg-amber-500/5"
                    }`}>
                      <div className="flex justify-between items-center">
                        <span className="font-bold text-slate-200">{o.name}</span>
                        <span className={`mono text-[8px] px-1 py-px rounded ${
                          o.risk === "high" ? "bg-rose-500/20 text-rose-400" :
                          o.risk === "medium" ? "bg-amber-500/20 text-amber-400" :
                          "bg-emerald-500/20 text-emerald-400"
                        }`}>{o.risk}</span>
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
              </div>
            )}

            {/* Implied Move - from EzOptions */}
            {data?.implied_move && (
              <div className="panel-2 p-2">
                <div className="label mb-1">Implied Move</div>
                <div className="grid grid-cols-2 gap-x-3 gap-y-0.5 text-[9px]">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Expected</span>
                    <span className="mono text-amber-300 font-bold">±{data.implied_move.implied_move_pct}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Range</span>
                    <span className="mono text-slate-300">${fmt(data.implied_move.lower_range, 1)}–${fmt(data.implied_move.upper_range, 1)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">ATM Strike</span>
                    <span className="mono text-slate-300">{fmt(data.implied_move.atm_strike, 0)}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Avg IV</span>
                    <span className="mono text-slate-300">{(data.implied_move.avg_iv * 100).toFixed(1)}%</span>
                  </div>
                </div>
                <div className="mt-1.5 h-2 bg-slate-800 rounded-full overflow-hidden relative">
                  <div className="absolute inset-y-0 left-1/2 w-0.5 bg-slate-500" />
                  <div
                    className="absolute inset-y-0 bg-amber-500/30 rounded-full"
                    style={{
                      left: `${50 - data.implied_move.implied_move_pct * 5}%`,
                      right: `${50 - data.implied_move.implied_move_pct * 5}%`,
                    }}
                  />
                </div>
                <div className="text-[8px] text-slate-600 mt-1">Market expects ±{data.implied_move.implied_move_pct}% move by nearest expiry</div>
              </div>
            )}

            {/* Greek Educational Accordion - from gflows */}
            <div className="panel-2 p-2">
              <div className="label mb-1">Greek Reference</div>
              <details className="text-[9px]">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Gamma (∂Δ/∂S)</summary>
                <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">
                  Rate of delta change. Highest ATM near expiry. Long γ = dealers hedge against market (stabilizing). Short γ = dealers hedge with market (destabilizing).
                </div>
              </details>
              <details className="text-[9px] mt-1">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vanna (∂Δ/∂σ)</summary>
                <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">
                  Delta sensitivity to IV changes. Long vanna = IV up → delta up (selling pressure). Short vanna = IV up → delta down (buying pressure). Strongest near OPEX.
                </div>
              </details>
              <details className="text-[9px] mt-1">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Charm (∂Δ/∂t)</summary>
                <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">
                  Delta decay per day. For 0DTE, charm is extreme. Long charm = delta increases daily (selling). Short charm = delta decreases (buying). Forces hedging flows as expiry approaches.
                </div>
              </details>
              <details className="text-[9px] mt-1">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Vomma (∂V/∂σ)</summary>
                <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">
                  Vega sensitivity to vol changes. High vomma = option prices explode during vol spikes. Creates feedback: vol up → vega up → more hedging.
                </div>
              </details>
              <details className="text-[9px] mt-1">
                <summary className="text-slate-400 cursor-pointer hover:text-slate-300">Zomma (∂Γ/∂σ)</summary>
                <div className="text-slate-500 mt-1 pl-2 border-l border-slate-700">
                  Gamma sensitivity to vol changes. Vol spike → gamma increase → bigger hedging demand → more vol. Key driver of PUT explosions.
                </div>
              </details>
            </div>
          </aside>
        </div>
      )}

      {/* FLOWSEEKER */}
      {page === "flowseeker" && (
        <div className="p-4">
          <Flowseeker ticker={ticker} />
        </div>
      )}

      {/* DRILLDOWN MODAL */}
      {drilldown && <Drilldown {...drilldown} onClose={() => setDrilldown(null)} />}

      <footer className="border-t border-slate-800 px-4 py-2 text-[10px] text-slate-600 flex justify-between">
        <span>Data: Databento OPRA (OI) · yfinance (IV) · Polygon (aggs). GEX via Black-Scholes γ.</span>
        <span>Confluence Decoder · Skylit-style Heatseeker · {new Date().getFullYear()}</span>
      </footer>
    </div>
  );
}
