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
  if (a >= 1e6) return (n / 1e6).toFixed(2) + "M";
  if (a >= 1e3) return (n / 1e3).toFixed(2) + "K";
  return n.toFixed(0);
};
const pctClass = (v) => v > 0 ? "text-emerald-400" : v < 0 ? "text-rose-400" : "text-slate-400";

const tagFor = (kind) => ({
  king: "tag king",
  floor: "tag floor",
  ceiling: "tag ceiling",
  gate: "tag gate",
  air: "tag air",
  fresh: "tag fresh",
  tested: "tag tested",
  delivered: "tag delivered",
  decaying: "tag decaying",
}[kind] || "tag");

// ============ Heatmap component ============
function Heatmap({ data, compact = false, filters }) {
  if (!data) return null;
  const { spot, strikes, nodes } = data;
  if (!strikes || strikes.length === 0) return <div className="text-slate-500 text-xs p-4">No strike data</div>;

  // Filter strikes per UI controls
  const filtered = strikes.filter((s) => {
    if (filters?.magMin && Math.abs(s.gex) < filters.magMin) return false;
    if (filters?.lifecycle && filters.lifecycle !== "all" && s.lifecycle !== filters.lifecycle) return false;
    if (filters?.side === "above" && s.strike <= spot) return false;
    if (filters?.side === "below" && s.strike >= spot) return false;
    return true;
  });

  if (filtered.length === 0) {
    return <div className="text-slate-500 text-xs p-4">No strikes match current filters.</div>;
  }

  // Sort by strike DESCENDING so high strikes render on top (like Skylit)
  const sorted = [...filtered].sort((a, b) => b.strike - a.strike);
  const maxAbs = Math.max(...filtered.map((s) => Math.abs(s.gex)), 1);

  const kingStrike = nodes?.king?.strike;
  const floorStrikes = new Set((nodes?.floors || []).map((f) => f.strike));
  const ceilStrikes = new Set((nodes?.ceilings || []).map((f) => f.strike));
  const gkStrikes = new Set((nodes?.gatekeepers || []).map((f) => f.strike));
  const airRanges = nodes?.air_pockets || [];

  // Spot insertion index (between strikes)
  const rowHeight = compact ? 16 : 20;

  return (
    <div className="relative" data-testid="heatmap-container" style={{ paddingTop: 8, paddingBottom: 8 }}>
      {/* axis legend */}
      <div className="flex justify-between text-[10px] text-slate-500 px-2 pb-1">
        <span>← PUT GEX (Barney/neg)</span>
        <span className="text-slate-400">STRIKE</span>
        <span>CALL GEX (Pika/pos) →</span>
      </div>

      <div className="relative" style={{ minHeight: sorted.length * rowHeight }}>
        {sorted.map((s, i) => {
          const isKing = s.strike === kingStrike;
          const isFloor = floorStrikes.has(s.strike);
          const isCeil = ceilStrikes.has(s.strike);
          const isGate = gkStrikes.has(s.strike);
          const inAirPocket = airRanges.some((a) => s.strike >= a.low && s.strike <= a.high);
          const pos = s.gex > 0;
          const w = Math.max(2, (Math.abs(s.gex) / maxAbs) * 50); // 50% half-width
          const dist = Math.abs(s.strike - spot) / spot * 100;
          // Lifecycle opacity
          const lifeAlpha = { fresh: 1.0, tested: 0.78, delivered: 0.55, decaying: 0.32 }[s.lifecycle] || 0.9;

          // Determine if spot line should appear between this and previous strike
          const prev = sorted[i - 1];
          const showSpotLine = prev && prev.strike > spot && s.strike <= spot;

          return (
            <React.Fragment key={s.strike}>
              {showSpotLine && (
                <div className="flex items-center my-1 px-2 relative" data-testid="spot-line">
                  <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
                  <div className="px-2 text-[10px] tracking-widest text-teal-300 font-bold" style={{ textShadow: "0 0 8px rgba(94,234,212,0.5)" }}>
                    SPOT {fmt(spot, 2)}
                  </div>
                  <div className="flex-1 h-px" style={{ background: "linear-gradient(90deg, transparent, rgba(94,234,212,0.85), transparent)" }} />
                </div>
              )}
              <div className={`bar-row flex items-center text-[11px] mono px-2 ${inAirPocket ? "opacity-50" : ""}`} style={{ height: rowHeight }}>
                {/* PUT/NEG side (right-aligned bar) */}
                <div className="flex-1 flex justify-end pr-1">
                  {!pos && (
                    <div className="heat-bar" style={{
                      width: `${w}%`,
                      background: isKing ? "var(--king)" : `rgba(248, 113, 113, ${0.45 + 0.45 * (Math.abs(s.gex)/maxAbs)})`,
                      opacity: lifeAlpha,
                    }} />
                  )}
                </div>
                {/* Strike label center */}
                <div className={`w-20 text-center font-bold ${isKing ? "text-amber-400" : isFloor ? "text-emerald-400" : isCeil ? "text-rose-400" : isGate ? "text-sky-400" : "text-slate-300"}`}>
                  {fmt(s.strike, 0)}
                </div>
                {/* CALL/POS side */}
                <div className="flex-1 flex pl-1">
                  {pos && (
                    <div className="heat-bar" style={{
                      width: `${w}%`,
                      background: isKing ? "var(--king)" : `rgba(52, 211, 153, ${0.45 + 0.45 * (Math.abs(s.gex)/maxAbs)})`,
                      opacity: lifeAlpha,
                    }} />
                  )}
                </div>
                {/* tags */}
                {!compact && (
                  <div className="w-44 flex gap-1 justify-end items-center pl-2">
                    {isKing && <span className={tagFor("king")}>KING</span>}
                    {isFloor && <span className={tagFor("floor")}>FLOOR</span>}
                    {isCeil && <span className={tagFor("ceiling")}>CEIL</span>}
                    {isGate && <span className={tagFor("gate")}>GATE</span>}
                    {inAirPocket && <span className={tagFor("air")}>AIR</span>}
                    <span className={tagFor(s.lifecycle)} title={`tap prob ${(s.tap_prob*100).toFixed(0)}%`}>{s.lifecycle?.[0]?.toUpperCase()}{s.taps>0?`·${s.taps}`:""}</span>
                  </div>
                )}
                {!compact && (
                  <div className="w-16 text-right text-slate-500 text-[10px]">{fmtAbs(s.gex)}</div>
                )}
                {!compact && (
                  <div className="w-12 text-right text-slate-600 text-[10px]">{dist.toFixed(1)}%</div>
                )}
              </div>
            </React.Fragment>
          );
        })}
      </div>
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
    <div className={`panel-2 p-3 border ${biasColor}`} data-testid={`pattern-${p.name.toLowerCase().replace(/\s+/g,'-')}`}>
      <div className="flex justify-between items-baseline">
        <div className="text-sm font-bold tracking-wide uppercase">{p.name}</div>
        <div className="text-[10px] uppercase tracking-widest opacity-70">{p.bias}</div>
      </div>
      <div className="h-1 mt-2 mb-2 bg-slate-800 rounded">
        <div className="h-full rounded" style={{ width: `${(p.severity*100).toFixed(0)}%`, background: "currentColor", opacity: 0.6 }} />
      </div>
      <div className="text-[11px] text-slate-400 leading-snug">{p.note}</div>
    </div>
  );
}

// ============ Velocity Gauge ============
function VelocityGauge({ velocity }) {
  if (!velocity) return null;
  const score = velocity.velocity_score || 0;
  const angle = score * 180 - 90;
  const color = score > 0.4 ? "#ef4444" : score > 0.2 ? "#fbbf24" : "#34d399";
  return (
    <div className="panel-2 p-3" data-testid="velocity-gauge">
      <div className="label mb-2">Velocity Mode</div>
      <div className="flex items-center gap-3">
        <svg viewBox="0 0 100 60" width="100" height="60">
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke="#1f2a3a" strokeWidth="6" />
          <path d="M 10 55 A 40 40 0 0 1 90 55" fill="none" stroke={color} strokeWidth="6"
                strokeDasharray={`${score * 125} 200`} strokeLinecap="round" />
          <line x1="50" y1="55" x2={50 + 35*Math.cos((angle-90)*Math.PI/180)} y2={55 + 35*Math.sin((angle-90)*Math.PI/180)} stroke={color} strokeWidth="2" />
          <circle cx="50" cy="55" r="3" fill={color} />
        </svg>
        <div>
          <div className="text-2xl font-bold mono" style={{ color }}>{(score*100).toFixed(0)}</div>
          <div className="text-[10px] uppercase tracking-widest text-slate-500">rate of change</div>
        </div>
      </div>
      <div className="grid grid-cols-2 gap-2 mt-3 text-[11px]">
        <div>
          <div className="label">Floor</div>
          <div className={velocity.rolling_floor === "rolling_up" ? "text-emerald-400" : velocity.rolling_floor === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_floor || "stable").replace("_"," ")}
          </div>
        </div>
        <div>
          <div className="label">Ceiling</div>
          <div className={velocity.rolling_ceiling === "rolling_up" ? "text-emerald-400" : velocity.rolling_ceiling === "rolling_down" ? "text-rose-400" : "text-slate-400"}>
            {(velocity.rolling_ceiling || "stable").replace("_"," ")}
          </div>
        </div>
      </div>
      {velocity.floor_sequence?.length > 1 && (
        <div className="mt-2 text-[10px] text-slate-500">
          Floors: {velocity.floor_sequence.slice(0,4).map(s=>fmt(s,0)).join(" → ")}
        </div>
      )}
      {velocity.ceiling_sequence?.length > 1 && (
        <div className="text-[10px] text-slate-500">
          Ceilings: {velocity.ceiling_sequence.slice(0,4).map(s=>fmt(s,0)).join(" → ")}
        </div>
      )}
    </div>
  );
}

// ============ Trinity strip ============
function TrinityBar({ tickers, onPick }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  const fetchT = useCallback(async () => {
    setLoading(true);
    try {
      const res = await axios.get(`${API}/trinity?tickers=${tickers.join(",")}`);
      setData(res.data);
    } catch (e) {
      console.error("trinity", e);
    } finally { setLoading(false); }
  }, [tickers]);

  useEffect(() => {
    fetchT();
    const id = setInterval(fetchT, REFRESH_MS);
    return () => clearInterval(id);
  }, [fetchT]);

  if (!data) return <div className="panel p-3 text-xs text-slate-500" data-testid="trinity-loading">Loading Trinity…</div>;

  const verdictColor = {
    full_alignment: "text-emerald-400",
    partial_alignment: "text-amber-300",
    divergence: "text-rose-400",
  }[data.alignment?.verdict] || "text-slate-400";

  return (
    <div className="panel p-3" data-testid="trinity-bar">
      <div className="flex items-center justify-between mb-2">
        <div className="label">Trinity Mode · SPX / SPY / QQQ</div>
        <div className={`text-[11px] uppercase tracking-widest ${verdictColor}`}>
          {(data.alignment?.verdict || "—").replace("_"," ")} · conf {(data.alignment?.confluence*100||0).toFixed(0)}%
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2">
        {tickers.map((t) => {
          const r = data.tickers[t];
          if (!r || r.error) return <div key={t} className="panel-2 p-2 text-[11px] text-rose-400">{t}: err</div>;
          const k = r.nodes?.king;
          const regColor = r.nodes?.regime === "positive" ? "text-emerald-400" : r.nodes?.regime === "negative" ? "text-rose-400" : "text-slate-400";
          return (
            <button
              key={t}
              onClick={() => onPick && onPick(t)}
              data-testid={`trinity-tile-${t}`}
              className="panel-2 p-2 text-left hover:border-teal-500 transition"
            >
              <div className="flex justify-between items-baseline">
                <div className="font-bold text-sm">{t.replace("^","")}</div>
                <div className={`text-[10px] uppercase ${regColor}`}>{r.nodes?.regime}</div>
              </div>
              <div className="text-[11px] mono text-slate-300 mt-1">spot {fmt(r.spot, 2)}</div>
              <div className="text-[10px] mono text-slate-500">king {fmt(k?.strike, 0)} · {fmtAbs(k?.gex)}</div>
              <div className="flex gap-1 mt-1 flex-wrap">
                {(r.patterns||[]).slice(0,3).map((p,i) => (
                  <span key={i} className="text-[9px] px-1 py-px border border-slate-700 rounded uppercase tracking-wider text-slate-400">{p.name}</span>
                ))}
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}

// ============ Movers panel ============
function Movers({ onPick }) {
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let mounted = true;
    const f = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${API}/movers?limit=12`);
        if (mounted) setRows(res.data.results || []);
      } catch (e) { console.error(e); }
      finally { if (mounted) setLoading(false); }
    };
    f();
    const id = setInterval(f, 60000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  return (
    <div className="panel p-3" data-testid="movers-panel">
      <div className="label mb-2">Top Movers (prev session %)</div>
      <div className="flex flex-col gap-1 text-[11px]">
        {rows.length === 0 && <div className="text-slate-500">{loading ? "…" : "no data"}</div>}
        {rows.map((r) => (
          <button
            key={r.ticker}
            onClick={() => onPick && onPick(r.ticker)}
            data-testid={`mover-${r.ticker}`}
            className="flex justify-between items-center px-2 py-1 hover:bg-slate-800/40 rounded"
          >
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
      : data.nodes.floors?.some(f=>f.strike===s.strike) ? "Floor"
      : data.nodes.ceilings?.some(f=>f.strike===s.strike) ? "Ceiling"
      : data.nodes.gatekeepers?.some(f=>f.strike===s.strike) ? "Gatekeeper"
      : null;
    return { ...s, role, mag: Math.abs(s.gex), dist: Math.abs(s.strike - spot) / spot * 100 };
  }).filter(s => s.role || s.mag > 0);

  const sorted = [...all].sort((a,b) => {
    const va = a[sortKey], vb = b[sortKey];
    if (va == null) return 1;
    if (vb == null) return -1;
    return sortDir === "desc" ? vb - va : va - vb;
  });

  const head = (k, l) => (
    <th className="text-left text-[10px] uppercase tracking-widest text-slate-500 font-normal px-2 py-1 cursor-pointer hover:text-teal-400"
        onClick={() => { setSortKey(k); setSortDir(d => sortKey===k && d==="desc" ? "asc":"desc"); }}>
      {l}{sortKey===k ? (sortDir==="desc"?" ↓":" ↑"):""}
    </th>
  );

  return (
    <div className="panel p-3" data-testid="nodes-table">
      <div className="label mb-2">Structural Nodes</div>
      <div className="overflow-y-auto" style={{ maxHeight: 280 }}>
        <table className="w-full text-[11px] mono">
          <thead className="sticky top-0 bg-slate-900">
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
                  {s.role && (
                    <span className={`tag ${s.role==="King"?"king":s.role==="Floor"?"floor":s.role==="Ceiling"?"ceiling":"gate"}`}>{s.role}</span>
                  )}
                </td>
                <td className="px-2 py-1 text-slate-300">{fmtAbs(s.mag)}</td>
                <td className={`px-2 py-1 ${s.gex>0?"text-emerald-400":"text-rose-400"}`}>{s.gex>0?"+":""}{fmtAbs(s.gex)}</td>
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

// ============ Main App ============
export default function App() {
  const [ticker, setTicker] = useState("SPY");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState(null);
  const [expiries, setExpiries] = useState(3);
  const [trinityMode, setTrinityMode] = useState(false);
  const [trinityData, setTrinityData] = useState(null);
  const [filters, setFilters] = useState({ magMin: 0, lifecycle: "all", side: "all" });
  const [customTicker, setCustomTicker] = useState("");
  const lastRefresh = useRef(null);

  const fetchHeatmap = useCallback(async (t) => {
    setLoading(true); setErr(null);
    try {
      const res = await axios.get(`${API}/heatmap/${encodeURIComponent(t)}?expiries=${expiries}`);
      setData(res.data);
      lastRefresh.current = new Date();
    } catch (e) {
      setErr(e.response?.data?.detail || e.message);
    } finally { setLoading(false); }
  }, [expiries]);

  const fetchTrinity = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/trinity?tickers=${TRINITY.join(",")}`);
      setTrinityData(res.data);
    } catch (e) { console.error(e); }
  }, []);

  useEffect(() => {
    if (trinityMode) {
      fetchTrinity();
      const id = setInterval(fetchTrinity, REFRESH_MS);
      return () => clearInterval(id);
    } else {
      fetchHeatmap(ticker);
      const id = setInterval(() => fetchHeatmap(ticker), REFRESH_MS);
      return () => clearInterval(id);
    }
  }, [ticker, trinityMode, fetchHeatmap, fetchTrinity]);

  const regimeColor = data?.nodes?.regime === "positive" ? "text-emerald-400" : data?.nodes?.regime === "negative" ? "text-rose-400" : "text-slate-400";

  return (
    <div className="App min-h-screen" style={{ background: "var(--bg)" }}>
      {/* HEADER */}
      <header className="border-b border-slate-800 px-4 py-2 flex items-center justify-between sticky top-0 z-20" style={{ background: "rgba(7,9,13,0.95)", backdropFilter: "blur(8px)" }}>
        <div className="flex items-center gap-4">
          <div className="flex items-baseline gap-2">
            <span className="text-sm font-bold tracking-widest text-teal-300">CONFLUENCE DECODER</span>
            <span className="text-[10px] text-slate-500">/ Heatseeker GEX</span>
          </div>
          <div className="dotted-divider w-8" />
          <div className="flex gap-1">
            {DEFAULT_TICKERS.map(t => (
              <button
                key={t}
                onClick={() => { setTicker(t); setTrinityMode(false); }}
                data-testid={`ticker-btn-${t}`}
                className={`btn ${!trinityMode && ticker===t ? "active":""}`}
              >
                {t.replace("^","")}
              </button>
            ))}
            <button
              onClick={() => setTrinityMode(true)}
              data-testid="trinity-toggle"
              className={`btn ${trinityMode ? "active":""}`}
            >△ TRINITY</button>
          </div>
          <input
            type="text"
            value={customTicker}
            onChange={(e) => setCustomTicker(e.target.value.toUpperCase())}
            onKeyDown={(e) => { if (e.key==="Enter" && customTicker) { setTicker(customTicker); setTrinityMode(false); }}}
            placeholder="add ticker…"
            data-testid="custom-ticker-input"
            className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 w-28 focus:outline-none focus:border-teal-500"
          />
        </div>
        <div className="flex items-center gap-3 text-[11px] text-slate-500">
          <span>refresh 30s</span>
          {loading && <span className="text-teal-400 flash-pulse">● syncing</span>}
          {!loading && lastRefresh.current && <span className="text-slate-600">last {lastRefresh.current.toLocaleTimeString()}</span>}
        </div>
      </header>

      {/* TRINITY MODE */}
      {trinityMode && trinityData && (
        <div className="p-4 space-y-4" data-testid="trinity-view">
          <div className="panel p-3">
            <div className="flex justify-between items-center">
              <div>
                <div className="label">Alignment Verdict</div>
                <div className={`text-2xl font-bold uppercase tracking-wider ${
                  trinityData.alignment.verdict === "full_alignment" ? "text-emerald-400" :
                  trinityData.alignment.verdict === "partial_alignment" ? "text-amber-300" : "text-rose-400"
                }`}>{trinityData.alignment.verdict.replace("_"," ")}</div>
              </div>
              <div className="text-right">
                <div className="label">Regime · Confluence</div>
                <div className="text-lg mono">
                  <span className={trinityData.alignment.regime==="positive"?"text-emerald-400":trinityData.alignment.regime==="negative"?"text-rose-400":"text-slate-400"}>{trinityData.alignment.regime}</span>
                  <span className="text-slate-500"> · </span>
                  <span>{(trinityData.alignment.confluence*100).toFixed(0)}%</span>
                </div>
              </div>
            </div>
            <div className="text-[11px] text-slate-500 mt-2">
              {trinityData.alignment.verdict === "full_alignment" && "All three indices agree. Highest-conviction environment — A+ setups live here."}
              {trinityData.alignment.verdict === "partial_alignment" && "Two-of-three confluence. Trade with reduced size; the third is a warning, not a stop sign."}
              {trinityData.alignment.verdict === "divergence" && "Cross-instrument disagreement. Wait. Forcing a trade into divergence is hope, not edge."}
            </div>
          </div>
          <div className="grid grid-cols-3 gap-3">
            {TRINITY.map((t) => {
              const d = trinityData.tickers[t];
              if (!d || d.error) return <div key={t} className="panel p-3 text-rose-400 text-xs">{t}: {d?.error}</div>;
              return (
                <div key={t} className="panel p-3" data-testid={`trinity-panel-${t}`}>
                  <div className="flex justify-between items-baseline mb-2">
                    <div className="font-bold text-sm">{t.replace("^","")}</div>
                    <button className="text-[10px] text-teal-400 underline" onClick={() => { setTicker(t); setTrinityMode(false); }}>focus →</button>
                  </div>
                  <div className="text-[11px] mono text-slate-400">spot {fmt(d.spot,2)} · king {fmt(d.nodes?.king?.strike,0)}</div>
                  <div className="mt-2">
                    <Heatmap data={d} compact filters={{}} />
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* SINGLE TICKER MODE */}
      {!trinityMode && (
        <div className="grid grid-cols-12 gap-3 p-4">
          {/* LEFT: filters + movers */}
          <aside className="col-span-3 space-y-3">
            <div className="panel p-3" data-testid="ticker-summary">
              <div className="flex justify-between items-baseline">
                <div className="text-lg font-bold tracking-wider">{ticker.replace("^","")}</div>
                <div className={`text-xs uppercase tracking-widest ${regimeColor}`}>{data?.nodes?.regime || "—"} γ</div>
              </div>
              <div className="text-2xl mono mt-1">${fmt(data?.spot, 2)}</div>
              <div className="text-[10px] text-slate-500">
                {data?.expiries_used?.length ? `${data.expiries_used.length} expiries · ${data.expiries_used[0]} → ${data.expiries_used.slice(-1)[0]}` : ""}
              </div>
              {err && <div className="text-rose-400 text-[11px] mt-2">{err}</div>}
              <div className="dotted-divider my-3" />
              <div className="grid grid-cols-2 gap-2 text-[11px]">
                <div><div className="label">King</div><div className="mono text-amber-400">{fmt(data?.nodes?.king?.strike,0)}</div></div>
                <div><div className="label">|GEX|</div><div className="mono">{fmtAbs(data?.nodes?.king?.gex)}</div></div>
                <div><div className="label">Top Floor</div><div className="mono text-emerald-400">{fmt(data?.nodes?.floors?.[0]?.strike,0) || "—"}</div></div>
                <div><div className="label">Top Ceiling</div><div className="mono text-rose-400">{fmt(data?.nodes?.ceilings?.[0]?.strike,0) || "—"}</div></div>
                <div><div className="label">Polarity</div><div className="mono text-sky-300">{data?.nodes?.polarity_level ? fmt(data.nodes.polarity_level,1) : "—"}</div></div>
                <div><div className="label">Gatekeepers</div><div className="mono">{data?.nodes?.gatekeepers?.length || 0}</div></div>
              </div>
            </div>

            <div className="panel p-3" data-testid="filter-panel">
              <div className="label mb-2">Filters / Sort</div>
              <div className="space-y-2 text-[11px]">
                <div>
                  <div className="text-slate-500 mb-1">Expiries near term</div>
                  <div className="flex gap-1">
                    {[1,2,3,4,6].map(n => (
                      <button key={n} onClick={() => setExpiries(n)} className={`btn flex-1 ${expiries===n?"active":""}`}>{n}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Side relative to spot</div>
                  <div className="flex gap-1">
                    {["all","above","below"].map(s => (
                      <button key={s} onClick={() => setFilters(f=>({...f,side:s}))} className={`btn flex-1 ${filters.side===s?"active":""}`}>{s}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Lifecycle</div>
                  <div className="flex gap-1 flex-wrap">
                    {["all","fresh","tested","delivered","decaying"].map(s => (
                      <button key={s} onClick={() => setFilters(f=>({...f,lifecycle:s}))} className={`btn ${filters.lifecycle===s?"active":""}`}>{s}</button>
                    ))}
                  </div>
                </div>
                <div>
                  <div className="text-slate-500 mb-1">Min |GEX| threshold</div>
                  <input type="range" min="0" max={Math.abs(data?.nodes?.king?.gex||1e9)} step={1e7}
                         value={filters.magMin} onChange={(e)=>setFilters(f=>({...f,magMin:Number(e.target.value)}))}
                         className="w-full" />
                  <div className="text-[10px] text-slate-500 mono">{fmtAbs(filters.magMin)}</div>
                </div>
              </div>
            </div>

            <Movers onPick={(t) => { setTicker(t); setTrinityMode(false); }} />
          </aside>

          {/* CENTER: heatmap */}
          <main className="col-span-6">
            <div className="panel p-3" data-testid="main-heatmap">
              <div className="flex justify-between items-center mb-2">
                <div>
                  <div className="label">Heatseeker · GEX by Strike</div>
                  <div className="text-[10px] text-slate-500">Pos (green) = Pika · dealers long γ (contrarian) · Neg (red) = Barney · pro-cyclical · Gold = King</div>
                </div>
                <div className="flex gap-2 text-[10px]">
                  <span className="tag king">KING</span>
                  <span className="tag floor">FLOOR</span>
                  <span className="tag ceiling">CEIL</span>
                  <span className="tag gate">GATE</span>
                  <span className="tag air">AIR</span>
                </div>
              </div>
              {data ? <Heatmap data={data} filters={filters} /> : <div className="text-slate-500 text-xs p-6 text-center">Loading…</div>}
            </div>
          </main>

          {/* RIGHT: patterns + velocity + nodes */}
          <aside className="col-span-3 space-y-3">
            <div className="panel p-3" data-testid="patterns-panel">
              <div className="label mb-2">Patterns Detected</div>
              <div className="space-y-2">
                {data?.patterns?.length ? data.patterns.map((p,i) => <PatternCard key={i} p={p} />) : (
                  <div className="text-slate-500 text-xs">No textbook pattern. Trade only A+ structure.</div>
                )}
              </div>
            </div>

            <VelocityGauge velocity={data?.velocity} />

            {data && <NodesTable data={data} />}

            {data?.nodes?.air_pockets?.length > 0 && (
              <div className="panel p-3" data-testid="air-pockets-panel">
                <div className="label mb-2">Air Pockets</div>
                <div className="space-y-1 text-[11px]">
                  {data.nodes.air_pockets.map((a,i) => (
                    <div key={i} className="flex justify-between text-slate-400">
                      <span className="mono">{fmt(a.low,0)} – {fmt(a.high,0)}</span>
                      <span className="text-slate-500">width {a.width} · mid {fmt(a.mid,0)}</span>
                    </div>
                  ))}
                </div>
                <div className="text-[10px] text-slate-600 mt-2 italic">Pathways, not targets.</div>
              </div>
            )}
          </aside>
        </div>
      )}

      {/* FOOTER */}
      <footer className="border-t border-slate-800 px-4 py-2 text-[10px] text-slate-600 flex justify-between">
        <span>Data: Polygon.io (aggs, movers) + yfinance (chains, IV). GEX via Black-Scholes γ.</span>
        <span>Confluence Decoder · Skylit-style Heatseeker · {new Date().getFullYear()}</span>
      </footer>
    </div>
  );
}
