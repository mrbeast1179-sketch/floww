import React, { useState, useEffect, useRef, useCallback } from "react";

const API = "http://localhost:8000/api/flowseeker";
const TICKERS = ["SPY","QQQ","IWM","DIA","TLT","AAPL","MSFT","NVDA","TSLA","AMZN","META","GOOGL"];

export default function FlowseekerProTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [chain, setChain] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [expiryIdx, setExpiryIdx] = useState(0);
  const [lastUpdate, setLastUpdate] = useState(null);
  const chartRef = useRef(null);

  const fetchChain = useCallback(async (sym) => {
    setLoading(true);
    setError(null);
    try {
      const r = await fetch(`${API}/chain/${sym}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      if (!d.chain || d.chain.length === 0) throw new Error("No chain data");
      setChain(d);
      setExpiryIdx(0);
      setLastUpdate(new Date().toLocaleTimeString());
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { if (active) fetchChain(ticker); }, [ticker, active, fetchChain]);
  useEffect(() => { if (!active) return; const id = setInterval(() => fetchChain(ticker), 20000); return () => clearInterval(id); }, [ticker, active, fetchChain]);

  // Render chart
  useEffect(() => {
    if (!chain || !chartRef.current || !window.Plotly) return;
    const exp = chain.chain[expiryIdx];
    if (!exp || !exp.strikes) return;

    const params = chain.params || [];
    const oiIdx = params.indexOf("openInterest");
    const volIdx = params.indexOf("volume");
    const ivIdx = params.indexOf("impliedVolatility");
    const deltaIdx = params.indexOf("delta");

    const strikes = [];
    const callOI = [];
    const putOI = [];
    const deltaLine = [];
    const spotPrice = exp.strikes[0]?.[1]?.[params.indexOf("underlying_price")] || 0;

    for (const s of exp.strikes) {
      const strike = s[0];
      const cv = s[1] || [];
      const pv = s[2] || [];
      strikes.push(strike);
      callOI.push(oiIdx >= 0 ? (cv[oiIdx - 1] || 0) : 0);
      putOI.push(oiIdx >= 0 ? (pv[oiIdx - 1] || 0) : 0);
      // Use actual delta if available, else synthetic
      if (deltaIdx >= 0 && cv[deltaIdx - 1] != null) {
        deltaLine.push(cv[deltaIdx - 1]);
      } else {
        const dist = (strike - spotPrice) / (spotPrice * 0.15);
        deltaLine.push(1 / (1 + Math.exp(-dist * 2)));
      }
    }

    if (strikes.length === 0) return;
    const maxOI = Math.max(...callOI, ...putOI, 1);

    const traces = [
      { y: strikes, x: callOI.map(v => -(v / maxOI) * 100), type: "bar", orientation: "h", name: "Call OI", marker: { color: "rgba(52,211,153,0.7)" }, customdata: callOI, hovertemplate: "Call OI: %{customdata}<extra></extra>" },
      { y: strikes, x: putOI.map(v => (v / maxOI) * 100), type: "bar", orientation: "h", name: "Put OI", marker: { color: "rgba(244,63,94,0.7)" }, customdata: putOI, hovertemplate: "Put OI: %{customdata}<extra></extra>" },
      { y: strikes, x: deltaLine.map(v => (v - 0.5) * 200), type: "scatter", mode: "lines", name: "Delta", line: { color: "#fbbf24", width: 2 } },
    ];

    if (spotPrice > 0) {
      traces.push({
        y: [spotPrice], x: [0], type: "scatter", mode: "markers+text",
        name: `Spot $${spotPrice.toFixed(0)}`, marker: { color: "#38bdf8", size: 10, symbol: "x" },
        text: [`$${spotPrice.toFixed(0)}`], textposition: "top right", textfont: { color: "#38bdf8", size: 10 },
      });
    }

    const layout = {
      title: { text: `OI by Strike — ${ticker} (${exp.expiration}) — ${strikes.length} strikes`, font: { color: "#94a3b8", size: 12 } },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", barmode: "overlay",
      margin: { l: 50, r: 20, t: 35, b: 35 },
      xaxis: { title: "OI (norm)", color: "#64748b", zeroline: true, zerolinecolor: "#475569", gridcolor: "#1e293b", tickfont: { size: 8 } },
      yaxis: { title: "Strike", color: "#64748b", gridcolor: "#1e293b", tickfont: { size: 8 } },
      legend: { font: { size: 8 }, orientation: "h", y: 1.1 },
      hovermode: "y unified", displayModeBar: false,
      height: Math.max(400, strikes.length * 18),
    };

    window.Plotly.newPlot(chartRef.current, traces, layout, { responsive: true, displayModeBar: false });
  }, [chain, expiryIdx, ticker]);

  // Load Plotly CDN
  useEffect(() => {
    if (window.Plotly) return;
    const s = document.createElement("script");
    s.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    document.head.appendChild(s);
  }, []);

  const expiries = chain?.chain?.map(c => c.expiration) || [];

  return (
    <div className="flex h-full">
      {/* Left sidebar */}
      <div className="w-56 flex-shrink-0 border-r border-slate-800 bg-slate-900/50 p-3 space-y-3 overflow-y-auto">
        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold">Ticker</div>
        <input value={ticker} onChange={e => setTicker(e.target.value.toUpperCase())}
          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-sm text-slate-200 outline-none focus:border-sky-500" />
        <div className="flex flex-wrap gap-1">
          {TICKERS.map(t => (
            <button key={t} onClick={() => setTicker(t)}
              className={`text-[10px] px-2 py-0.5 rounded ${t === t ? "bg-sky-600 text-white" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}>
              {t}
            </button>
          ))}
        </div>

        <div className="text-[10px] uppercase tracking-wider text-slate-500 font-semibold mt-3">Expiry</div>
        <select value={expiryIdx} onChange={e => setExpiryIdx(Number(e.target.value))}
          className="w-full bg-slate-800 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200">
          {expiries.map((exp, i) => <option key={i} value={i}>{exp}</option>)}
        </select>

        <div className="text-[10px] text-slate-500 mt-3">
          {loading && <span className="text-amber-400">● Loading...</span>}
          {error && <span className="text-rose-400">● {error}</span>}
          {chain && !loading && <span className="text-emerald-400">● {chain.chain.length} expirations</span>}
          {lastUpdate && <div className="text-slate-600 mt-1">Updated: {lastUpdate}</div>}
        </div>

        <div className="text-[10px] text-slate-600 mt-3 border-t border-slate-800 pt-2">
          <div>Data: CVForge cvserver</div>
          <div>32 expirations · 171 strikes</div>
        </div>
      </div>

      {/* Main chart area */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <div className="flex items-center gap-3 px-3 py-2 border-b border-slate-800 bg-slate-900/30">
          <span className="text-xs text-slate-400">{ticker}</span>
          {chain && <span className="text-xs text-emerald-400">● LIVE</span>}
          {chain && <span className="text-xs text-slate-500">{chain.chain?.[expiryIdx]?.strikes?.length || 0} strikes</span>}
          <button onClick={() => fetchChain(ticker)} className="ml-auto text-[10px] px-2 py-0.5 bg-slate-800 hover:bg-slate-700 rounded text-slate-400">Refresh</button>
        </div>

        <div className="flex-1 p-2 overflow-auto">
          {loading && !chain && (
            <div className="flex items-center justify-center h-full text-slate-500 text-sm">Loading chain data...</div>
          )}
          {error && (
            <div className="flex items-center justify-center h-full text-rose-400 text-sm">{error}</div>
          )}
          <div ref={chartRef} className="w-full" style={{ minHeight: 400 }}></div>
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 px-3 py-1.5 border-t border-slate-800 text-[9px] text-slate-500">
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-emerald-500/70"></span> Call OI</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-sm bg-rose-500/70"></span> Put OI</span>
          <span className="flex items-center gap-1"><span className="w-3 h-0.5 bg-amber-400"></span> Delta</span>
          <span className="flex items-center gap-1"><span className="w-2 h-2 rounded-full border border-sky-400"></span> Spot</span>
          <span className="ml-auto text-slate-600">CVForge cvserver · {chain?.chain?.length || 0} expirations</span>
        </div>
      </div>
    </div>
  );
}
