import React, { useState, useEffect, useCallback, useRef, useMemo } from "react";
import Plot from "react-plotly.js";

const API = "http://localhost:8000/api/flowseeker";
const DASH_API = "http://localhost:8000/api";
const TICKERS = ["SPY","QQQ","IWM","DIA","TLT","AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL"];

const CLASS_COLORS = {
  high_volume: "#fbbf24",
  high_iv: "#f43f5e",
  oi_spike: "#a855f7",
  delta_extreme: "#38bdf8",
  premium_concentration: "#22c55e",
  sweep: "#f43f5e",
  block: "#a855f7",
  unusual: "#fbbf24",
  regular: "#64748b",
};

function convictionColor(score) {
  if (score >= 80) return "#34d399";
  if (score >= 60) return "#fbbf24";
  return "#64748b";
}

function convictionLabel(score) {
  if (score >= 80) return "HIGH";
  if (score >= 60) return "MEDIUM";
  return "LOW";
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

  useEffect(() => { if (active) { fetchChain(ticker); fetchGex(ticker); } }, [ticker, active, fetchChain, fetchGex]);
  useEffect(() => { if (!active) return; const id = setInterval(() => { fetchChain(ticker); fetchAlerts(ticker); }, 30000); return () => clearInterval(id); }, [ticker, active, fetchChain, fetchAlerts]);
  useEffect(() => { if (!active) return; fetchAlerts(ticker); const id = setInterval(() => fetchAlerts(ticker), 10000); return () => clearInterval(id); }, [ticker, active, fetchAlerts]);

  // Build chart
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

      const strikes = [], callOI = [], putOI = [], deltaLine = [], callVol = [], putVol = [];
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
        callVol.push(volIdx > 0 ? (Number(cv[volIdx - 1]) || 0) : 0);
        putVol.push(volIdx > 0 ? (Number(pv[volIdx - 1]) || 0) : 0);
        if (deltaIdx > 0 && cv[deltaIdx - 1] != null) {
          deltaLine.push(Number(cv[deltaIdx - 1]) || 0.5);
        } else {
          const dist = (strike - spot) / Math.max(spot * 0.15, 1);
          deltaLine.push(1 / (1 + Math.exp(-dist * 2)));
        }
      }
      if (!strikes.length) { setChartData(null); return; }
      const maxOI = Math.max(...callOI, ...putOI, 1);

      // Find high-conviction alert strikes for highlighting
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

  // Summary stats
  const stats = useMemo(() => {
    const highConf = alerts.filter(a => a.confidence_score >= 70);
    const sweeps = alerts.filter(a => a.classification === "sweep");
    const totalPremium = alerts.reduce((s, a) => s + (a.premium || 0), 0);
    return { highConf: highConf.length, sweeps: sweeps.length, totalAlerts: alerts.length, totalPremium };
  }, [alerts]);

  return (
    <div className="flex h-full overflow-hidden">
      <audio ref={audioRef} src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQo6l9/Ss2QdBz2Y3dKyaB8F" preload="auto" />

      {/* Sidebar */}
      <div className="w-56 flex-shrink-0 border-r border-slate-800/50 bg-[#0b0d12] p-3 space-y-3 overflow-y-auto">
        {/* Ticker selector */}
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

        {/* Expiry selector */}
        {expiries.length > 0 && (
          <div>
            <div className="text-[9px] uppercase tracking-widest text-slate-500 font-bold mb-1">Expiry</div>
            <select value={expiryIdx} onChange={e => setExpiryIdx(Number(e.target.value))}
              className="w-full bg-slate-800/50 border border-slate-700/40 rounded-lg px-2 py-1.5 text-xs text-slate-200">
              {expiries.map((exp, i) => <option key={i} value={i}>{exp}</option>)}
            </select>
          </div>
        )}

        {/* Summary stats */}
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

        {/* Status */}
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

        {/* Sound toggle */}
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
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Chart area */}
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

          {/* Alerts panel */}
          <div className="w-80 flex-shrink-0 border-l border-slate-800/30 bg-[#0b0d12] flex flex-col overflow-hidden">
            <div className="px-3 py-2 border-b border-slate-800/30 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-xs">🔔</span>
                <span className="text-[10px] uppercase tracking-widest text-slate-400 font-bold">Live Alerts</span>
              </div>
              <span className="text-[9px] text-slate-600 bg-slate-800/50 px-1.5 py-0.5 rounded-full">{alerts.length}</span>
            </div>

            {alerts.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center p-4 text-center">
                <div className="text-2xl mb-2">🔍</div>
                <div className="text-[10px] text-slate-500">Scanning for institutional activity...</div>
                <div className="text-[9px] text-slate-600 mt-1">Volume spikes · IV anomalies · OI concentration · Sweep detection</div>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto">
                {alerts.slice(0, 50).map((a, i) => (
                  <div key={i} className={`px-3 py-2.5 border-b border-slate-800/20 hover:bg-slate-800/20 transition-colors cursor-pointer ${selectedAlert === i ? "bg-slate-800/30" : ""}`}
                    onClick={() => setSelectedAlert(selectedAlert === i ? null : i)}>
                    <div className="flex items-center gap-1.5">
                      <span className="w-2 h-2 rounded-full flex-shrink-0" style={{ background: CLASS_COLORS[a.classification] || "#64748b" }} />
                      <span className="text-[10px] font-bold text-slate-200 uppercase">{(a.classification || "regular").replace(/_/g, " ")}</span>
                      <span className="text-[9px] text-slate-400 font-mono">{a.option_type}</span>
                      <span className="text-[10px] font-mono text-slate-300 font-bold">${a.strike?.toFixed(0)}</span>
                      <span className="text-[9px] text-slate-500">{a.expiration?.slice(5)}</span>
                      {a.confidence_score >= 70 && (
                        <span className="text-[8px] px-1 py-0.5 rounded-full bg-emerald-500/20 text-emerald-400 font-bold ml-auto">
                          {convictionLabel(a.confidence_score)}
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-3 mt-1 text-[9px]">
                      <span className="text-slate-400">OI: <span className="text-slate-300 font-mono">{a.oi?.toFixed(0)}</span></span>
                      <span className="text-slate-400">IV: <span className="text-slate-300 font-mono">{(a.iv * 100)?.toFixed(1)}%</span></span>
                      <span className="text-slate-400">Δ: <span className="text-slate-300 font-mono">{a.delta?.toFixed(2)}</span></span>
                      {a.premium > 0 && <span className="text-amber-400 font-mono">${(a.premium / 1000).toFixed(0)}K</span>}
                    </div>
                    {selectedAlert === i && a.confidence_factors?.length > 0 && (
                      <div className="mt-2 pt-2 border-t border-slate-800/30">
                        <div className="text-[8px] text-slate-500 uppercase tracking-wider mb-1">Institutional Indicators</div>
                        {a.confidence_factors.map((f, j) => (
                          <div key={j} className="text-[9px] text-slate-400 py-0.5">• {f}</div>
                        ))}
                        {a.recommended_actions?.length > 0 && (
                          <div className="mt-1.5 pt-1.5 border-t border-slate-800/20">
                            <div className="text-[8px] text-slate-500 uppercase tracking-wider mb-1">Recommended</div>
                            {a.recommended_actions.map((r, j) => (
                              <div key={j} className="text-[9px] text-emerald-400 py-0.5">→ {r}</div>
                            ))}
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Legend */}
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
