import React, { useState, useEffect, useCallback, useRef } from "react";
import Plot from "react-plotly.js";

const API = "http://localhost:8000/api/flowseeker";
const TICKERS = ["SPY","QQQ","IWM","DIA","TLT","AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL"];

const CLASS_COLORS = { sweep: "#fbbf24", block: "#f43f5e", unusual: "#a855f7", regular: "#64748b" };

export default function FlowseekerProTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expiryIdx, setExpiryIdx] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [chartData, setChartData] = useState(null);
  const [alerts, setAlerts] = useState([]);
  const [soundEnabled, setSoundEnabled] = useState(true);
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

  useEffect(() => { if (active) fetchChain(ticker); }, [ticker, active, fetchChain]);
  useEffect(() => { if (!active) return; const id = setInterval(() => fetchChain(ticker), 30000); return () => clearInterval(id); }, [ticker, active, fetchChain]);
  useEffect(() => { if (!active) return; fetchAlerts(ticker); const id = setInterval(() => fetchAlerts(ticker), 10000); return () => clearInterval(id); }, [ticker, active, fetchAlerts]);

  // Build chart data
  useEffect(() => {
    if (!chain) { setChartData(null); return; }
    try {
      const exp = chain.chain[expiryIdx] || chain.chain[0];
      if (!exp?.strikes?.length) { setChartData(null); return; }
      const params = chain.params || [];
      const oiIdx = params.indexOf("openInterest");
      const deltaIdx = params.indexOf("delta");
      const spotIdx = params.indexOf("underlying_price");

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

      const traces = [
        { y: strikes, x: callOI.map(v => -(v / maxOI) * 100), type: "bar", orientation: "h",
          name: "Call OI", marker: { color: "rgba(52,211,153,0.65)" },
          customdata: callOI, hovertemplate: "Call OI: %{customdata}<extra></extra>" },
        { y: strikes, x: putOI.map(v => (v / maxOI) * 100), type: "bar", orientation: "h",
          name: "Put OI", marker: { color: "rgba(244,63,94,0.65)" },
          customdata: putOI, hovertemplate: "Put OI: %{customdata}<extra></extra>" },
        { y: strikes, x: deltaLine.map(v => (v - 0.5) * 80), type: "scatter", mode: "lines",
          name: "Delta", line: { color: "#fbbf24", width: 2.5 }, xaxis: "x2" },
      ];

      const layout = {
        title: { text: `OI by Strike — ${ticker} (${exp.expiration}) — ${strikes.length} strikes`, font: { color: "#94a3b8", size: 12 } },
        paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", barmode: "overlay",
        margin: { l: 50, r: 60, t: 35, b: 35 },
        xaxis: { title: "OI (norm)", color: "#64748b", zeroline: true, zerolinecolor: "#334155", gridcolor: "#1e293b", tickfont: { size: 8 }, range: [-100, 100] },
        xaxis2: { overlaying: "x", side: "top", title: "Delta", color: "#fbbf24", tickfont: { size: 7, color: "#fbbf24" }, range: [-40, 40], tickvals: [-40, -20, 0, 20, 40], ticktext: ["1.0", "0.75", "0.5", "0.25", "0.0"] },
        yaxis: { title: "Strike", color: "#64748b", gridcolor: "#1e293b", tickfont: { size: 8 } },
        legend: { font: { color: "#94a3b8", size: 9 }, orientation: "h", y: 1.08 },
        hovermode: "y unified", showlegend: true,
        height: Math.max(350, strikes.length * 16),
        shapes: spot > 0 ? [{ type: "line", x0: -100, x1: 100, y0: spot, y1: spot, line: { color: "#38bdf8", width: 1.5, dash: "dot" } }] : [],
        annotations: spot > 0 ? [{ x: 95, y: spot, text: `$${spot.toFixed(0)}`, showarrow: false, font: { color: "#38bdf8", size: 9 }, xref: "x", yref: "y" }] : [],
      };
      setChartData({ traces, layout });
    } catch (e) {
      console.error("FlowseekerPro chart error:", e);
      setChartData(null);
    }
  }, [chain, expiryIdx, ticker]);

  const expiries = chain?.chain?.map(c => c.expiration) || [];

  return (
    <div className="flex h-full overflow-hidden">
      <audio ref={audioRef} src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQoGAACBhYqFbF1fdJivrJBhNjVgodDbq2EcBj+a2teleQo6l9/Ss2QdBz2Y3dKyaB8F" preload="auto" />

      {/* Sidebar */}
      <div className="w-52 flex-shrink-0 border-r border-slate-800 bg-[#0d0f14] p-3 space-y-2 overflow-y-auto">
        <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold">Ticker</div>
        <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === "Enter") fetchChain(ticker); }}
          className="w-full bg-slate-800/80 border border-slate-700/50 rounded px-2 py-1 text-sm text-slate-200 outline-none focus:border-sky-500/50" />
        <div className="flex flex-wrap gap-1">
          {TICKERS.map(t => (
            <button key={t} onClick={() => setTicker(t)}
              className={`text-[10px] px-1.5 py-0.5 rounded transition-colors ${t === ticker ? "bg-sky-600/80 text-white" : "bg-slate-800/50 text-slate-400 hover:bg-slate-700/50"}`}>{t}</button>
          ))}
        </div>
        {expiries.length > 0 && (
          <>
            <div className="text-[10px] uppercase tracking-widest text-slate-500 font-bold mt-2">Expiry</div>
            <select value={expiryIdx} onChange={e => setExpiryIdx(Number(e.target.value))}
              className="w-full bg-slate-800/80 border border-slate-700/50 rounded px-2 py-1 text-xs text-slate-200">
              {expiries.map((exp, i) => <option key={i} value={i}>{exp}</option>)}
            </select>
          </>
        )}
        <div className="text-[9px] space-y-1 mt-2">
          {loading && <div className="text-amber-400/80">● Loading chain...</div>}
          {error && <div className="text-rose-400/80">● {error}</div>}
          {chain && !loading && (
            <div className="space-y-0.5">
              <div className="text-emerald-400/80">● {chain.chain.length} expirations</div>
              <div className="text-slate-500">{chain.chain?.[expiryIdx]?.strikes?.length || 0} strikes</div>
              {lastUpdate && <div className="text-slate-600">Updated {lastUpdate}</div>}
            </div>
          )}
        </div>

        {/* Alerts toggle */}
        <div className="border-t border-slate-800 pt-2 mt-2">
          <div className="flex items-center justify-between">
            <span className="text-[10px] text-slate-500">🔔 Sweep Alerts</span>
            <button onClick={() => setSoundEnabled(!soundEnabled)}
              className={`text-[10px] px-2 py-0.5 rounded ${soundEnabled ? "bg-emerald-600/20 text-emerald-400" : "bg-slate-800 text-slate-500"}`}>
              {soundEnabled ? "ON" : "OFF"}
            </button>
          </div>
          <div className="text-[9px] text-slate-600 mt-1">{alerts.length} alerts · 10s refresh</div>
        </div>

        <button onClick={() => { fetchChain(ticker); fetchAlerts(ticker); }}
          className="w-full text-[10px] py-1 bg-slate-800/50 hover:bg-slate-700/50 rounded text-slate-400">↻ Refresh</button>
      </div>

      {/* Main content: Chart + Alerts */}
      <div className="flex-1 flex flex-col overflow-hidden bg-[#0b0d12]">
        <div className="flex items-center gap-3 px-3 py-1.5 border-b border-slate-800/50">
          <span className="text-xs font-medium text-slate-300">{ticker}</span>
          {chain && <span className="text-[10px] text-emerald-400">● LIVE</span>}
          {chain && <span className="text-[10px] text-slate-500">{chain.chain?.length || 0} exp</span>}
          {alerts.length > 0 && <span className="text-[10px] text-amber-400">🔔 {alerts.length} alerts</span>}
        </div>

        <div className="flex-1 flex overflow-hidden">
          {/* Chart */}
          <div className="flex-1 p-2 overflow-auto flex items-center justify-center">
            {loading && !chain && <div className="text-slate-500 text-sm animate-pulse">Loading chain data...</div>}
            {error && !chain && (
              <div className="flex flex-col items-center gap-2 text-rose-400 text-sm">
                <div>{error}</div>
                <button onClick={() => fetchChain(ticker)} className="text-xs px-3 py-1 bg-rose-500/10 hover:bg-rose-500/20 rounded">Retry</button>
              </div>
            )}
            {chartData && (
              <Plot data={chartData.traces} layout={chartData.layout}
                config={{ responsive: true, displayModeBar: false }}
                style={{ width: "100%", height: "100%" }} useResizeHandler={true} />
            )}
          </div>

          {/* Alerts panel */}
          <div className="w-64 flex-shrink-0 border-l border-slate-800 bg-[#0d0f14] overflow-y-auto">
            <div className="px-2 py-1.5 border-b border-slate-800 text-[10px] uppercase tracking-widest text-slate-500 font-bold flex items-center justify-between">
              <span>Live Alerts</span>
              <span className="text-[9px] text-slate-600 normal-case">{alerts.length}</span>
            </div>
            {alerts.length === 0 ? (
              <div className="p-3 text-[10px] text-slate-600 text-center">No large trades detected</div>
            ) : (
              <div className="divide-y divide-slate-800/50">
                {alerts.slice(0, 30).map((a, i) => (
                  <div key={i} className="px-2 py-1.5 hover:bg-slate-800/30 transition-colors">
                    <div className="flex items-center gap-1.5">
                      <span className="w-1.5 h-1.5 rounded-full" style={{ background: CLASS_COLORS[a.classification] || "#64748b" }} />
                      <span className="text-[10px] font-medium text-slate-300">{a.type}</span>
                      <span className="text-[10px] text-slate-500">{a.strike.toFixed(0)}</span>
                      <span className="text-[10px] text-slate-600">{a.expiration?.slice(5)}</span>
                    </div>
                    <div className="flex items-center gap-2 mt-0.5 text-[9px] text-slate-500">
                      <span>{a.size.toFixed(0)}x @ ${a.price.toFixed(2)}</span>
                      <span className="text-slate-600">${(a.premium / 1000).toFixed(0)}k</span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 px-3 py-1.5 border-t border-slate-800/50 text-[9px] text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2.5 h-1.5 rounded-sm bg-emerald-500/60"></span> Call OI</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-1.5 rounded-sm bg-rose-500/60"></span> Put OI</span>
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-amber-400/80"></span> Delta</span>
          <span className="flex items-center gap-1"><span className="w-2.5 h-0.5 border-t border-dashed border-sky-400/80"></span> Spot</span>
          <span className="ml-auto text-slate-600">{expiries[expiryIdx] || "—"}</span>
        </div>
      </div>
    </div>
  );
}
