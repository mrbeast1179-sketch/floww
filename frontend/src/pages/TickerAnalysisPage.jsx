import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

const PRO_TICKERS = ["NVDA", "TSLA", "SPY", "AAPL", "AMD"];
const TIME_RANGES = ["1m", "5m", "15m", "1h", "1D", "1W"];
const CONFIDENCE_COLORS = { HIGH: "var(--green)", MED: "var(--gold)", LOW: "var(--amber)" };

function fmt(n, d) {
  if (n == null || isNaN(n)) return "—";
  if (d !== undefined) return n.toFixed(d);
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
}

function pctStr(n) {
  if (n == null) return "—";
  return (n > 0 ? "+" : "") + n.toFixed(1) + "%";
}

export default function TickerAnalysisPage({ ticker: propTicker }) {
  const [ticker, setTicker] = useState(propTicker || "SPY");
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [timeRange, setTimeRange] = useState("1D");

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      setLoading(true);
      try {
        const res = await axios.get(`${API}/deep-dive/${ticker}`, { timeout: 120000 });
        if (mounted) { setData(res.data); setErr(null); }
      } catch (e) {
        if (mounted) setErr(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, [ticker, timeRange]);

  const summary = data?.summary || {};
  const chain = data?.chain || {};
  const spot = summary.spot || 0;
  const contracts = chain.contracts || [];
  const topStrikes = summary.top_strikes || [];

  // Key levels from top strikes
  const resistanceLevels = useMemo(() => {
    return topStrikes.filter(s => s.strike > spot).slice(0, 3);
  }, [topStrikes, spot]);

  const supportLevels = useMemo(() => {
    return topStrikes.filter(s => s.strike < spot).sort((a, b) => b.strike - a.strike).slice(0, 3);
  }, [topStrikes, spot]);

  // Compute aggregated stats from contracts
  const stats = useMemo(() => {
    if (!contracts.length) return { totalPremium: 0, callPremium: 0, putPremium: 0, oiTotal: 0 };
    let callPremium = 0, putPremium = 0, oiTotal = 0;
    for (const c of contracts) {
      const prem = c.premium || 0;
      const oi = c.total_oi || c.open_interest || 0;
      oiTotal += oi;
      if ((c.type || "").toUpperCase() === "CALL") callPremium += prem;
      else putPremium += prem;
    }
    return { totalPremium: callPremium + putPremium, callPremium, putPremium, oiTotal };
  }, [contracts]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Page header */}
      <div style={{
        background: "rgba(10,10,11,0.85)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border-c)",
        padding: "8px 16px", minHeight: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          <span className="text-[13px]" style={{ color: "var(--text-tertiary)" }}>Analysis</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-quaternary)" }}>
            <path d="M9 18l6-6-6-6"/>
          </svg>
          <span className="display text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>Ticker Analysis</span>
        </div>
        <div className="mono text-[10px]" style={{ color: "var(--text-tertiary)" }}>
          {data?.asof ? new Date(data.asof).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" }) + " ET" : "—"}
          {" · "}
          <span style={{ color: "var(--amber)" }}>MARKET CLOSED</span>
        </div>
      </div>

      {/* How to read + PRO badge */}
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "4px 16px" }}>
        <button className="text-[11px]" style={{ color: "var(--text-quaternary)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
          How to read this page
        </button>
        <span className="mono text-[10px] font-semibold uppercase tracking-wider rounded px-2 py-0.5"
          style={{ background: "var(--gold-dim)", color: "var(--gold)", border: "1px solid var(--gold-border)" }}>
          PRO
        </span>
      </div>

      {/* Ticker selector */}
      <div style={{ padding: "0 16px 8px", display: "flex", gap: 4, flexWrap: "wrap" }}>
        {PRO_TICKERS.map(t => (
          <button
            key={t}
            type="button"
            className="mono px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-all"
            style={{
              borderRadius: 4,
              border: ticker === t ? "1px solid var(--gold-border)" : "1px solid var(--border-c)",
              background: ticker === t ? "var(--gold-dim)" : "transparent",
              color: ticker === t ? "var(--gold)" : "var(--text-tertiary)",
            }}
            onClick={() => setTicker(t)}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Ticker info bar */}
      <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border-c)", display: "flex", alignItems: "center", gap: 12 }}>
        <span className="display text-[16px] font-bold" style={{ color: "var(--text-primary)" }}>{ticker}</span>
        <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>—</span>
        <span className="mono text-[18px] font-bold" style={{ color: "var(--text-primary)" }}>
          ${spot ? spot.toFixed(2) : "—"}
        </span>
        <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
          Vol — · Avg —
        </span>
        <div style={{ marginLeft: "auto", display: "flex", gap: 2 }}>
          {TIME_RANGES.map(r => (
            <button
              key={r}
              type="button"
              className="mono text-[10px] font-bold uppercase tracking-wider px-2 py-1"
              style={{
                borderRadius: 4,
                border: timeRange === r ? "1px solid var(--border-hover)" : "1px solid transparent",
                background: timeRange === r ? "var(--surface-2)" : "transparent",
                color: timeRange === r ? "var(--text-secondary)" : "var(--text-quaternary)",
              }}
              onClick={() => setTimeRange(r)}
            >
              {r}
            </button>
          ))}
        </div>
      </div>

      {loading && !data && (
        <div className="panel-2 p-6 m-3" style={{ textAlign: "center", color: "var(--text-quaternary)", fontSize: 13 }}>
          Loading {ticker} analysis… (this may take up to 2 minutes)
        </div>
      )}

      {err && (
        <div className="panel-2 p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
          Error: {err}
        </div>
      )}

      {data && (
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>

          {/* EMA toggle row */}
          <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
            {["Key Levels", "OI Walls", "Volume", "Patterns"].map(f => (
              <button key={f} type="button" className="mono text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5"
                style={{ borderRadius: 4, border: "1px solid var(--border-c)", background: "var(--surface-2)", color: "var(--text-tertiary)" }}>
                {f}
              </button>
            ))}
            <button type="button" className="mono text-[10px] font-bold uppercase tracking-wider px-2.5 py-1.5"
              style={{ borderRadius: 4, border: "1px solid var(--border-c)", background: "transparent", color: "var(--text-quaternary)" }}>
              Reset
            </button>
            <span className="text-[10px] margin-left-auto" style={{ color: "var(--text-quaternary)", marginLeft: "auto" }}>
              Polygon · 1D · daily · levels from /analyze
            </span>
          </div>

          {/* Live Bias */}
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 12 }}>
              <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: "var(--text-quaternary)" }}>Live Bias</span>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
              <div>
                <div className="display text-[18px] font-bold" style={{ color: "var(--emerald)" }}>
                  BULLISH STEADY TREND
                </div>
                <div className="text-[12px]" style={{ color: "var(--text-secondary)", marginTop: 2 }}>
                  {ticker} — bullish setup, high conviction. Thesis broken below ${supportLevels[0]?.strike?.toFixed(0) || "—"}.
                </div>
              </div>
              <div style={{ marginLeft: "auto", textAlign: "right" }}>
                <div className="display text-[22px] font-bold tracking-tight" style={{ color: "var(--gold)" }}>
                  88<span className="text-[14px]" style={{ color: "var(--text-tertiary)" }}>/100</span>
                </div>
                <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>
                  HIGH CONVICTION
                </div>
              </div>
            </div>
          </div>

          {/* Confluence Zone */}
          <div className="card" style={{ padding: 16 }}>
            <div className="display text-[13px] font-bold" style={{ color: "var(--text-primary)", marginBottom: 8 }}>Confluence</div>
            <div className="text-[12px]" style={{ color: "var(--text-secondary)", marginBottom: 8 }}>
              Confluence Zone ${spot ? (spot * 0.99).toFixed(2) : "—"} – ${spot ? (spot * 1.01).toFixed(2) : "—"}
              {" · "}5 levels align in a tight band just below spot.
            </div>
          </div>

          {/* Key Levels */}
          <div className="card" style={{ padding: 0 }}>
            <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-c)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span className="display text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>Key Levels</span>
              <span className="text-[10px]" style={{ color: "var(--text-quaternary)" }}>{Math.min(topStrikes.length, 5)} levels</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 1, padding: "8px 16px" }}>
              {/* Resistance levels */}
              {resistanceLevels.length > 0 && resistanceLevels.map((s, i) => (
                <div key={`r${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span className="text-[10px] font-bold" style={{ color: "var(--green)" }}>Resistance</span>
                    <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>{pctStr(((s.strike - spot) / spot * 100))}</span>
                  </div>
                  <span className="mono text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>{s.strike ? s.strike.toFixed(0) : "—"}</span>
                </div>
              ))}
              {/* King */}
              {topStrikes.length > 0 && (
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span className="text-[10px] font-bold" style={{ color: "var(--gold)" }}>KING</span>
                    {topStrikes[0]?.strike && <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>Live</span>}
                  </div>
                  <span className="mono text-[13px] font-bold" style={{ color: "var(--gold)" }}>
                    {topStrikes[0]?.strike ? topStrikes[0].strike.toFixed(0) : "—"}
                  </span>
                </div>
              )}
              {/* Support levels */}
              {supportLevels.length > 0 && supportLevels.map((s, i) => (
                <div key={`s${i}`} style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 0" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                    <span className="text-[10px] font-bold" style={{ color: "var(--red)" }}>Support</span>
                    <span className="text-[10px]" style={{ color: "var(--text-tertiary)" }}>{pctStr(((s.strike - spot) / spot * 100))}</span>
                  </div>
                  <span className="mono text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>{s.strike ? s.strike.toFixed(0) : "—"}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Options Flow Summary */}
          <div className="card" style={{ padding: 16 }}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
              <span className="display text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>
                Alpha Pod ENGINE — live
              </span>
              <span className="text-[10px]" style={{ color: "var(--text-quaternary)" }}>Options Flow · 7D</span>
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8 }}>
              <div>
                <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>Premium</div>
                <div className="mono text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>
                  ${fmt(stats.totalPremium)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>Net Gamma</div>
                <div className="mono text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>
                  {fmt(summary.total_gex)}
                </div>
              </div>
              <div>
                <div className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-quaternary)" }}>OI Total</div>
                <div className="mono text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>
                  {fmt(stats.oiTotal)}
                </div>
              </div>
            </div>
          </div>

          {/* Top Flows */}
          {topStrikes.length > 0 && (
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>Top Flows</span>
                <span className="text-[11px]" style={{ color: "var(--text-tertiary)", marginLeft: 8 }}>
                  {Math.min(contracts.length, 5)} alerts · 7d
                </span>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["Type", "Contract", "Premium", "Conf."].map(h => (
                      <th key={h} style={{
                        color: "var(--text-tertiary)", padding: "8px 10px", textAlign: "left",
                        fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em",
                        whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {topStrikes.slice(0, 5).map((s, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)", height: 34 }}>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[10px] font-bold" style={{ color: (s.gex || 0) < 0 ? "var(--green)" : "var(--red)" }}>
                          {(s.gex || 0) > 0 ? "CALL" : "PUT"} {(s.gex || 0) > 0 ? "BUY" : "SELL"}
                        </span>
                      </td>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[11px]" style={{ color: "var(--text-secondary)" }}>
                          {s.strike ? `$${s.strike.toFixed(0)}` : "—"}
                        </span>
                      </td>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[12px]" style={{ color: "var(--text-primary)" }}>
                          —
                        </span>
                      </td>
                      <td style={{ padding: "0 10px" }}>
                        <span style={{ padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                          background: i === 0 ? "var(--green-dim)" : "var(--gold-dim)",
                          color: i === 0 ? "var(--green)" : "var(--gold)",
                        }}>
                          {i === 0 ? "HIGH" : "MED"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Actions */}
          <div style={{ display: "flex", gap: 8, padding: "4px 0" }}>
            <button type="button" className="mono text-[10px] font-bold uppercase tracking-wider px-3 py-1.5"
              style={{ borderRadius: 4, border: "1px solid var(--border-c)", background: "var(--surface-2)", color: "var(--text-secondary)" }}>
              Set alert at confluence
            </button>
            <button type="button" className="mono text-[10px] font-bold uppercase tracking-wider px-3 py-1.5"
              style={{ borderRadius: 4, border: "1px solid var(--border-c)", background: "var(--surface-2)", color: "var(--text-secondary)" }}>
              Save to watchlist
            </button>
            <button type="button" className="mono text-[10px] font-bold uppercase tracking-wider px-3 py-1.5"
              style={{ borderRadius: 4, border: "1px solid var(--border-c)", background: "var(--surface-2)", color: "var(--text-secondary)" }}>
              Share
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
