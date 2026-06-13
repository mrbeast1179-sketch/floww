import React, { useEffect, useState } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

function fmt(n, decimals = 0) {
  if (n == null || isNaN(n)) return "—";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(decimals);
}

export default function DailyReportPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [sortBy, setSortBy] = useState("confidence");

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/flow-digest`, { timeout: 30000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, []);

  const sessionDate = data?.session_date || new Date().toISOString().split("T")[0];
  const bodyMd = data?.body_md || "";

  // Parse the markdown body for hit list items
  const hitListItems = [];
  const lines = bodyMd.split("\n");
  for (const line of lines) {
    if (line.startsWith("- ") || line.match(/^\d+\./)) {
      hitListItems.push(line.replace(/^[-*]\s*/, "").replace(/^\d+\.\s*/, ""));
    }
  }

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        {/* Page header */}
        <div className="fa-page-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1>Daily Report</h1>
            <span className="tag" style={{ background: "var(--gold-dim)", color: "var(--gold)", fontSize: 10 }}>NEW</span>
          </div>
          <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            {sessionDate}
          </span>
        </div>

        {loading && !data && (
          <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
            Loading Daily Report…
          </div>
        )}

        {error && (
          <div className="panel p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
            Error: {error}
          </div>
        )}

        {/* Market summary */}
        <div style={{ display: "flex", gap: 16, padding: "8px 16px", borderBottom: "1px solid var(--border-c)", alignItems: "center" }}>
          <span className="mono text-[12px]" style={{ color: "var(--text-primary)" }}>
            SPY —
          </span>
          <span className="mono text-[12px]" style={{ color: "var(--text-secondary)" }}>
            VIX —
          </span>
          <span className="text-[11px] uppercase tracking-wider" style={{ color: "var(--emerald)", marginLeft: "auto" }}>
            BULLISH
          </span>
        </div>

        {/* Digest body */}
        {bodyMd && (
          <div style={{ padding: "16px" }}>
            <div className="card" style={{ padding: 16 }}>
              <div className="display text-[12px] font-semibold mb-3" style={{ color: "var(--text-primary)" }}>
                Flow Digest — {sessionDate}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-secondary)", lineHeight: 1.8 }}>
                {lines.filter(l => l.trim()).map((line, i) => {
                  if (line.startsWith("##")) return <h3 key={i} style={{ color: "var(--text-primary)", fontSize: 14, margin: "12px 0 4px" }}>{line.replace(/^#+\s*/, "")}</h3>;
                  if (line.startsWith("#")) return <h2 key={i} style={{ color: "var(--text-primary)", fontSize: 16, margin: "12px 0 4px" }}>{line.replace(/^#+\s*/, "")}</h2>;
                  if (line.startsWith("- ") || line.startsWith("* ")) return <div key={i} style={{ padding: "2px 0 2px 16px" }}>• {line.replace(/^[-*]\s*/, "")}</div>;
                  return <p key={i} style={{ margin: "4px 0" }}>{line}</p>;
                })}
              </div>
            </div>
          </div>
        )}

        {/* Hit List */}
        {hitListItems.length > 0 && (
          <div style={{ padding: "0 16px 16px" }}>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
                <span className="display text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  Hit List
                </span>
                <div style={{ display: "flex", gap: 4 }}>
                  {["confidence", "premium", "ticker"].map(s => (
                    <button key={s} className={`fa-chip ${sortBy === s ? "active" : ""}`} onClick={() => setSortBy(s)} style={{ fontSize: 10, padding: "2px 8px" }}>
                      Sort: {s.charAt(0).toUpperCase() + s.slice(1)}
                    </button>
                  ))}
                </div>
              </div>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["#", "Ticker", "Conf", "Premium", "Contract", "Thesis", "Sector"].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {hitListItems.map((item, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)" }}>{i + 1}</td>
                      <td className="px-3 py-2 mono font-semibold" style={{ color: "var(--gold)" }}>
                        {item.split(" ")[0] || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--text-tertiary)" }}>—</span>
                      </td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>—</td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)", fontSize: 10 }}>—</td>
                      <td className="px-3 py-2" style={{ color: "var(--text-secondary)", fontSize: 11, maxWidth: 300 }}>{item}</td>
                      <td className="px-3 py-2" style={{ color: "var(--text-tertiary)", fontSize: 11 }}>—</td>
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
