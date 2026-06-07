import React, { useEffect, useState } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

export default function EarningsPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [view, setView] = useState("today");

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/earnings`, { timeout: 15000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    return () => { mounted = false; };
  }, [view]);

  const today = new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
  const calendar = data?.calendar || [];

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>
        {/* Page header */}
        <div className="fa-page-header">
          <h1>Earnings Hub</h1>
          <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            {today}
          </span>
        </div>

        {/* Subtitle */}
        <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border-c)" }}>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>
            Pre-market and after-hours earnings, with implied move, IV rank, and post-earnings history.
          </p>
        </div>

        {/* View tabs */}
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--border-c)" }}>
          {["today", "tomorrow", "this-week", "next-week", "monthly"].map(v => (
            <button
              key={v}
              className={`fa-chip ${view === v ? "active" : ""}`}
              onClick={() => setView(v)}
            >
              {v.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}
            </button>
          ))}
        </div>

        {loading && !data && (
          <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
            Loading earnings…
          </div>
        )}

        {error && (
          <div className="panel p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
            Error: {error}
          </div>
        )}

        {/* Earnings content */}
        <div style={{ padding: "16px" }}>
          <div className="card" style={{ padding: 24, textAlign: "center" }}>
            <div className="display text-[14px] font-semibold mb-2" style={{ color: "var(--text-primary)" }}>
              Earnings Hub — {view.split("-").map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(" ")}
            </div>
            {calendar.length === 0 ? (
              <div style={{ color: "var(--text-quaternary)", fontSize: 13, marginTop: 16 }}>
                No earnings reporting in this session. Try the next session, or jump to "This Week" for the full window.
              </div>
            ) : (
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse", marginTop: 12 }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["Ticker", "Date", "Time", "Implied Move", "IV Rank"].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {calendar.map((e, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-2 mono font-semibold" style={{ color: "var(--gold)" }}>{e.ticker}</td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>{e.date}</td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-tertiary)" }}>{e.time || "—"}</td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-primary)" }}>{e.implied_move || "—"}</td>
                      <td className="px-3 py-2 mono" style={{ color: "var(--text-secondary)" }}>{e.iv_rank || "—"}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
