import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Plot from "react-plotly.js";

const API = "http://localhost:8000/api/flowseeker";
const DASH_API = "http://localhost:8000/api";
const TICKERS = ["SPY","QQQ","IWM","DIA","TLT","AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL"];

// ── Blademap signal types → colour chips ──────────────────────────────────
// Mirrors backend/services/institutional_detector.py SIGNAL_TYPE_COLORS.
const CLASS_COLORS = {
  CALL_SWEEP: "#fb7185",
  PUT_SWEEP: "#34d399",
  CALL_BLOCK: "#84cc16",
  PUT_BLOCK: "#fb923c",
  FLOOR_SWEEP: "#2dd4bf",          // teal: dealer floor buy-in
  GOLDEN_SWEEP: "#facc15",         // gold: zero-gamma flip area
  HIGH_VOLUME: "#fbbf24",
  HIGH_IV: "#f43f5e",
  OI_SPIKE: "#a855f7",
  DELTA_EXTREME: "#38bdf8",
  PREMIUM_CONCENTRATION: "#22c55e",
  UNUSUAL_VOL_OI: "#94a3b8",
  high_volume: "#fbbf24",          // legacy aliases (kept from v1)
  high_iv: "#f43f5e",
  oi_spike: "#a855f7",
  delta_extreme: "#38bdf8",
  premium_concentration: "#22c55e",
  sweep: "#f43f5e",
  block: "#a855f7",
  unusual: "#fbbf24",
  regular: "#64748b",
};

const DIRECTION_COLORS = {
  BULLISH: "#34d399",
  BEARISH: "#fb7185",
  NEUTRAL: "#94a3b8",
};

// ── Sub-score definitions ─────────────────────────────────────────────────
// Sum of four caps = 100.  Order matches the "why this score" meter.
const SUB_SCORE_KEYS = [
  { key: "statistical_anomaly", label: "Anomaly",   max: 30, colour: "#fbbf24" },
  { key: "institutional_pattern", label: "Pattern",  max: 25, colour: "#22c55e" },
  { key: "market_context",       label: "Context",  max: 20, colour: "#38bdf8" },
  { key: "price_impact",          label: "Impact",   max: 25, colour: "#a855f7" },
];

function convictionColor(score) {
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#fbbf24";
  if (score >= 40) return "#a3a3a3";
  return "#64748b";
}
function convictionLabel(score) {
  if (score >= 80) return "HIGH";
  if (score >= 60) return "MED";
  if (score >= 40) return "WATCH";
  return "LOW";
}

// Tiny render-time formatter that never throws on missing / weird input.
function safe(n, digits = 0) {
  if (n == null || Number.isNaN(n)) return "—";
  const v = Number(n);
  if (!Number.isFinite(v)) return "—";
  return v.toFixed(digits);
}

export default function FlowseekerProTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expiryIdx, setExpiryIdx] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [gexData, setGexData] = useState(null);
  const [soundEnabled, setSoundEnabled] = useState(true);
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [ofi, setOfi] = useState(null);
  const [regime, setRegime] = useState(null);
  const [vpin, setVpin] = useState(null);
  const [kyleLambda, setKyleLambda] = useState(null);
  const [amihud, setAmihud] = useState(null);
  const [composite, setComposite] = useState(null);
  const [confidence, setConfidence] = useState(null);
  const [replay, setReplay] = useState(null);
  const [realisedVol, setRealisedVol] = useState(null);
  const prevAlertCount = useRef(0);
  const audioRef = useRef(null);

  const fetchChain = useCallback(async (sym) => {
    if (!sym) return;
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/chain/${sym}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      if (!d?.chain?.length) throw new Error("No chain data");
      setChain(d);
      setExpiryIdx(0);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e.message || "Failed to fetch chain");
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchAlerts = useCallback(async (sym) => {
    try {
      const r = await fetch(`${API}/alerts/${sym}?min_premium=50000`);
      if (!r.ok) return;
      const d = await r.json();
      if (d.alerts?.length > prevAlertCount.current && soundEnabled && audioRef.current) {
        audioRef.current.play().catch(() => {});
      }
      prevAlertCount.current = d.alerts?.length || 0;
      setAlerts(d.alerts || []);
    } catch (e) { /* silent */ }
  }, [soundEnabled]);

  const fetchGex = useCallback(async (sym) => {
    try {
      const r = await fetch(`${DASH_API}/advanced/${sym}?expiries=4`);
      if (!r.ok) return;
      const d = await r.json();
      setGexData(d);
    } catch (e) { /* silent */ }
  }, []);

  // Multi-level OFI (Xu/Gould/Howison 2019) — polls less often than alerts.
  // First poll seeds a chain snapshot; second poll produces a real OFI
  // vector from the deltas. Capture ``sym`` at fetch start so a stale
  // response from a prior ticker swap doesn't overwrite fresh state.
  const ofiWarmingRef = useRef(true);
  const activeSymRef = useRef(ticker);
  useEffect(() => { activeSymRef.current = ticker; }, [ticker]);
  const fetchOfi = useCallback(async (sym) => {
    try {
      const r = await fetch(`${API}/ofi/${sym}?levels=5`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && Array.isArray(d.of_per_level) && activeSymRef.current === sym) {
        ofiWarmingRef.current = (d.snaps_used || 0) < 2;
        setOfi(d);
      }
    } catch (e) { /* silent */ }
  }, []);

  // VPIN toxicity (paper #5 — Easley/López de Prado/O'Hara 2013) — mirrors
  // the OFI/HMM staleness guard via activeSymRef.
  const fetchVpin = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/vpin/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setVpin(d);
    } catch (e) { /* silent */ }
  }, []);

  // Kyle's λ (market-depth; Kyle 1985). Same staleness guard pattern.
  const fetchKylesLambda = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/lambda/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setKyleLambda(d);
    } catch (e) { /* silent */ }
  }, []);

  // Amihud illiquidity ratio (Amihud 2002); sister metric to Kyle's λ —
  // measures |r| / DV (unsigned total-flow depth). Same staleness guard.
  const fetchAmihud = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/amihud/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setAmihud(d);
    } catch (e) { /* silent */ }
  }, []);

  // Composite Flow Score — synthesises Amihud + Kyle + VPIN + HMM + OFI
  // into a single 0..100 tradable-conviction headline. Same staleness
  // guard pattern as the other analytics endpoints.
  const fetchComposite = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/composite/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setComposite(d);
    } catch (e) { /* silent */ }
  }, []);

  // Chain Replay — pulls /replay/{sym} on a longer cadence (every poll)
  // and renders the last ~64 composite snapshots as a sparkline + label
  // timeline. Same staleness guard pattern.
  const fetchReplay = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/replay/${sym}?last_n=64`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setReplay(d);
    } catch (e) { /* silent */ }
  }, []);

  // Composite Confidence Bands — pulls /composite-confidence/{sym} and
  // wraps the live Composite Flow Score point estimate with a 95% bootstrap
  // confidence interval (lower..upper) + a 3-band confidence label. Same
  // staleness guard pattern.
  const fetchConfidence = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/composite-confidence/${sym}?last_n=64`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setConfidence(d);
    } catch (e) { /* silent */ }
  }, []);

  // Market Regime Detector — pulls /regime/{sym} and fills the HMM
  // 3-state posterior + regime label into the summary bar.
  const fetchRegime = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/regime/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setRegime(d);
    } catch (e) { /* silent */ }
  }, []);

  // Realised Volatility — Andersen-Bollerslev 1998 / BNS 2002 high-frequency
  // RV + BV estimators over a 60-obs rolling window (~30 min @ 30s cadence).
  // Companion metric to Composite Score — answers "how MUCH is moving" via
  // annualised decimals, complementing HMM regime's "which direction".
  const fetchRealisedVol = useCallback(async (sym) => {
    if (!sym) return;
    try {
      const r = await fetch(`${API}/realized-volatility/${sym}`);
      if (!r.ok) return;
      const d = await r.json();
      if (d && activeSymRef.current === sym) setRealisedVol(d);
    } catch (e) { /* silent */ }
  }, []);

  useEffect(() => { if (active) { fetchChain(ticker); fetchGex(ticker); fetchOfi(ticker); fetchRegime(ticker); fetchVpin(ticker); fetchKylesLambda(ticker); fetchAmihud(ticker); fetchComposite(ticker); fetchConfidence(ticker); fetchRealisedVol(ticker); fetchReplay(ticker); } }, [ticker, active, fetchChain, fetchGex, fetchOfi, fetchRegime, fetchVpin, fetchKylesLambda, fetchAmihud, fetchComposite, fetchConfidence, fetchRealisedVol, fetchReplay]);
  useEffect(() => { if (!active) return; const id = setInterval(() => { fetchChain(ticker); fetchAlerts(ticker); fetchOfi(ticker); fetchRegime(ticker); fetchVpin(ticker); fetchKylesLambda(ticker); fetchAmihud(ticker); fetchComposite(ticker); fetchConfidence(ticker); fetchRealisedVol(ticker); fetchReplay(ticker); }, 30000); return () => clearInterval(id); }, [ticker, active, fetchChain, fetchAlerts, fetchOfi, fetchRegime, fetchVpin, fetchKylesLambda, fetchAmihud, fetchComposite, fetchConfidence, fetchRealisedVol, fetchReplay]);
  // Reset OFI warming + clear stale OFI/Regime/VPIN/Kyle/Amihud/Composite/Confidence/RV/Replay on ticker swap
  useEffect(() => { ofiWarmingRef.current = true; setOfi(null); setRegime(null); setVpin(null); setKyleLambda(null); setAmihud(null); setComposite(null); setConfidence(null); setRealisedVol(null); setReplay(null); }, [ticker]);
  useEffect(() => { if (!active) return; fetchAlerts(ticker); const id = setInterval(() => fetchAlerts(ticker), 10000); return () => clearInterval(id); }, [ticker, active, fetchAlerts]);

  // Build OI Profile chart (unchanged from v1 — chart layer was already good)
  useEffect(() => {
    if (!chain) { setChartData(null); return; }
    try {
      const exp = chain.chain[expiryIdx] || chain.chain[0];
      if (!exp?.strikes?.length) { setChartData(null); return; }
      const params = chain.params || [];
      const oiIdx = params.indexOf("openInterest");
      const deltaIdx = params.indexOf("delta");
      const spotIdx = params.indexOf("underlying_price");
      const volIdx = params.indexOf("volume");

      const strikes = [], callOI = [], putOI = [], deltaLine = [];
      const spotRaw = exp.strikes[0]?.[1];
      const spot = spotRaw && spotIdx >= 0 ? (Number(spotRaw[spotIdx - 1]) || 0) : 0;

      for (const s of exp.strikes) {
        if (!s || s.length < 3) continue;
        const strike = Number(s[0]) || 0;
        if (strike <= 0) continue;
        const cv = Array.isArray(s[1]) ? s[1] : [];
        const pv = Array.isArray(s[2]) ? s[2] : [];
        strikes.push(strike);
        callOI.push(oiIdx > 0 ? (Number(cv[oiIdx - 1]) || 0) : 0);
        putOI.push(oiIdx > 0 ? (Number(pv[oiIdx - 1]) || 0) : 0);
        if (deltaIdx > 0 && cv[deltaIdx - 1] != null) {
          deltaLine.push(Number(cv[deltaIdx - 1]) || 0.5);
        } else {
          const dist = (strike - spot) / Math.max(spot * 0.15, 1);
          deltaLine.push(1 / (1 + Math.exp(-dist * 2)));
        }
      }
      if (!strikes.length) { setChartData(null); return; }
      const maxOI = Math.max(...callOI, ...putOI, 1);

      const alertStrikes = new Set(alerts.filter(a => a.confidence_score >= 70).map(a => a.strike));

      const traces = [
        { y: strikes, x: callOI.map(v => -(v / maxOI) * 100), type: "bar", orientation: "h", name: "Call OI",
          marker: { color: strikes.map(s => alertStrikes.has(s) ? "#34d399" : "rgba(52,211,153,0.6)") },
          customdata: callOI, hovertemplate: "Call OI: %{customdata:,.0f}<extra></extra>" },
        { y: strikes, x: putOI.map(v => (v / maxOI) * 100), type: "bar", orientation: "h", name: "Put OI",
          marker: { color: strikes.map(s => alertStrikes.has(s) ? "#fb7185" : "rgba(244,63,94,0.6)") },
          customdata: putOI, hovertemplate: "Put OI: %{customdata:,.0f}<extra></extra>" },
        { y: strikes, x: deltaLine.map(v => (v - 0.5) * 80), type: "scatter", mode: "lines", name: "Delta",
          line: { color: "#fbbf24", width: 2.5 }, xaxis: "x2" },
      ];

      const layout = {
        title: { text: `OI Profile — ${ticker} (${exp.expiration})`, font: { color: "#e2e8f0", size: 13 } },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", barmode: "overlay",
        margin: { l: 55, r: 65, t: 40, b: 35 },
        xaxis: { title: "OI (norm)", color: "#94a3b8", zeroline: true, zerolinecolor: "#475569", gridcolor: "#1e293b", tickfont: { size: 9 }, range: [-100, 100] },
        xaxis2: { overlaying: "x", side: "top", title: "Delta", color: "#fbbf24", tickfont: { size: 8, color: "#fbbf24" }, range: [-40, 40], tickvals: [-40, -20, 0, 20, 40], ticktext: ["1.0", "0.75", "0.5", "0.25", "0.0"] },
        yaxis: { title: "Strike", color: "#94a3b8", gridcolor: "#1e293b", tickfont: { size: 9 } },
        legend: { font: { color: "#94a3b8", size: 10 }, orientation: "h", y: 1.08 },
        hovermode: "y unified", showlegend: true,
        height: Math.max(400, strikes.length * 14),
        shapes: spot > 0 ? [{ type: "line", x0: -100, x1: 100, y0: spot, y1: spot, line: { color: "#38bdf8", width: 2, dash: "dot" } }] : [],
        annotations: spot > 0 ? [{ x: 95, y: spot, text: `$${spot.toFixed(2)}`, showarrow: false, font: { color: "#38bdf8", size: 10 }, xref: "x", yref: "y" }] : [],
      };
      setChartData({ traces, layout });
    } catch (e) {
      console.error("FlowseekerPro chart error:", e);
      setChartData(null);
    }
  }, [chain, expiryIdx, ticker, alerts]);

  const expiries = chain?.chain?.map(c => c.expiration) || [];

  const stats = useMemo(() => {
    const highConf = alerts.filter(a => (a.conviction_score ?? a.confidence_score ?? 0) >= 70);
    const sweeps = alerts.filter(a => (a.signal_type || a.classification || "").includes("SWEEP"));
    const blocks = alerts.filter(a => (a.signal_type || a.classification || "").includes("BLOCK"));
    const totalPremium = alerts.reduce((s, a) => s + (a.premium || a.indicators?.estimated_premium || 0), 0);
    return { highConf: highConf.length, sweeps: sweeps.length, blocks: blocks.length, totalAlerts: alerts.length, totalPremium };
  }, [alerts]);

  // Top-of-tab summary: regime + dealer positioning pulled from highest-conviction alert.
  const topAlert = alerts[0];
  const summary = useMemo(() => {
    if (!topAlert) {
      return { regime: "QUIET", dealer: "—", zeroCross: null, rationale: null };
    }
    const ctx = topAlert.context || {};
    return {
      regime: ctx.market_regime || "UNKNOWN",
      dealer: ctx.dealer_positioning || "—",
      zeroCross: ctx.zero_gamma_cross ?? null,
      rationale: topAlert.rationale || null,
    };
  }, [topAlert]);

  return (
    <div className="flex h-full overflow-hidden">
      <audio ref={audioRef} src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQo6l9/Ss2QdBz2Y3dKyaB8F" preload="auto" />

      {/* Sidebar — unchanged from v1 except for the new summary panel */}
      <div className="w-56 flex-shrink-0 border-r border-slate-800/50 bg-[#0b0d12] p-3 space-y-3 overflow-y-auto">
        <div>
          <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-1">Ticker</div>
          <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
            onKeyDown={e => { if (e.key === "Enter") fetchChain(ticker); }}
            className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2 py-1.5 text-sm text-slate-200 outline-none focus:border-sky-500/50 font-mono" />
          <div className="flex flex-wrap gap-1 mt-1.5">
            {TICKERS.map(t => (
              <button key={t} onClick={() => setTicker(t)}
                className={`text-[9px] px-1.5 py-0.5 rounded-md font-mono transition-all ${t === ticker ? "bg-sky-600 text-white shadow-lg shadow-sky-500/20" : "bg-slate-800/50 text-slate-500 hover:bg-slate-700/50"}`}>{t}</button>
            ))}
          </div>
        </div>

        {expiries.length > 0 && (
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-1">Expiry</div>
            <select value={expiryIdx} onChange={e => setExpiryIdx(Number(e.target.value))}
              className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2 py-1.5 text-xs text-slate-200">
              {expiries.map((exp, i) => <option key={i} value={i}>{exp}</option>)}
            </select>
          </div>
        )}

        <div className="border-t border-slate-800/50 pt-2">
          <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-1.5">Summary</div>
          <div className="grid grid-cols-2 gap-1.5">
            <div className="bg-slate-800/30 rounded-lg p-2 text-center">
              <div className="text-[8px] text-slate-500 uppercase">Alerts</div>
              <div className="text-sm font-bold text-slate-200">{stats.totalAlerts}</div>
            </div>
            <div className="bg-slate-800/30 rounded-lg p-2 text-center">
              <div className="text-[8px] text-slate-500 uppercase">High Conf</div>
              <div className="text-sm font-bold text-emerald-400">{stats.highConf}</div>
            </div>
            <div className="bg-slate-800/30 rounded-lg p-2 text-center">
              <div className="text-[8px] text-slate-500 uppercase">Sweeps</div>
              <div className="text-sm font-bold text-rose-400">{stats.sweeps}</div>
            </div>
            <div className="bg-slate-800/30 rounded-lg p-2 text-center">
              <div className="text-[8px] text-slate-500 uppercase">Premium</div>
              <div className="text-sm font-bold text-amber-400">${(stats.totalPremium / 1e6).toFixed(1)}M</div>
            </div>
          </div>
        </div>

        <div className="text-[9px] space-y-1 border-t border-slate-800/50 pt-2">
          {loading && <div className="text-amber-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse" />Loading chain...</div>}
          {error && <div className="text-rose-400">⚠ {error}</div>}
          {chain && !loading && (
            <>
              <div className="text-emerald-400 flex items-center gap-1"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />LIVE — {chain.chain.length} exp</div>
              {lastUpdate && <div className="text-slate-600">Updated {lastUpdate}</div>}
            </>
          )}
        </div>

        <div className="flex items-center justify-between border-t border-slate-800/50 pt-2">
          <span className="text-[9px] text-slate-500">🔔 Sweep Alerts</span>
          <button onClick={() => setSoundEnabled(!soundEnabled)}
            className={`text-[9px] px-2 py-0.5 rounded-full font-bold ${soundEnabled ? "bg-emerald-600/20 text-emerald-400" : "bg-slate-800 text-slate-500"}`}>
            {soundEnabled ? "ON" : "OFF"}
          </button>
        </div>

        <button onClick={() => { fetchChain(ticker); fetchAlerts(ticker); }}
          className="w-full text-[9px] py-1.5 bg-slate-800/50 hover:bg-slate-700/50 rounded-lg text-slate-400 border border-slate-700/30">↻ Refresh</button>
      </div>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#0a0c10]">
        {/* Top bar */}
        <div className="flex items-center gap-3 px-4 py-2 border-b border-slate-800/30 bg-[#0c0e14]">
          <span className="text-sm font-bold text-slate-100">{ticker}</span>
          {chain && <span className="text-[9px] text-emerald-400 px-1.5 py-0.5 bg-emerald-500/10 rounded-full font-bold">● LIVE</span>}
          {chain && <span className="text-[9px] text-slate-500">{chain.chain?.length || 0} expirations</span>}
          {stats.highConf > 0 && <span className="text-[9px] text-emerald-400 px-1.5 py-0.5 bg-emerald-500/10 rounded-full font-bold">{stats.highConf} HIGH</span>}
          {stats.sweeps > 0 && <span className="text-[9px] text-rose-400 px-1.5 py-0.5 bg-rose-500/10 rounded-full font-bold">{stats.sweeps} SWEEPS</span>}
          {stats.blocks > 0 && <span className="text-[9px] text-orange-300 px-1.5 py-0.5 bg-orange-500/10 rounded-full font-bold">{stats.blocks} BLOCKS</span>}
        </div>

        {/* ─── NEW: Blademap positioning summary bar ─── */}
        <div className="px-4 py-2 border-b border-slate-800/30 bg-[#0a0c10] flex flex-wrap items-center gap-2 text-[10px]">
          <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Context</span>
          <span className="px-2 py-0.5 rounded-full font-mono"
            title="market_regime from top conviction alert"
            style={{ background: "rgba(56,189,248,0.10)", color: "#38bdf8", border: "1px solid rgba(56,189,248,0.25)" }}>
            regime: {summary.regime}
          </span>
          <span className="px-2 py-0.5 rounded-full font-mono"
            title="dealer_positioning from top conviction alert"
            style={{ background: summary.dealer?.includes("short") ? "rgba(244,63,94,0.10)" : "rgba(34,197,94,0.10)", color: summary.dealer?.includes("short") ? "#fb7185" : "#34d399", border: `1px solid ${summary.dealer?.includes("short") ? "rgba(244,63,94,0.25)" : "rgba(34,197,94,0.25)"}` }}>
            dealer: {summary.dealer}
          </span>
          {summary.zeroCross != null && (
            <span className="px-2 py-0.5 rounded-full font-mono"
              style={{ background: "rgba(250,204,21,0.10)", color: "#facc15", border: "1px solid rgba(250,204,21,0.25)" }}>
              γ-flip @ ${safe(summary.zeroCross, 2)}
            </span>
          )}
          {summary.rationale && (
            <span className="text-[10px] text-slate-300 italic truncate max-w-[48ch]" title={summary.rationale}>
              “{summary.rationale}”
            </span>
          )}
          {composite && (
            <CompositeScoreBar composite={composite} confidence={confidence} />
          )}
          {realisedVol && (
            <RealisedVolBar rv={realisedVol} />
          )}
          <span className="ml-auto" />
          {amihud && (
            <AmihudBar amihud={amihud} />
          )}
          {kyleLambda && (
            <KylesLambdaBar kyleLambda={kyleLambda} />
          )}
          {vpin && (
            <VpinBar vpin={vpin} />
          )}
          {regime && (
            <RegimeBar regime={regime} />
          )}
          {ofi && Array.isArray(ofi.of_per_level) && ofi.of_per_level.length > 0 && (
            <OfiVectorBar ofi={ofi} warming={ofiWarmingRef.current} />
          )}
        </div>

        <div className="flex-1 flex overflow-hidden">            {/* Chain Replay strip — compact sparkline + label timeline.
                Sits between the chip rail and the chart so the chips
                don't crowd. */}
            <ReplayPanel replay={replay} ticker={ticker} />

            {/* Chart area — kept exactly as in v1 */}
          <div className="flex-1 p-3 overflow-auto">
            {loading && !chain && (
              <div className="flex flex-col items-center justify-center h-full gap-3">
                <div className="w-8 h-8 border-2 border-sky-500/30 border-t-sky-500 rounded-full animate-spin" />
                <div className="text-slate-500 text-sm">Loading chain data from CVForge...</div>
              </div>
            )}
            {error && !chain && (
              <div className="flex flex-col items-center justify-center h-full gap-3 text-rose-400">
                <div className="text-2xl">⚠️</div>
                <div className="text-sm">{error}</div>
                <button onClick={() => fetchChain(ticker)} className="text-xs px-4 py-1.5 bg-rose-500/10 hover:bg-rose-500/20 rounded-lg border border-rose-500/20">Retry</button>
              </div>
            )}
            {chartData && (
              <Plot data={chartData.traces} layout={chartData.layout}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: "100%", height: "100%" }} useResizeHandler={true} />
            )}
          </div>

          {/* ─── Alerts panel — replaced skinny rows with Blademap cards ─── */}
          <div className="w-96 flex-shrink-0 border-l border-slate-800/30 bg-[#0b0d12] flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-800/30 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs">🔔</span>
                <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Blademap Alerts</span>
              </div>
              <span className="text-[9px] text-slate-600 bg-slate-800/50 px-1.5 py-0.5 rounded-full">{alerts.length}</span>
            </div>

            {alerts.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center p-4 text-center">
                <div className="text-2xl mb-2">🔍</div>
                <div className="text-[10px] text-slate-500">Scanning for institutional activity...</div>
                <div className="text-[9px] text-slate-600 mt-1 leading-tight">
                  Volume spikes · IV anomalies · OI concentration<br/>Sweep / Block / Floor / Golden detection
                </div>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto p-2 space-y-2">
                {alerts.slice(0, 50).map((a, i) => (
                  <BlademapAlertCard
                    key={i}
                    a={a}
                    expanded={selectedAlert === i}
                    onToggle={() => setSelectedAlert(selectedAlert === i ? null : i)}
                  />
                ))}
              </div>
            )}

            <div className="flex items-center gap-3 px-3 py-1.5 border-t border-slate-800/30 text-[8px] text-slate-500 bg-[#0a0c10]">
              <span className="flex items-center gap-1"><span className="w-2 h-1 rounded-sm bg-emerald-500/60" /> Call OI</span>
              <span className="flex items-center gap-1"><span className="w-2 h-1 rounded-sm bg-rose-500/60" /> Put OI</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 bg-amber-400" /> Delta</span>
              <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 border-t border-dashed border-sky-400" /> Spot</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Blademap Alert Card — one card per alert, fully resilient to missing fields.
// ─────────────────────────────────────────────────────────────────────────

function BlademapAlertCard({ a, expanded, onToggle }) {
  const signal = a.signal_type || a.classification || "REGULAR";
  const signalColor = CLASS_COLORS[signal] || CLASS_COLORS.regular;
  const direction = a.direction || "NEUTRAL";
  const dirColor = DIRECTION_COLORS[direction] || DIRECTION_COLORS.NEUTRAL;
  const conviction = a.conviction_score ?? a.confidence_score ?? 0;
  const convColor = convictionColor(conviction);
  const convLabel = convictionLabel(conviction);

  // Sub-scores map → safe fallbacks for legacy payloads.
  const sub = a.sub_scores || {};
  const subs = SUB_SCORE_KEYS.map((def) => {
    const v = sub[def.key];
    return {
      ...def,
      points: (v && typeof v === "object" ? v.points : v) ?? 0,
    };
  });

  const ind = a.indicators || null;
  const keyLevels = a.key_levels || null;
  const rationale = a.rationale || null;
  const actions = a.recommended_actions || [];
  const signalTypes = a.signal_types || (signal ? [signal] : []);
  const alertId = a.alert_id || "";
  const tier = a.tier ?? a.tier_label ?? null;

  return (
    <div
      data-testid="blademap-alert-card"
      data-alert-id={alertId}
      data-signal-type={signal}
      data-direction={direction}
      data-conviction={conviction}
      className={`border border-slate-800/60 rounded-lg overflow-hidden bg-[#0c0e14] ${
        expanded ? "ring-1 ring-sky-500/40" : ""
      } cursor-pointer hover:border-slate-700 transition-colors`}
      onClick={onToggle}
    >
      {/* Row 1: signal chip · tier badge · direction pill · strike · side */}
      <div className="flex items-center gap-1.5 px-2.5 py-1.5 border-b border-slate-800/40">
        <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: signalColor }} />
        <span className="text-[10px] font-bold uppercase tracking-wide" style={{ color: signalColor }}>
          {String(signal).replace(/_/g, " ")}
        </span>
        {tier != null && (
          <span
            data-testid="tier-badge"
            className="text-[8px] px-1.5 py-0.5 rounded-md font-bold tracking-widest"
            style={{
              background: tier <= 2 ? "rgba(52,211,153,0.15)" : tier === 3 ? "rgba(251,191,36,0.15)" : "rgba(148,163,184,0.15)",
              color: tier <= 2 ? "#34d399" : tier === 3 ? "#fbbf24" : "#94a3b8",
              border: `1px solid ${tier <= 2 ? "rgba(52,211,153,0.35)" : tier === 3 ? "rgba(251,191,36,0.35)" : "rgba(148,163,184,0.35)"}`,
            }}
          >
            T{tier}
          </span>
        )}
        <span
          data-testid="direction-pill"
          className="text-[8px] px-1.5 py-0.5 rounded-md font-bold uppercase"
          style={{ background: "rgba(255,255,255,0.04)", color: dirColor, border: `1px solid ${dirColor}55` }}
        >
          {direction}
        </span>
        <span className="text-[10px] font-mono text-slate-200 font-bold ml-auto">${safe(a.strike, 0)}</span>
        <span className="text-[9px] text-slate-400 font-mono">{a.side || a.option_type || "—"}</span>
        <span className="text-[9px] text-slate-500 font-mono">{a.expiration?.slice(5) || ""}</span>
      </div>

      {/* Row 2: conviction score + sub-score meters */}
      <div className="px-2.5 py-2 grid grid-cols-[auto_1fr] gap-2 items-center">
        <div className="text-center" data-testid="conviction-score">
          <div className="text-[7px] uppercase tracking-widest text-slate-500">Conviction</div>
          <div className="text-lg font-bold font-mono leading-none" style={{ color: convColor }}>{conviction}</div>
          <div className="text-[8px] uppercase tracking-widest" style={{ color: convColor }}>{convLabel}</div>
        </div>
        <div className="space-y-1">
          {subs.map((s) => {
            const pct = Math.max(0, Math.min(100, (s.points / s.max) * 100));
            return (
              <div key={s.key} data-testid={`subscore-${s.key}`} className="flex items-center gap-2">
                <div className="text-[8px] uppercase tracking-widest text-slate-500 w-12">{s.label}</div>
                <div className="flex-1 h-1.5 rounded-full bg-slate-800/70 overflow-hidden">
                  <div
                    className="h-full rounded-full"
                    style={{ width: `${pct}%`, background: s.colour, opacity: s.points > 0 ? 1 : 0.25 }}
                  />
                </div>
                <div className="text-[8px] font-mono text-slate-300 w-12 text-right">
                  {s.points}/{s.max}
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* Row 3: trade-plan pills (entry / invalidation / target) */}
      {keyLevels && (
        <div className="px-2.5 py-1.5 flex items-center gap-2 border-t border-slate-800/40" data-testid="key-levels">
          <span className="text-[8px] uppercase tracking-widest text-slate-500 font-bold">Trade Plan</span>
          <PlanPill k="entry" v={keyLevels.entry} colour="#64748b" />
          <PlanPill k="invalidation" v={keyLevels.invalidation} colour="#fb7185" />
          <PlanPill k="target" v={keyLevels.target} colour="#34d399" />
        </div>
      )}

      {/* Expanded section: rationale + actions + signal-type chips + indicator row */}
      {expanded && (
        <div className="px-2.5 py-2 border-t border-slate-800/40 space-y-2 bg-[#0a0c10]">
          {rationale && (
            <div data-testid="rationale">
              <div className="text-[8px] uppercase tracking-widest text-slate-500 mb-0.5">Rationale</div>
              <div className="text-[10px] text-slate-200 leading-snug">“{rationale}”</div>
            </div>
          )}
          {actions.length > 0 && (
            <div data-testid="recommended-actions">
              <div className="text-[8px] uppercase tracking-widest text-slate-500 mb-0.5">Recommended actions</div>
              <ul className="space-y-0.5">
                {actions.map((r, j) => (
                  <li key={j} className="text-[10px] text-emerald-300 font-mono">→ {r}</li>
                ))}
              </ul>
            </div>
          )}
          {signalTypes.length > 1 && (
            <div data-testid="signal-types" className="flex flex-wrap gap-1">
              {signalTypes.map((s, j) => (
                <span
                  key={j}
                  className="text-[7px] px-1 py-0.5 rounded font-mono uppercase tracking-wider"
                  style={{
                    background: `${CLASS_COLORS[s] || "#64748b"}22`,
                    color: CLASS_COLORS[s] || "#94a3b8",
                    border: `1px solid ${CLASS_COLORS[s] || "#64748b"}44`,
                  }}
                >
                  {String(s).replace(/_/g, " ")}
                </span>
              ))}
            </div>
          )}
          {ind && (
            <div data-testid="indicators-row" className="grid grid-cols-3 gap-x-2 gap-y-0.5 text-[8px] font-mono">
              <Stat label="OI"      v={safe((ind.call_oi || 0) + (ind.put_oi || 0), 0)} />
              <Stat label="Vol"     v={safe((ind.call_vol || 0) + (ind.put_vol || 0), 0)} />
              <Stat label="Vol/OI"  v={safe((ind.vol_oi_ratio || 0) * 100, 1)} suffix="%" />
              <Stat label="IV"      v={safe((ind.iv || 0) * 100, 1)} suffix="%" />
              <Stat label="Δ"       v={safe(ind.delta, 2)} />
              <Stat label="Premium" v={safe((ind.estimated_premium || 0) / 1000, 0)} suffix="K" />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── Multi-Level OFI vector bar (Xu/Gould/Howison 2019) ────────────────
function OfiVectorBar({ ofi, warming }) {
  const vec = ofi.of_per_level || [];
  const maxAbs = Math.max(1, ...vec.map(v => Math.abs(v)));
  const agg = ofi.of_aggregated || 0;
  const label = ofi.imbalance_label || "neutral";
  const dirColor = label === "buy_pressure" ? "#34d399" : label === "sell_pressure" ? "#fb7185" : "#94a3b8";
  if (warming) {
    return (
      <span data-testid="ofi-bar-warming" title="Needs ≥2 chain snapshots to compute OFI deltas"
        className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60">
        ⌛ OFI warming ({ofi.snaps_used || 0}/2 snaps)
      </span>
    );
  }
  return (
    <span data-testid="ofi-bar" className="flex items-center gap-1.5" title={`Multi-Level OFI (Xu/Gould/Howison 2019). Aggregate=${agg.toFixed(0)} (${label}).`}>
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">OFI</span>
      <span className="flex items-end gap-[2px] h-3">
        {vec.map((v, i) => {
          const h = Math.max(2, Math.round(Math.abs(v) / maxAbs * 12));
          return (
            <span
              key={i}
              data-testid={`ofi-level-${i}`}
              title={`Level ${i + 1}: ${v >= 0 ? "+" : ""}${v}`}
              className="block w-[3px] rounded-sm"
              style={{
                height: `${h}px`,
                background: v >= 0 ? "#34d399" : "#fb7185",
                opacity: v === 0 ? 0.25 : 1,
              }}
            />
          );
        })}
      </span>
      <span className="px-1.5 py-0.5 rounded font-mono text-[9px]" style={{ color: dirColor, border: `1px solid ${dirColor}55`, background: `${dirColor}22` }}>
        {agg >= 0 ? "+" : ""}{agg.toFixed(0)} {label.replace("_", " ")}
      </span>
    </span>
  );
}

function PlanPill({ k, v, colour }) {
  const labels = { entry: "Entry", invalidation: "Stop", target: "Target" };
  return (
    <span
      className="inline-flex items-baseline gap-1 px-1.5 py-0.5 rounded-md text-[8px] font-mono"
      style={{ background: `${colour}22`, color: colour, border: `1px solid ${colour}44` }}
    >
      <span className="text-[7px] uppercase tracking-widest opacity-70">{labels[k] || k}</span>
      <span className="text-[9px] font-bold">${safe(v, 2)}</span>
    </span>
  );
}

// ── VPIN Toxicity bar (paper #5 — Easley/López de Prado/O'Hara 2013) ─────
function VpinBar({ vpin }) {
  if (!vpin) return null;
  if (vpin.is_warming) {
    return (
      <span data-testid="vpin-bar-warming"
            title={`VPIN warming: needs ≥${vpin.buckets_used || 20} buckets (have ${vpin.history_total || 0}).`}
            className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60">
        ⌛ VPIN warming ({vpin.history_total || 0}/20)
      </span>
    );
  }
  const value = typeof vpin.vpin === "number" ? vpin.vpin : 0;
  const pct = Math.max(0, Math.min(100, value * 100));
  const color = vpin.label_color || "#94a3b8";
  const labelText = String(vpin.label || "LOW_TOXICITY").replace(/_/g, " ");
  return (
    <span data-testid="vpin-bar"
          title={`VPIN toxicity (${labelText}). vpin=${value.toFixed(3)} over last ${vpin.n_buckets} buckets. Paper #5 in Blademap bibliography.`}
          className="flex items-center gap-1.5">
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">VPIN</span>
      <span className="relative flex h-2 w-32 rounded overflow-hidden border border-slate-800/60"
            data-testid="vpin-bar-fill-track">
        <span
          data-testid="vpin-bar-fill"
          className="h-full"
          style={{ width: `${pct}%`, background: color, transition: "width 600ms ease-out" }}
        />
        {/* 0.3 / 0.5 / 0.7 tier markers */}
        <span className="absolute top-0 left-[30%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[50%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[70%] h-full w-px bg-slate-700/70" aria-hidden />
      </span>
      <span className="px-1.5 py-0.5 rounded font-mono text-[9px]"
            data-testid="vpin-current-label"
            style={{
              background: `${color}22`,
              color: color,
              border: `1px solid ${color}55`,
            }}>
        {labelText} {(value * 100).toFixed(0)}%
      </span>
    </span>
  );
}

// ── HMM Regime Bar (paper #6 — Market Regime Detection using HMMs) ─────────
function RegimeBar({ regime }) {
  if (!regime) return null;
  if (regime.is_warming) {
    return (
      <span data-testid="regime-bar-warming"
            title={`HMM warming: needs ≥5 observations to fit (have ${regime.n_obs || 0}).`}
            className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60">
        ⌛ HMM warming ({regime.n_obs || 0}/5)
      </span>
    );
  }
  const STATE_COLORS = ["#22c55e", "#94a3b8", "#ef4444"]; // BULL, RANGING, BEAR
  const posterior = Array.isArray(regime.posterior) ? regime.posterior : [];
  if (posterior.length !== 3) return null;
  const conf = regime.confidence != null ? Math.round(regime.confidence * 100) : 0;
  return (
    <span data-testid="regime-bar"
          title={`HMM regime (3-state Gaussian). Confidence ${conf}%. Paper #6 in Blademap bibliography.`}
          className="flex items-center gap-1.5">
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Regime</span>
      <span className="flex h-2 w-32 rounded overflow-hidden border border-slate-800/60"
            data-testid="regime-posterior-bar">
        {posterior.map((p, i) => (
          <span key={i}
                data-testid={`regime-bar-state-${i}`}
                title={`State ${i}: ${(p * 100).toFixed(0)}%`}
                className="h-full"
                style={{ width: `${Math.max(0, p * 100)}%`, background: STATE_COLORS[i] }} />
        ))}
      </span>
      <span className="px-1.5 py-0.5 rounded font-mono text-[9px]"
            data-testid="regime-current-state"
            style={{
              background: "rgba(148,163,184,0.12)",
              color: regime.current_state === "TRENDING_BULL" ? "#22c55e"
                   : regime.current_state === "TRENDING_BEAR" ? "#ef4444"
                   : "#94a3b8",
              border: "1px solid rgba(148,163,184,0.35)",
            }}>
        {String(regime.current_state || "RANGING").replace("_", " ")} {conf}%
      </span>
    </span>
  );
}

// ── Chain Replay strip — compact sparkline + label timeline ──────────
function ReplayPanel({ replay, ticker }) {
  const snaps = (replay && Array.isArray(replay.snapshots)) ? replay.snapshots : [];
  const latest = replay && replay.latest ? replay.latest : null;
  const size = replay && typeof replay.size === "number" ? replay.size : 0;
  const capacity = replay && typeof replay.capacity === "number" ? replay.capacity : 240;
  const summary = replay && replay.summary ? replay.summary : { count: 0, min: 0, max: 0, avg: 0, first_label: null, last_label: null };

  // Empty state
  if (!replay || snaps.length === 0) {
    return (
      <div
        data-testid="replay-panel-empty"
        className="px-4 py-1.5 border-b border-slate-800/30 bg-[#0a0c10] flex items-center gap-2 text-[10px]"
        title="Chain Replay — composite history captured each composite-fetch poll"
      >
        <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Replay</span>
        <span className="text-slate-600 italic">collecting… (0/{capacity} snaps captured)</span>
      </div>
    );
  }

  // Sparkline geometry ─
  const W = 320, H = 28, padX = 2, padY = 2;
  const innerW = W - 2 * padX, innerH = H - 2 * padY;
  const composites = snaps.map(s => Number(s.composite) || 0);
  const ymin = 0, ymax = 100;
  const xStep = innerW / Math.max(1, composites.length - 1);
  const points = composites.map((v, i) => {
    const x = padX + i * xStep;
    const yNorm = (v - ymin) / (ymax - ymin);
    const y = padY + (1 - yNorm) * innerH;
    return [x, y];
  });
  const pathD = points.map((p, i) => (i === 0 ? `M${p[0].toFixed(1)},${p[1].toFixed(1)}` : `L${p[0].toFixed(1)},${p[1].toFixed(1)}`)).join(" ");
  const lastX = points[points.length - 1][0];
  const lastY = points[points.length - 1][1];
  const aheadX = Math.min(W - padX, lastX + xStep * 0.5);

  // Color the line with the *latest* label color so a glance tells
  // you the current conviction.
  const lineColor = (latest && latest.label_color) || "#64748b";
  const labelText = String((latest && latest.label) || "LOW").replace("_", " ");
  const lastVal = (latest && latest.composite) != null ? Number(latest.composite).toFixed(0) : "—";

  // Compute "transition strip" — most-recent first 8 labels, dedup consecutive.
  const strip = [];
  for (let i = snaps.length - 1; i >= 0 && strip.length < 8; i--) {
    const lbl = String(snaps[i].label || "LOW");
    if (strip.length === 0 || strip[strip.length - 1].label !== lbl) {
      strip.push({ label: lbl, color: snaps[i].label_color || "#64748b" });
    }
  }

  return (
    <div
      data-testid="replay-panel"
      className="px-4 py-1.5 border-b border-slate-800/30 bg-[#0a0c10] flex items-center gap-3 text-[10px]"
      title={`Chain Replay — last ${snaps.length} composite reads for ${ticker}. Captured each 30s poll. Buffer ${size}/${capacity}.`}
    >
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold shrink-0">Replay</span>

      {/* Sparkline SVG — 80/60/40 marker rules as faint horizontals */}
      <svg
        data-testid="replay-sparkline"
        width={W} height={H}
        viewBox={`0 0 ${W} ${H}`}
        className="shrink-0"
        style={{ background: "rgba(15,23,42,0.4)", borderRadius: 4, border: "1px solid rgba(30,41,59,0.6)" }}
      >
        {/* 80 / 60 / 40 tier guidelines */}
        {[80, 60, 40].map((band) => {
          const y = padY + (1 - (band - ymin) / (ymax - ymin)) * innerH;
          return (
            <line
              key={band}
              x1={padX} x2={W - padX} y1={y} y2={y}
              stroke="rgba(148,163,184,0.15)"
              strokeDasharray="2 3"
            />
          );
        })}
        <path
          data-testid="replay-sparkline-path"
          d={pathD}
          stroke={lineColor}
          strokeWidth="1.4"
          fill="none"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
        <circle cx={lastX} cy={lastY} r="2.2" fill={lineColor} />
        <line
          x1={lastX} y1={lastY}
          x2={aheadX} y2={lastY}
          stroke={lineColor}
          strokeWidth="1.4"
          opacity="0.4"
        />
      </svg>

      {/* Latest score + label pill */}
      <span className="flex items-center gap-1.5 shrink-0">
        <span className="font-mono text-[11px] font-bold" style={{ color: lineColor }} data-testid="replay-latest-score">
          {lastVal}
        </span>
        <span
          data-testid="replay-latest-label"
          className="px-1.5 py-0.5 rounded font-mono text-[9px]"
          style={{
            background: `${lineColor}22`,
            color: lineColor,
            border: `1px solid ${lineColor}55`,
          }}
        >
          {labelText}
        </span>
      </span>

      {/* Transition strip — last 8 unique consecutive labels, oldest → newest */}
      <span className="flex items-center gap-1 shrink-0" data-testid="replay-transition-strip">
        {strip.slice().reverse().map((t, i) => (
          <span
            key={`${t.label}-${i}`}
            data-testid={`replay-step-${t.label}`}
            className="text-[8px] px-1 py-0.5 rounded font-mono uppercase tracking-wider"
            style={{
              background: `${t.color}22`,
              color: t.color,
              border: `1px solid ${t.color}44`,
              opacity: i === strip.length - 1 ? 1 : 0.7,
            }}
            title={`${t.label}`}
          >
            {t.label.replace("_", " ")}
          </span>
        ))}
      </span>

      {/* Buffer fill bar + summary stats */}
      <span className="flex items-center gap-1.5 shrink-0 ml-auto" data-testid="replay-buffer-stats">
        <span className="text-[9px] text-slate-500 font-mono">
          {size}/{capacity} snaps
        </span>
        <span className="relative flex h-1.5 w-16 rounded overflow-hidden border border-slate-800/60" data-testid="replay-buffer-track">
          <span
            data-testid="replay-buffer-fill"
            className="h-full"
            style={{
              width: `${Math.min(100, (size / Math.max(1, capacity)) * 100)}%`,
              background: "linear-gradient(90deg, rgba(52,211,153,0.7), rgba(56,189,248,0.7))",
              transition: "width 600ms ease-out",
            }}
          />
        </span>
        <span className="text-[9px] text-slate-500 font-mono" data-testid="replay-summary-stats">
          min {Number(summary.min || 0).toFixed(0)} · max {Number(summary.max || 0).toFixed(0)} · avg {Number(summary.avg || 0).toFixed(0)}
        </span>
      </span>
    </div>
  );
}

// ── Realised Volatility bar (Andersen-Bollerslev 1998 / BNS 2002) ─────
function RealisedVolBar({ rv }) {
  if (!rv) return null;
  if (rv.is_warming) {
    return (
      <span
        data-testid="rv-bar-warming"
        title={`Realised Vol warming: needs ≥${rv.window_minutes ? rv.window_minutes * 2 : 60} spot observations (have ${rv.n_obs || 0}).`}
        className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60"
      >
        ⌛ RV warming ({rv.n_obs || 0}/60)
      </span>
    );
  }
  const pct = (rv.rv_annualised * 100).toFixed(1);
  const color = rv.label_color || "#94a3b8";
  const labelText = String(rv.label || "MILD");
  const bvPct = (rv.bv_annualised * 100).toFixed(1);
  // A horizontal mini-track visualises rv_annualised on a 0..50% scale
  // (50% == STRESSED entry threshold × 1.25). The chip rail stays
  // compact: a single fill bar shows position within the band.
  const trackPct = Math.max(0, Math.min(100, (rv.rv_annualised / 0.5) * 100));
  return (
    <span
      data-testid="rv-bar"
      title={`Realised Volatility (paper #6 — Andersen-Bollerslev 1998 / Barndorff-Nielsen-Shephard 2002): RV=${pct}% annualised over ${rv.window_minutes || 30}-minute window (${rv.n_obs}/${rv.n_obs} obs). Bipower (jump-robust) BV=${bvPct}%. ${labelText} regime.`}
      className="flex items-center gap-1.5"
    >
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">RV</span>
      <span className="relative flex h-2 w-20 rounded overflow-hidden border border-slate-800/60">
        <span
          data-testid="rv-bar-fill"
          className="h-full"
          style={{ width: `${trackPct}%`, background: color, transition: "width 600ms ease-out" }}
        />
        {/* 10% / 20% / 40% tier markers (the QUIET/MILD/ACTIVE/STRESSED cutoff line) */}
        <span className="absolute top-0 left-[20%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[40%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[80%] h-full w-px bg-slate-700/70" aria-hidden />
      </span>
      <span
        data-testid="rv-current-label"
        className="px-1.5 py-0.5 rounded font-mono text-[9px]"
        style={{
          background: `${color}22`,
          color,
          border: `1px solid ${color}55`,
        }}
      >
        {labelText} {pct}%
      </span>
    </span>
  );
}

function Stat({ label, v, suffix }) {
  return (
    <span>
      <span className="text-slate-500 mr-1">{label}</span>
      <span className="text-slate-200">{v}{suffix || ""}</span>
    </span>
  );
}

// ── Kyle's λ bar (Kyle 1985 — price impact / market depth) ────────────
function KylesLambdaBar({ kyleLambda }) {
  if (!kyleLambda) return null;
  if (kyleLambda.is_warming) {
    return (
      <span
        data-testid="kyle-bar-warming"
        title={`Kyle's λ warming: needs ≥${kyleLambda.window || 20} observations (have ${kyleLambda.n_obs || 0}).`}
        className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60"
      >
        ⌛ Kyle's λ warming ({kyleLambda.n_obs || 0}/20)
      </span>
    );
  }
  const value = typeof kyleLambda.lambda_value === "number" ? kyleLambda.lambda_value : 0;
  const r2 = typeof kyleLambda.r_squared === "number" ? kyleLambda.r_squared : 0;
  const color = kyleLambda.label_color || "#94a3b8";
  const labelText = String(kyleLambda.label || "NORMAL");
  // Visualise λ on a 0..0.01 horizontal track (0.005 ILLIQUID threshold at 50%).
  const pct = Math.max(0, Math.min(100, (value / 0.01) * 100));
  return (
    <span
      data-testid="kyle-bar"
      title={`Kyle's λ (market depth): ${value.toFixed(4)} per unit directional flow, r²=${r2.toFixed(2)}. Paper Kyle (1985) — Blademap stack.`}
      className="flex items-center gap-1.5"
    >
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Kyle's λ</span>
      <span className="relative flex h-2 w-24 rounded overflow-hidden border border-slate-800/60">
        <span
          data-testid="kyle-bar-fill"
          className="h-full"
          style={{ width: `${pct}%`, background: color, transition: "width 600ms ease-out" }}
        />
        {/* 0.001 / 0.005 LIQUID→NORMAL→ILLIQUID tier markers (at 10% / 50%) */}
        <span className="absolute top-0 left-[10%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[50%] h-full w-px bg-slate-700/70" aria-hidden />
      </span>
      <span
        className="px-1.5 py-0.5 rounded font-mono text-[9px]"
        data-testid="kyle-current-label"
        style={{
          background: `${color}22`,
          color: color,
          border: `1px solid ${color}55`,
        }}
      >
        {labelText} {value >= 0 ? "+" : ""}{(value * 100).toFixed(2)}%
      </span>
    </span>
  );
}

// ── Amihud illiquidity-ratio bar (Amihud 2002 — ||r|| / DV depth) ──────
function AmihudBar({ amihud }) {
  if (!amihud) return null;
  if (amihud.is_warming) {
    return (
      <span
        data-testid="amihud-bar-warming"
        title={`Amihud warming: needs ≥${amihud.window || 20} observations (have ${amihud.n_obs || 0}).`}
        className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60"
      >
        ⌛ Amihud warming ({amihud.n_obs || 0}/20)
      </span>
    );
  }
  // Visualise amihud on a 0..1e-4 normalised track; 1e-7 LIQUID→NORMAL at 0.1%, 1e-5 NORMAL→ILLIQUID at 10%.
  // A safer practical range is 0..1e-4 (×10 of the ILLIQUID threshold).
  const value = typeof amihud.amihud === "number" ? amihud.amihud : 0;
  const pct = Math.max(0, Math.min(100, (value / 1e-4) * 100));
  const color = amihud.label_color || "#94a3b8";
  const labelText = String(amihud.label || "NORMAL");
  return (
    <span
      data-testid="amihud-bar"
      title={`Amihud illiquidity (${labelText}). value=${value.toExponential(2)} over last ${amihud.n_obs} obs. Paper Amihud (2002) — Blademap stack.`}
      className="flex items-center gap-1.5"
    >
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Amihud</span>
      <span className="relative flex h-2 w-24 rounded overflow-hidden border border-slate-800/60">
        <span
          data-testid="amihud-bar-fill"
          className="h-full"
          style={{ width: `${pct}%`, background: color, transition: "width 600ms ease-out" }}
        />
        {/* 1e-7 / 1e-5 LIQUID→NORMAL→ILLIQUID tier markers (at 0.1% / 10% on a 0..1e-4 track) */}
        <span className="absolute top-0 left-[0.1%] h-full w-px bg-slate-700/70" aria-hidden />
        <span className="absolute top-0 left-[10%] h-full w-px bg-slate-700/70" aria-hidden />
      </span>
      <span
        className="px-1.5 py-0.5 rounded font-mono text-[9px]"
        data-testid="amihud-current-label"
        style={{
          background: `${color}22`,
          color: color,
          border: `1px solid ${color}55`,
        }}
      >
        {labelText} {value.toExponential(1)}
      </span>
    </span>
  );
}

// ── Composite Flow Score Bar (LEAD chip showing 0..100 tradable conviction) ──
function CompositeScoreBar({ composite, confidence }) {
  if (!composite) return null;
  if (composite.is_warming) {
    return (
      <span
        data-testid="composite-bar-warming"
        title={`Composite Score warming: needs all 5 sub-services to be ready (illiquidity, toxicity, regime, flow). Current min n_obs=${composite.n_obs_min || 0}.`}
        className="text-[9px] uppercase tracking-widest text-slate-500 px-2 py-0.5 rounded-full border border-slate-800/60"
      >
        ⌛ Composite warming
      </span>
    );
  }
  const score = typeof composite.composite === "number" ? composite.composite : 0;
  const color = composite.label_color || "#94a3b8";
  const labelText = String(composite.label || "LOW");
  const subs = composite.sub_scores || {};
  // NEW: Confidence-Band inset chip (Bootstrap CI around the live score).
  // Only render when we have a non-warming confidence payload.
  const conf = confidence && !confidence.is_warming ? confidence : null;
  // Bootstrap CI is only renderable when both numeric endpoints are present.
  // The backend can return a partially-initialised payload (lower/upper undefined)
  // alongside a confidence_label, so guard before calling .toFixed(...).
  const hasBands = conf && conf.lower != null && conf.upper != null;
  const wColor = conf ? (
    conf.confidence_label === "WIDE"     ? "#ef4444" :
    conf.confidence_label === "MODERATE" ? "#fbbf24" :
    "#22c55e"
  ) : null;
  const wText = hasBands ? `[${conf.lower.toFixed(0)}‑${conf.upper.toFixed(0)}]` : null;
  return (
    <span
      data-testid="composite-bar"
      title={
        hasBands
          ? `Composite Flow Score (headline): ${score.toFixed(0)} / 100 — ${labelText}. 95% Bootstrap CI [${conf.lower}–${conf.upper}] (${conf.confidence_label}, n=${conf.n_samples}). Synthesises Amihud + Kyle's λ + VPIN + HMM + OFI. Blademap stack.`
          : `Composite Flow Score (headline): ${score.toFixed(0)} / 100 — ${labelText}. Synthesises Amihud + Kyle's λ + VPIN + HMM + OFI. Blademap stack.`
      }
      className="flex items-center gap-2 px-2 py-0.5 rounded-md border border-slate-700/60 bg-[#0a0c10]"
      style={{ borderColor: `${color}55` }}
    >
      <span className="text-[9px] uppercase tracking-widest text-slate-500 font-bold">Score</span>
      <span
        className="text-base font-mono font-bold leading-none"
        data-testid="composite-score-value"
        style={{ color }}
      >
        {score.toFixed(0)}
      </span>
      {conf && (
        <span
          data-testid="composite-confidence-band"
          aria-label={`95 percent bootstrap confidence interval ${conf && conf.confidence_label ? conf.confidence_label.toLowerCase() : ''}`}
          className="text-[10px] font-mono tracking-widest leading-none drop-shadow-sm"
          style={{ color: wColor, borderLeft: `1px solid ${wColor}55`, paddingLeft: 6 }}
        >
          {wText}
        </span>
      )}
      <span
        className="px-1.5 py-0.5 rounded font-mono text-[9px]"
        data-testid="composite-current-label"
        style={{
          background: `${color}22`,
          color,
          border: `1px solid ${color}55`,
        }}
      >
        {labelText}
      </span>
      {/* 4 sub-score mini-pills: illiquidity / toxicity / dislocation / direction */}
      <span className="flex items-center gap-1 ml-1" data-testid="composite-sub-scores">
        {[
          { k: "illiq", label: "ILLIQ", v: subs.illiquidity || 0, colour: "#22c55e" },
          { k: "tox",   label: "TOX",   v: subs.toxicity    || 0, colour: "#ef4444" },
          { k: "dis",   label: "DIS",   v: subs.dislocation || 0, colour: "#a855f7" },
          { k: "dir",   label: "DIR",   v: subs.direction   || 0, colour: "#38bdf8" },
        ].map((s) => {
          const pct = Math.max(0, Math.min(100, (s.v || 0) * 100));
          return (
            <span
              key={s.k}
              data-testid={`composite-sub-${s.k}`}
              title={`${s.label} sub-score = ${(s.v || 0).toFixed(2)}`}
              className="flex items-center gap-1"
            >
              <span className="text-[8px] uppercase tracking-widest text-slate-500 font-bold">{s.label}</span>
              <span className="relative flex h-1.5 w-8 rounded overflow-hidden border border-slate-800/60">
                <span
                  className="h-full"
                  style={{ width: `${pct}%`, background: s.colour, opacity: 0.85, transition: "width 600ms ease-out" }}
                />
              </span>
            </span>
          );
        })}
      </span>
    </span>
  );
}
