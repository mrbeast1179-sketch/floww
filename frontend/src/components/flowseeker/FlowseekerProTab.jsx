import React, { useState, useEffect, useCallback } from "react";
import { useFlowseeker } from "../../hooks/useFlowseeker";
import { BACKEND_URL } from "../../config/api";

const API = `${BACKEND_URL}/api/flowseeker`;
const TICKERS = ["SPY", "QQQ", "IWM", "DIA", "TLT", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL"];

export default function FlowseekerProTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [chainData, setChainData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [lastUpdate, setLastUpdate] = useState(null);
  const [filter, setFilter] = useState("all");
  const [expiryIdx, setExpiryIdx] = useState(0);

  // Load chain data
  const loadChain = useCallback(async (sym) => {
    setLoading(true);
    setError(null);
    try {
      const resp = await fetch(`${API}/chain/${sym}`);
      const data = await resp.json();
      if (data && data.chain && data.chain.length > 0) {
        setChainData(data);
        setLastUpdate(new Date().toLocaleTimeString());
        setExpiryIdx(0);
      } else {
        setError(data?.error || "No chain data available");
      }
    } catch (e) {
      setError(e.message || "Failed to fetch chain");
    } finally {
      setLoading(false);
    }
  }, []);

  // Load on mount and ticker change
  useEffect(() => {
    if (active) loadChain(ticker);
  }, [ticker, active, loadChain]);

  // Auto-refresh every 15s
  useEffect(() => {
    if (!active) return;
    const id = setInterval(() => loadChain(ticker), 15000);
    return () => clearInterval(id);
  }, [ticker, active, loadChain]);

  // Render chart when data or plotly ready
  useEffect(() => {
    if (!chainData || !window.Plotly) return;

    const exp = chainData.chain[expiryIdx] || chainData.chain[0];
    if (!exp || !exp.strikes) return;

    const params = chainData.params || [];
    const oiIdx = params.indexOf("openInterest");
    const oiValsIdx = oiIdx > 0 ? oiIdx - 1 : 4;

    const strikes = exp.strikes.map(s => s[0]).filter(v => v > 0);
    const callOI = exp.strikes.map(s => (s[1] || [])[oiValsIdx] || 0);
    const putOI = exp.strikes.map(s => (s[2] || [])[oiValsIdx] || 0);
    const spot = (exp.strikes[0]?.[1] || [])[13] || 0;

    const maxOI = Math.max(...callOI, ...putOI, 1);

    // Delta from actual data if available, else synthetic
    const deltaIdx = params.indexOf("delta");
    const deltaValsIdx = deltaIdx > 0 ? deltaIdx - 1 : 3;
    const delta = exp.strikes.map(s => {
      const v = (s[1] || [])[deltaValsIdx];
      return v != null ? v : 0.5;
    });

    const el = document.getElementById("chain-chart");
    if (!el) return;

    const traces = [
      {
        y: strikes, x: callOI.map(v => -(v / maxOI) * 100),
        type: "bar", orientation: "h", name: "Call OI",
        marker: { color: "rgba(52,211,153,0.7)" },
        hovertemplate: "Call OI: %{customdata}<extra></extra>",
        customdata: callOI,
      },
      {
        y: strikes, x: putOI.map(v => (v / maxOI) * 100),
        type: "bar", orientation: "h", name: "Put OI",
        marker: { color: "rgba(244,63,94,0.7)" },
        hovertemplate: "Put OI: %{customdata}<extra></extra>",
        customdata: putOI,
      },
      {
        y: strikes, x: delta.map(v => (v - 0.5) * 200),
        type: "scatter", mode: "lines", name: "Delta",
        line: { color: "#fbbf24", width: 2 },
      },
    ];

    if (spot > 0) {
      traces.push({
        y: [spot, spot], x: [-100, 100],
        type: "scatter", mode: "lines", name: `Spot $${spot.toFixed(0)}`,
        line: { color: "#38bdf8", width: 1.5, dash: "dot" },
      });
    }

    const layout = {
      title: { text: `OI by Strike — ${chainData.symbol} (${exp.expiration})`, font: { color: "#94a3b8", size: 13 } },
      paper_bgcolor: "rgba(0,0,0,0)", plot_bgcolor: "rgba(0,0,0,0)", barmode: "overlay",
      margin: { l: 55, r: 20, t: 35, b: 35 },
      xaxis: { title: "OI (normalized)", color: "#64748b", gridcolor: "#1e293b", tickfont: { size: 9 } },
      yaxis: { title: "Strike", color: "#64748b", gridcolor: "#1e293b", tickfont: { size: 9 } },
      legend: { font: { size: 9 }, orientation: "h", y: 1.08 },
      hovermode: "x unified", displayModeBar: false,
      height: Math.max(350, strikes.length * 20),
    };

    window.Plotly.newPlot(el, traces, layout, { responsive: true, displayModeBar: false });
  }, [chainData, expiryIdx]);

  // Load Plotly CDN if not available
  useEffect(() => {
    if (window.Plotly) return;
    const script = document.createElement("script");
    script.src = "https://cdn.plot.ly/plotly-2.35.2.min.js";
    document.head.appendChild(script);
  }, []);

  return (
    <div style={{ display: "flex", height: "100%" }}>
      {/* Sidebar */}
      <div style={{ width: 240, flexShrink: 0, background: "#0d0f14", borderRight: "1px solid rgba(255,255,255,.06)", padding: 12, overflowY: "auto" }}>
        <input
          value={ticker}
          onChange={e => setTicker(e.target.value.toUpperCase())}
          onKeyDown={e => { if (e.key === "Enter") loadChain(ticker); }}
          placeholder="Ticker (e.g. SPY)"
          style={{ width: "100%", background: "#161a22", border: "1px solid rgba(255,255,255,.1)", borderRadius: 8, color: "#e6e8ee", fontSize: 14, padding: "8px 12px", outline: "none", boxSizing: "border-box", marginBottom: 8 }}
        />
        <div style={{ display: "flex", flexWrap: "wrap", gap: 4, marginBottom: 12 }}>
          {TICKERS.map(t => (
            <span key={t} onClick={() => { setTicker(t); }}
              style={{ fontSize: 11, padding: "3px 10px", borderRadius: 12, cursor: "pointer", background: t === ticker ? "#3b82f6" : "rgba(59,130,246,.12)", color: t === ticker ? "#fff" : "#60a5fa", border: `1px solid ${t === ticker ? "#3b82f6" : "rgba(59,130,246,.2)"}` }}>
              {t}
            </span>
          ))}
        </div>

        <div style={{ marginTop: 14 }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".8px", color: "#7a8599", marginBottom: 6, fontWeight: 600 }}>Flow Filters</div>
          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
            {["all", "sweep", "block", "unusual"].map(f => (
              <span key={f} onClick={() => setFilter(f)}
                style={{ fontSize: 10, padding: "3px 8px", borderRadius: 10, cursor: "pointer", background: filter === f ? "#3b82f6" : "rgba(120,120,120,.15)", color: filter === f ? "#fff" : "#888" }}>
                {f.toUpperCase()}
              </span>
            ))}
          </div>
        </div>

        {chainData && chainData.chain && (
          <div style={{ marginTop: 14 }}>
            <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".8px", color: "#7a8599", marginBottom: 6, fontWeight: 600 }}>Expiry</div>
            <select value={expiryIdx} onChange={e => setExpiryIdx(Number(e.target.value))}
              style={{ width: "100%", background: "#161a22", border: "1px solid rgba(255,255,255,.08)", borderRadius: 6, color: "#e6e8ee", fontSize: 12, padding: "6px 8px" }}>
              {chainData.chain.map((c, i) => <option key={i} value={i}>{c.expiration}</option>)}
            </select>
          </div>
        )}
      </div>

      {/* Main content */}
      <div style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}>
        <div style={{ flex: 1, padding: 12, overflow: "auto" }}>
          <div style={{ fontSize: 12, fontWeight: 600, color: "#b0b8c4", padding: "0 0 8px" }}>
            {loading ? "Loading chain data..." : error ? `Error: ${error}` : chainData ? `${chainData.symbol} — ${chainData.chain[expiryIdx]?.expiration || ""}` : "Select a ticker"}
          </div>
          <div id="chain-chart" style={{ width: "100%", height: "calc(100% - 30px)", minHeight: 350 }}></div>
          <div style={{ display: "flex", gap: 12, padding: "8px 0", fontSize: 9, color: "#7a8599", borderTop: "1px solid rgba(255,255,255,.04)", marginTop: 8 }}>
            <span>● Call OI</span><span>● Put OI</span><span>— Delta</span><span>— Spot</span>
          </div>
        </div>

        {/* Live Tape */}
        <div style={{ height: 140, flexShrink: 0, background: "#0d0f14", borderTop: "1px solid rgba(255,255,255,.06)", padding: "8px 12px", overflowY: "auto" }}>
          <div style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: ".8px", color: "#7a8599", marginBottom: 6, fontWeight: 600, display: "flex", justifyContent: "space-between" }}>
            <span>Live Flow</span><span>{lastUpdate || "—"}</span>
          </div>
          <div style={{ fontSize: 11, color: "#7a8599" }}>
            {loading ? "Loading..." : error ? error : "Data source: CVForge cvserver (32 expirations, 171 strikes)"}
          </div>
        </div>
      </div>
    </div>
  );
}
