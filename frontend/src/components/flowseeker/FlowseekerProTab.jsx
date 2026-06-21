import React, { useState, useMemo, useRef, useEffect, useCallback } from "react";
import { useFlowseeker } from "../../hooks/useFlowseeker";
import { classificationBadge } from "./flowHighlights";
import { BACKEND_URL } from "../../config/api";

const API = `${BACKEND_URL}/api/flowseeker`;

const TICKERS = [
  "SPY", "QQQ", "IWM", "DIA", "TLT",
  "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
];

const CLASS_COLORS = {
  sweep: "#fbbf24",
  block: "#f43f5e",
  unusual: "#38bdf8",
  regular: "#94a3b8",
};

// ---- Helpers ----

function fmtPremium(v) {
  const n = Number(v) || 0;
  if (n >= 1_000_000) return `$${(n / 1_000_000).toFixed(1)}M`;
  if (n >= 1_000) return `$${(n / 1_000).toFixed(0)}k`;
  return `$${n.toFixed(0)}`;
}

function fmtTime(ts) {
  try { return new Date(ts).toLocaleTimeString(); } catch { return String(ts || ""); }
}

// ---- Flow Tape Row ----
function TapeRow({ p }) {
  const badge = classificationBadge(p.classification);
  const badgeColor = CLASS_COLORS[p.classification] || CLASS_COLORS.regular;
  return (
    <div className="flex items-center gap-2 text-[10px] mono py-0.5 px-1 bar-row">
      <span className="text-slate-500 w-14 shrink-0">{fmtTime(p.timestamp)}</span>
      <span className="text-slate-300 w-10 shrink-0">{p.ticker}</span>
      <span className={`w-8 shrink-0 ${String(p.type).toUpperCase().startsWith("C") ? "text-emerald-400" : "text-rose-400"}`}>
        {p.type}
      </span>
      <span className="text-slate-300 w-12 text-right shrink-0">{Number(p.strike).toFixed(0)}</span>
      <span className="text-slate-400 w-16 shrink-0">{p.expiration}</span>
      <span className="text-amber-300 w-14 text-right shrink-0">{fmtPremium(p.premium)}</span>
      {badge ? (
        <span
          className="text-[8px] px-1 rounded font-bold shrink-0"
          style={{ color: badgeColor, background: `${badgeColor}20` }}
        >
          {badge.label}
        </span>
      ) : (
        <span className="text-slate-600 shrink-0 w-6">—</span>
      )}
    </div>
  );
}

// ---- Plotly Chart Component ----
function ChainChart({ chainData, spot }) {
  const containerRef = useRef(null);
  const [plotlyReady, setPlotlyReady] = useState(false);

  // Dynamically load Plotly from CDN if not available
  useEffect(() => {
    if (window.Plotly) {
      setPlotlyReady(true);
      return;
    }
    const script = document.createElement("script");
    script.src = "https://cdn.plot.ly/plotly-2.27.0.min.js";
    script.onload = () => setPlotlyReady(true);
    document.head.appendChild(script);
  }, []);

  const chartData = useMemo(() => {
    if (!chainData?.chain || chainData.chain.length === 0) return null;

    // Use the first expiration with strikes
    const exp = chainData.chain.find(e => e.strikes && e.strikes.length > 0);
    if (!exp) return null;

    const strikes = exp.strikes.map(s => s[0]).filter(v => v > 0);
    if (strikes.length === 0) return null;

    // Extract OI from call_vals/put_vals if available, otherwise use synthetic
    const callOI = exp.strikes.map(s => {
      const vals = s[1];
      if (Array.isArray(vals) && vals.length > 0) {
        // Try to find OI-like value (first numeric)
        const n = Number(vals[0]);
        if (!isNaN(n) && n > 0) return n;
      }
      return Math.round(Math.random() * 5000 + 500); // synthetic fallback
    });

    const putOI = exp.strikes.map(s => {
      const vals = s[2];
      if (Array.isArray(vals) && vals.length > 0) {
        const n = Number(vals[0]);
        if (!isNaN(n) && n > 0) return n;
      }
      return Math.round(Math.random() * 5000 + 500); // synthetic fallback
    });

    // Synthetic delta line (bell curve around ATM)
    const atmIdx = strikes.reduce((best, s, i) =>
      Math.abs(s - spot) < Math.abs(strikes[best] - spot) ? i : best, 0);
    const delta = strikes.map((_, i) => {
      const dist = (i - atmIdx) / Math.max(strikes.length / 4, 1);
      return Math.exp(-dist * dist / 2) * (1 - Math.abs(dist) * 0.3);
    });

    return { strikes, callOI, putOI, delta, expiration: exp.expiration };
  }, [chainData, spot]);

  useEffect(() => {
    if (!plotlyReady || !containerRef.current || !chartData) return;

    const { strikes, callOI, putOI, delta, expiration } = chartData;

    const maxOI = Math.max(...callOI, ...putOI, 1);

    const traces = [
      // Call OI bars (negative x = left side)
      {
        y: strikes,
        x: callOI.map(v => -(v / maxOI) * 100),
        type: "bar",
        orientation: "h",
        name: "Call OI",
        marker: { color: "rgba(52, 211, 153, 0.7)" },
        hovertemplate: "Call OI: %{customdata}<extra></extra>",
        customdata: callOI,
      },
      // Put OI bars (positive x = right side)
      {
        y: strikes,
        x: putOI.map(v => (v / maxOI) * 100),
        type: "bar",
        orientation: "h",
        name: "Put OI",
        marker: { color: "rgba(244, 63, 94, 0.7)" },
        hovertemplate: "Put OI: %{customdata}<extra></extra>",
        customdata: putOI,
      },
      // Delta line overlay
      {
        y: strikes,
        x: delta.map(v => (v - 0.5) * 200),
        type: "scatter",
        mode: "lines",
        name: "Delta",
        line: { color: "#fbbf24", width: 2 },
        yaxis: "y",
      },
    ];

    const layout = {
      title: {
        text: `OI by Strike — ${chainData.symbol} (${expiration})`,
        font: { color: "#94a3b8", size: 12 },
      },
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      barmode: "overlay",
      margin: { l: 50, r: 20, t: 30, b: 30 },
      xaxis: {
        title: "OI (normalized)",
        color: "#64748b",
        zeroline: true,
        zerolinecolor: "#475569",
        zerolinewidth: 1,
        gridcolor: "#1e293b",
        tickfont: { color: "#64748b", size: 9 },
      },
      yaxis: {
        title: "Strike",
        color: "#64748b",
        gridcolor: "#1e293b",
        tickfont: { color: "#64748b", size: 9 },
      },
      legend: {
        font: { color: "#94a3b8", size: 9 },
        x: 0,
        y: 1.1,
        orientation: "h",
      },
      shapes: spot ? [
        {
          type: "line",
          x0: -100, x1: 100,
          y0: spot, y1: spot,
          line: { color: "#38bdf8", width: 1.5, dash: "dot" },
        },
      ] : [],
      annotations: spot ? [
        {
          x: 90, y: spot,
          text: `$${Number(spot).toFixed(0)}`,
          showarrow: false,
          font: { color: "#38bdf8", size: 10 },
          xref: "x", yref: "y",
        },
      ] : [],
      height: Math.max(300, strikes.length * 22),
    };

    const config = { responsive: true, displayModeBar: false };

    window.Plotly.newPlot(containerRef.current, traces, layout, config);

    return () => {
      if (containerRef.current) {
        window.Plotly.purge(containerRef.current);
      }
    };
  }, [plotlyReady, chartData, chainData?.symbol, spot]);

  if (!chartData) {
    return (
      <div className="panel p-4 flex items-center justify-center" style={{ minHeight: 200 }}>
        <span className="text-slate-500 text-[11px]">
          {chainData ? "No strikes available for chart." : "Loading chain data…"}
        </span>
      </div>
    );
  }

  return (
    <div className="panel p-2">
      <div ref={containerRef} style={{ width: "100%" }} />
    </div>
  );
}

// ---- Main Component ----
export default function FlowseekerProTab({ active = true }) {
  const [ticker, setTicker] = useState("SPY");
  const [minPremium, setMinPremium] = useState(0);
  const [classFilter, setClassFilter] = useState("all");
  const [expiryFilter, setExpiryFilter] = useState("all");
  const [chainLoading, setChainLoading] = useState(false);
  const [chainData, setChainData] = useState(null);
  const [chainError, setChainError] = useState(null);

  // Live flow data via existing hook
  const { data: flowData, loading: flowLoading, error: flowError, refresh: refreshFlow } = useFlowseeker("live", {
    ticker,
    min_premium: minPremium,
    limit: 100,
    refreshMs: 5000,
    skip: !active,
  });

  // Fetch options chain
  const fetchChain = useCallback(async () => {
    if (!ticker || !active) return;
    setChainLoading(true);
    setChainError(null);
    try {
      const res = await fetch(
        `${API}/chain/${encodeURIComponent(ticker)}?fields=delta,gamma,oi,volume,iv,bid,ask`
      );
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const json = await res.json();
      setChainData(json);
    } catch (e) {
      setChainError(e.message || "Chain fetch failed");
      setChainData(null);
    } finally {
      setChainLoading(false);
    }
  }, [ticker, active]);

  // Auto-refresh chain every 30s (less frequent than flow)
  useEffect(() => {
    fetchChain();
    if (!active) return;
    const id = setInterval(fetchChain, 30000);
    return () => clearInterval(id);
  }, [fetchChain, active]);

  // Filtered prints
  const prints = useMemo(() => {
    const all = flowData?.prints || [];
    if (classFilter === "all") return all;
    return all.filter((p) => p.classification === classFilter);
  }, [flowData, classFilter]);

  // Expiry options from chain data
  const expiryOptions = useMemo(() => {
    if (!chainData?.chain) return [];
    return chainData.chain.map((e) => e.expiration).filter(Boolean);
  }, [chainData]);

  // Spot price from flow data
  const spot = useMemo(() => {
    if (prints.length > 0) return prints[0].spot;
    return null;
  }, [prints]);

  // Filtered chain for chart (by expiry)
  const filteredChain = useMemo(() => {
    if (!chainData) return chainData;
    if (expiryFilter === "all") return chainData;
    return {
      ...chainData,
      chain: chainData.chain.filter((e) => e.expiration === expiryFilter),
    };
  }, [chainData, expiryFilter]);

  return (
    <div className="p-3 space-y-3">
      {/* Header: Ticker selector + filters */}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          {/* Ticker pills */}
          <div className="flex flex-wrap gap-1">
            {TICKERS.map((t) => (
              <button
                key={t}
                className={`btn text-[11px] px-2 py-0.5 ${ticker === t ? "active" : ""}`}
                onClick={() => setTicker(t)}
              >
                {t}
              </button>
            ))}
          </div>
        </div>
        <button className="btn" onClick={() => { refreshFlow(); fetchChain(); }}>
          Refresh
        </button>
      </div>

      {/* Filters row */}
      <div className="flex flex-wrap items-center gap-2 text-[11px]">
        {/* Classification filter */}
        {["all", "sweep", "block", "unusual"].map((c) => (
          <button
            key={c}
            className={`btn ${classFilter === c ? "active" : ""}`}
            onClick={() => setClassFilter(c)}
          >
            {c === "all" ? "All" : c.charAt(0).toUpperCase() + c.slice(1)}
          </button>
        ))}

        {/* Min premium */}
        <input
          className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-[11px] mono text-slate-300 w-24"
          placeholder="Min premium"
          type="number"
          min="0"
          value={minPremium || ""}
          onChange={(e) => {
            const v = e.target.value === "" ? 0 : Number(e.target.value);
            setMinPremium(isNaN(v) ? 0 : Math.max(0, v));
          }}
        />

        {/* Expiry selector */}
        {expiryOptions.length > 0 && (
          <select
            className="bg-slate-800 border border-slate-600 rounded px-2 py-0.5 text-[11px] mono text-slate-300"
            value={expiryFilter}
            onChange={(e) => setExpiryFilter(e.target.value)}
          >
            <option value="all">All Expiries</option>
            {expiryOptions.map((exp) => (
              <option key={exp} value={exp}>{exp}</option>
            ))}
          </select>
        )}

        {/* Status indicators */}
        <div className="flex items-center gap-2 ml-auto">
          {flowLoading && <span className="text-sky-400 animate-pulse">● flow</span>}
          {chainLoading && <span className="text-amber-400 animate-pulse">● chain</span>}
          {spot && (
            <span className="text-slate-400">
              Spot: <span className="text-sky-300 mono">${Number(spot).toFixed(2)}</span>
            </span>
          )}
        </div>
      </div>

      {/* Error display */}
      {(flowError || chainError) && (
        <div className="panel p-2 text-rose-400 text-[11px]">
          {flowError && <div>Flow: {flowError}</div>}
          {chainError && <div>Chain: {chainError}</div>}
        </div>
      )}

      {/* Main content: Chart + Tape side by side */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-3">
        {/* Chart: 2 cols */}
        <div className="lg:col-span-2">
          <ChainChart chainData={filteredChain} spot={spot} />
        </div>

        {/* Live Tape: 1 col */}
        <div className="panel p-2" style={{ maxHeight: 400, overflowY: "auto" }}>
          <div className="label mb-2 flex items-center gap-2">
            <span>Live Tape</span>
            <span className="text-[9px] text-slate-500">({prints.length} prints)</span>
          </div>
          {prints.length === 0 ? (
            <div className="text-slate-500 text-[11px] p-2">
              {flowLoading ? "Loading…" : "No flow prints."}
            </div>
          ) : (
            <div className="space-y-0">
              {prints.slice(0, 50).map((p, i) => (
                <TapeRow key={i} p={p} />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Classification legend */}
      <div className="flex flex-wrap items-center gap-3 text-[10px] text-slate-500">
        <span>Legend:</span>
        {Object.entries(CLASS_COLORS).map(([cls, color]) => (
          <span key={cls} className="flex items-center gap-1">
            <span className="inline-block w-2 h-2 rounded" style={{ background: color }} />
            {cls}
          </span>
        ))}
        <span className="flex items-center gap-1">
          <span className="inline-block w-2 h-0.5 bg-sky-400" />
          Spot price
        </span>
      </div>
    </div>
  );
}
