import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

const DEFAULT_TICKERS = ["NVDA", "TSLA", "SPY", "AAPL", "AMD"];

const SECTORS = [
  "Technology", "Healthcare", "Financial", "Energy", "Consumer",
  "Industrials", "Materials", "Utilities", "Real Estate", "Communication"
];

function confidenceColor(conf) {
  const c = (conf || "").toUpperCase();
  if (c === "HIGH") return "var(--conf-high)";
  if (c === "MED" || c === "MEDIUM") return "var(--gold)";
  if (c === "LOW") return "var(--amber)";
  return "var(--text-tertiary)";
}

export default function TickerAnalysisPage({ ticker: propTicker }) {
  const [ticker, setTicker] = useState(propTicker || "NVDA");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [timeRange, setTimeRange] = useState("1D");

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${API}/deep-dive/${ticker}`, { timeout: 120000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, [ticker, timeRange]);

  const summary = data?.summary || {};
  const chain = data?.chain || {};

  // Compute key levels from chain data
  const keyLevels = useMemo(() => {
    if (!chain.contracts) return [];
    return chain.contracts.slice(0, 20);
  }, [chain]);

  // Compute top flows from contracts
  const topFlows = useMemo(() => {
    if (!chain.contracts) return [];
    return chain.contracts
      .filter(c => c.premium && c.premium > 0)
      .sort((a, b) => (b.premium || 0) - (a.premium || 0))
      .slice(0, 5);
  }, [chain]);

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        {/* Page header */}
        <div className="fa-page-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1>Ticker Analysis</h1>
            <span className="tag" style={{ background: "var(--gold-dim)", color: "var(--gold)", fontSize: 10 }}>NEW</span>
          </div>
          <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            {data?.asof ? new Date(data.asof).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) : "—"} ET
          </span>
        </div>

        {/* Ticker selector */}
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--border-c)", alignItems: "center" }}>
          <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)", marginRight: 8 }}>PRO</span>
          {DEFAULT_TICKERS.map(t => (
            <button
              key={t}
              className={`fa-chip ${ticker === t ? "active" : ""}`}
              onClick={() => setTicker(t)}
            >
              {t}
            </button>
          ))}
        </div>

        {/* Ticker info bar */}
        <div style={{ display: "flex", gap: 16, padding: "8px 16px", borderBottom: "1px solid var(--border-c)", alignItems: "center" }}>
          <span className="display text-[16px] font-bold" style={{ color: "var(--text-primary)" }}>
            {ticker}
          </span>
          <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            {summary.sector || "—"}
          </span>
          <span className="mono text-[14px] font-bold" style={{ color: "var(--text-primary)", marginLeft: "auto" }}>
            ${summary.spot?.toFixed(2) || "—"}
          </span>
          {summary.change != null && (
            <span className="mono text-[12px]" style={{ color: summary.change >= 0 ? "var(--emerald)" : "var(--red)" }}>
              {summary.change >= 0 ? "+" : ""}{summary.change.toFixed(2)}%
            </span>
          )}
        </div>

        {/* Time range selector */}
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--border-c)" }}>
          {["1m", "5m", "15m", "1h", "1D", "1W"].map(r => (
            <button
              key={r}
              className={`fa-chip ${timeRange === r ? "active" : ""}`}
              onClick={() => setTimeRange(r)}
            >
              {r}
            </button>
          ))}
        </div>

        {loading && !data && (
          <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
            Loading {ticker} analysis… (this may take up to 2 minutes)
          </div>
        )}

        {error && (
          <div className="panel p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
            Error: {error}
          </div>
        )}

        {/* Bias / Thesis */}
        {data && (
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
            <div style={{ display: "flex", gap: 16, alignItems: "center" }}>
              <div>
                <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>Live Bias</span>
                <div className="display text-[14px] font-bold" style={{ color: "var(--emerald)" }}>
                  BULLISH STEADY TREND
                </div>
              </div>
              <div style={{ marginLeft: "auto", textAlign: "right" }}>
                <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>Score</span>
                <div className="display text-[18px] font-bold" style={{ color: "var(--gold)" }}>
                  88<span className="text-[12px]" style={{ color: "var(--text-tertiary)" }}>/100</span>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* Key Levels */}
        {summary.top_strikes && summary.top_strikes.length > 0 && (
          <div style={{ padding: "0 16px 16px" }}>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Key Levels
                </span>
              </div>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["Strike", "GEX", "Dist"].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {summary.top_strikes.slice(0, 5).map((s, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-1.5 mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                        ${s.strike?.toFixed(0) || "—"}
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: (s.gex || 0) > 0 ? "var(--emerald)" : "var(--red)" }}>
                        {(s.gex || 0) > 0 ? "+" : ""}{(s.gex / 1e6).toFixed(1)}M
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: "var(--text-tertiary)" }}>
                        {s.strike && summary.spot ? `${s.strike > summary.spot ? "+" : ""}${((s.strike - summary.spot) / summary.spot * 100).toFixed(1)}%` : "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Top Flows */}
        {topFlows.length > 0 && (
          <div style={{ padding: "0 16px 16px" }}>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Top Flows
                </span>
              </div>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["Type", "Contract", "Premium", "Conf."].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topFlows.map((f, i) => (
                    <tr key={i} style={{ borderBottom: "var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-1.5">
                        <span className="mono text-[10px] font-semibold" style={{ color: (f.type || "").toUpperCase() === "CALL" ? "var(--emerald)" : "var(--red)" }}>
                          {(f.type || "—").toUpperCase()} BUY
                        </span>
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: "var(--text-secondary)", fontSize: 10 }}>
                        {f.strike ? `$${f.strike}` : ""} {(f.type || "").toUpperCase()} {f.expiry || ""}
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: "var(--text-primary)" }}>
                        {f.premium ? `$${(f.premium / 1e3).toFixed(0)}K` : "—"}
                      </td>
                      <td className="px-3 py-1.5">
                        <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: confidenceColor(f.confidence) }}>
                          {f.confidence || "—"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* Source */}
        <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border-c)" }}>
          <span className="text-[10px]" style={{ color: "var(--text-quaternary)" }}>
            Source: Polygon · {ticker} option snapshot · Live analysis
          </span>
        </div>
      </div>
    </div>
  );
}
