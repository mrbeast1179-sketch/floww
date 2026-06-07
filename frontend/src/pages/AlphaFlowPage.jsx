import React, { useEffect, useState } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

function fmt(n) {
  if (n == null || isNaN(n)) return "—";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(0);
}

export default function AlphaFlowPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/alpha-flow`, { timeout: 30000 });
        if (mounted) { setData(res.data); setErr(null); }
      } catch (e) {
        if (mounted) setErr(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, []);

  const top10 = data?.top_10 || [];
  const market = data?.market || {};
  const sessionDate = data?.session_date || new Date().toISOString().split("T")[0];
  const summaryMd = data?.executive_summary_md || "";

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
          <span className="text-[13px]" style={{ color: "var(--text-tertiary)" }}>Alpha Flow</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-quaternary)" }}>
            <path d="M9 18l6-6-6-6"/>
          </svg>
          <span className="display text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>Alpha Flow</span>
          <span className="inline-flex items-center gap-1.5 rounded-md px-2 py-1"
            style={{ background: "var(--surface-1)", border: "1px solid var(--border-c)", fontSize: 10, color: "var(--text-tertiary)" }}>
            Cached
          </span>
        </div>
        <div className="mono text-[10px]" style={{ color: "var(--text-tertiary)" }}>
          {new Date().toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" })} ET
        </div>
      </div>

      {/* How to read */}
      <div style={{ padding: "4px 16px", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <button className="text-[11px]" style={{ color: "var(--text-quaternary)", background: "none", border: "none", cursor: "pointer", padding: 0 }}>
          How to read this page
        </button>
      </div>

      {/* Market context bar */}
      <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border-c)", display: "flex", alignItems: "center", gap: 16 }}>
        <span className="mono text-[13px]" style={{ color: "var(--text-primary)" }}>
          SPY {market.spy_close ? `$${market.spy_close.toFixed(2)}` : "—"}
        </span>
        <span className="mono text-[13px]" style={{ color: "var(--text-secondary)" }}>
          VIX {market.vix_close ? market.vix_close.toFixed(2) : "—"}
        </span>
        <span className="mono text-[12px]" style={{ color: "var(--text-tertiary)", marginLeft: "auto" }}>
          {sessionDate}
        </span>
      </div>

      {loading && !data && (
        <div className="panel-2 p-6 m-3" style={{ textAlign: "center", color: "var(--text-quaternary)", fontSize: 13 }}>
          Loading Alpha Flow…
        </div>
      )}

      {err && (
        <div className="panel-2 p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>Error: {err}</div>
      )}

      {data && (
        <div style={{ flex: 1, overflowY: "auto", padding: "8px 16px 16px", display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Executive Summary */}
          {summaryMd && (
            <div className="card" style={{ padding: 16 }}>
              <div className="display text-[13px] font-bold" style={{ color: "var(--text-primary)", marginBottom: 8 }}>
                Executive Summary
              </div>
              <div className="text-[12px]" style={{ color: "var(--text-secondary)", lineHeight: 1.7 }}>
                {summaryMd.replace(/^#+\s*/gm, "").split("\n").filter(l => l.trim()).map((line, i) => (
                  <p key={i} style={{ margin: "4px 0" }}>{line}</p>
                ))}
              </div>
            </div>
          )}

          {/* Top 10 Table */}
          {top10.length > 0 && (
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-bold" style={{ color: "var(--text-primary)" }}>
                  Top 10 by Flow Score
                </span>
              </div>
              <table style={{ width: "100%", borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["#", "Ticker", "Score", "Direction"].map(h => (
                      <th key={h} style={{
                        color: "var(--text-tertiary)", padding: "8px 10px", textAlign: "left",
                        fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em",
                        whiteSpace: "nowrap",
                      }}>{h}</th>
                    ))}
                    <th style={{ width: "100%" }}></th>
                  </tr>
                </thead>
                <tbody>
                  {top10.map((row, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)", height: 34 }}>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>{row.rank || i + 1}</span>
                      </td>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[12px] font-bold" style={{ color: "var(--gold)" }}>{row.ticker}</span>
                      </td>
                      <td style={{ padding: "0 10px" }}>
                        <span className="mono text-[12px]" style={{ color: "var(--text-primary)" }}>
                          {row.score?.toFixed(1) || "—"}
                        </span>
                      </td>
                      <td style={{ padding: "0 10px", textAlign: "right" }}>
                        <span style={{
                          padding: "3px 8px", borderRadius: 4, fontSize: 10, fontWeight: 600,
                          background: row.direction === "bullish" ? "var(--green-dim)" : row.direction === "bearish" ? "var(--red-dim)" : "var(--surface-2)",
                          color: row.direction === "bullish" ? "var(--green)" : row.direction === "bearish" ? "var(--red)" : "var(--text-tertiary)",
                        }}>
                          {(row.direction || "—").toUpperCase()}
                        </span>
                      </td>
                      <td style={{ width: "100%" }}></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
