import React, { useEffect, useState } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

export default function AlphaFlowPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedDate, setSelectedDate] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/alpha-flow`, { timeout: 30000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, [selectedDate]);

  const top10 = data?.top_10 || [];
  const market = data?.market || {};
  const sessionDate = data?.session_date || new Date().toISOString().split("T")[0];

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        {/* Page header */}
        <div className="fa-page-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1>Alpha Flow</h1>
            <span className="tag" style={{ background: "var(--gold-dim)", color: "var(--gold)", fontSize: 10 }}>NEW</span>
          </div>
          <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            {data?.title || `Alpha Flow — ${sessionDate}`}
          </span>
        </div>

        {/* Market context */}
        <div style={{ display: "flex", gap: 16, padding: "8px 16px", borderBottom: "1px solid var(--border-c)", alignItems: "center" }}>
          <span className="mono text-[12px]" style={{ color: "var(--text-primary)" }}>
            SPY {market.spy_close ? `$${market.spy_close.toFixed(2)}` : "—"}
          </span>
          <span className="mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
            VIX {market.vix_close ? market.vix_close.toFixed(2) : "—"}
          </span>
          <span className="text-[11px]" style={{ color: "var(--text-tertiary)", marginLeft: "auto" }}>
            Session: {sessionDate}
          </span>
        </div>

        {loading && !data && (
          <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
            Loading Alpha Flow…
          </div>
        )}

        {error && (
          <div className="panel p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
            Error: {error}
          </div>
        )}

        {/* Executive Summary */}
        {data?.executive_summary_md && (
          <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
            <div className="card" style={{ padding: 16 }}>
              <div className="display text-[12px] font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
                Executive Summary
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.6 }}>
                {data.executive_summary_md.replace(/^#+\s*/gm, "").split("\n").filter(l => l.trim()).map((line, i) => (
                  <p key={i} style={{ margin: "4px 0" }}>{line}</p>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Top 10 Table */}
        {top10.length > 0 && (
          <div style={{ padding: "0 16px 16px" }}>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Top 10 by Flow Score
                </span>
              </div>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["#", "Ticker", "Score", "Direction"].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {top10.map((row, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)", width: 40 }}>
                        {row.rank || i + 1}
                      </td>
                      <td className="px-3 py-2 mono font-semibold" style={{ color: "var(--gold)" }}>
                        {row.ticker}
                      </td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-primary)" }}>
                        {row.score?.toFixed(1) || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-[10px] uppercase tracking-wider font-semibold" style={{
                          color: row.direction === "bullish" ? "var(--emerald)" : row.direction === "bearish" ? "var(--red)" : "var(--text-tertiary)"
                        }}>
                          {row.direction || "—"}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
