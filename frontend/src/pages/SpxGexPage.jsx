import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

function fmt(n, decimals = 0) {
  if (n == null || isNaN(n)) return "—";
  if (Math.abs(n) >= 1e9) return (n / 1e9).toFixed(1) + "B";
  if (Math.abs(n) >= 1e6) return (n / 1e6).toFixed(1) + "M";
  if (Math.abs(n) >= 1e3) return (n / 1e3).toFixed(0) + "K";
  return n.toFixed(decimals);
}

function gexColor(gex) {
  if (gex > 0) return "var(--emerald)";
  if (gex < 0) return "var(--red)";
  return "var(--text-tertiary)";
}

function roleColor(role) {
  if (role === "Resist") return "var(--emerald)";
  if (role === "Support") return "var(--red)";
  return "var(--text-secondary)";
}

export default function SpxGexPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dteFilter, setDteFilter] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/gex/spx`, { timeout: 30000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setError(e.message);
      }
      if (mounted) setLoading(false);
    };
    fetchData();
    const id = setInterval(fetchData, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  const spot = data?.spot || 0;
  const byStrike = data?.by_strike || [];
  const totalGex = data?.total_gex || 0;

  // Filter strikes within ±150 of spot
  const filteredStrikes = useMemo(() => {
    return byStrike.filter(s => Math.abs(s.strike - spot) <= 150);
  }, [byStrike, spot]);

  // Sort by absolute GEX descending for king nodes
  const kingNodes = useMemo(() => {
    return [...byStrike]
      .sort((a, b) => Math.abs(b.gex || 0) - Math.abs(a.gex || 0))
      .slice(0, 10)
      .map(n => ({
        ...n,
        dist: n.strike - spot,
        role: (n.gex || 0) > 0 ? "Resist" : "Support",
      }));
  }, [byStrike, spot]);

  // Find flip point (where GEX crosses from positive to negative)
  const flipPoint = useMemo(() => {
    for (let i = 0; i < filteredStrikes.length - 1; i++) {
      const curr = filteredStrikes[i];
      const next = filteredStrikes[i + 1];
      if ((curr.gex || 0) > 0 && (next.gex || 0) <= 0) {
        return (curr.strike + next.strike) / 2;
      }
    }
    return null;
  }, [filteredStrikes]);

  // Max absolute GEX for bar scaling
  const maxAbsGex = useMemo(() => {
    return Math.max(...filteredStrikes.map(s => Math.abs(s.gex || 0)), 1);
  }, [filteredStrikes]);

  return (
    <div className="ap-main" style={{ flex: 1, padding: 0 }}>
      <div className="flow-alerts-terminal-glass" style={{ padding: 0 }}>

        {/* Page header */}
        <div className="fa-page-header">
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <h1>SPX GEX</h1>
            <span className="tag" style={{ background: "var(--gold-dim)", color: "var(--gold)", fontSize: 10 }}>NEW</span>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
            <span className="mono text-[11px]" style={{ color: "var(--text-tertiary)" }}>
              {data?.asof ? new Date(data.asof).toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—"} ET
            </span>
          </div>
        </div>

        {/* Description */}
        <div style={{ padding: "8px 16px", borderBottom: "1px solid var(--border-c)" }}>
          <p style={{ fontSize: 12, color: "var(--text-tertiary)", margin: 0 }}>
            SPX Gamma Exposure. Daily GEX levels by strike. Above spot: positive = call wall (resistance).
            Below spot: negative = put wall (support).
          </p>
        </div>

        {/* DTE filter tabs */}
        <div style={{ display: "flex", gap: 4, padding: "8px 16px", borderBottom: "1px solid var(--border-c)" }}>
          {[{ l: "0 DTE", v: 0 }, { l: "1 DTE", v: 1 }, { l: "2 DTE", v: 2 }, { l: "4 DTE", v: 4 }].map(({ l, v }) => (
            <button
              key={l}
              className={`fa-chip ${dteFilter === v ? "active" : ""}`}
              onClick={() => setDteFilter(dteFilter === v ? null : v)}
            >
              {l}
            </button>
          ))}
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 4 }}>
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--emerald)" }}>● Positive</span>
            <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--red)" }}>● Negative</span>
          </div>
        </div>

        {/* Summary bar */}
        <div style={{ display: "flex", gap: 16, padding: "8px 16px", borderBottom: "1px solid var(--border-c)", alignItems: "center" }}>
          <span className="text-[11px]" style={{ color: "var(--text-tertiary)" }}>
            Net GEX by Strike · Strikes within ±150 of spot
          </span>
          <span className="text-[11px] mono" style={{ color: "var(--text-secondary)" }}>
            Total: <span style={{ color: totalGex > 0 ? "var(--emerald)" : "var(--red)", fontWeight: 600 }}>
              {totalGex > 0 ? "+" : ""}{fmt(totalGex)}
            </span>
          </span>
        </div>

        {loading && !data && (
          <div className="panel p-6" style={{ textAlign: "center", color: "var(--text-quaternary)" }}>
            Loading SPX GEX data…
          </div>
        )}

        {error && (
          <div className="panel p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
            Error loading GEX data: {error}. Showing cached/stub data.
          </div>
        )}

        {/* GEX Bar Chart */}
        {filteredStrikes.length > 0 && (
          <div style={{ padding: "12px 16px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 1 }}>
              {/* Spot line marker */}
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--gold)", width: 60 }}>◀ SPOT</span>
                <span className="mono text-[11px]" style={{ color: "var(--gold)" }}>{fmt(spot, 0)}</span>
                {flipPoint && (
                  <>
                    <span className="text-[10px] uppercase tracking-wider" style={{ color: "var(--amber)", marginLeft: 16 }}>◀ FLIP</span>
                    <span className="mono text-[11px]" style={{ color: "var(--amber)" }}>{fmt(flipPoint, 0)}</span>
                  </>
                )}
              </div>

              {/* Strike rows */}
              <div style={{ maxHeight: 400, overflowY: "auto" }}>
                {filteredStrikes.map((s, i) => {
                  const gex = s.gex || 0;
                  const barWidth = Math.abs(gex) / maxAbsGex * 100;
                  const isSpot = Math.abs(s.strike - spot) < 2.5;
                  return (
                    <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, height: 18 }}>
                      <span className="mono text-[10px]" style={{
                        width: 50,
                        textAlign: "right",
                        color: isSpot ? "var(--gold)" : "var(--text-tertiary)",
                        fontWeight: isSpot ? 700 : 400,
                      }}>
                        {fmt(s.strike, 0)}
                      </span>
                      <div style={{ flex: 1, display: "flex", alignItems: "center", height: 14, position: "relative" }}>
                        {/* Center line */}
                        <div style={{ position: "absolute", left: "50%", width: 1, height: 14, background: "var(--border-c)" }} />
                        {/* Bar */}
                        <div style={{
                          position: "absolute",
                          left: gex > 0 ? "50%" : `${50 - barWidth / maxAbsGex * 50}%`,
                          width: `${Math.max(barWidth / maxAbsGex * 50, 0.5)}%`,
                          height: 10,
                          background: gex > 0 ? "rgba(16,185,129,0.5)" : "rgba(239,68,68,0.5)",
                          borderRadius: 1,
                        }} />
                      </div>
                      <span className="mono text-[10px]" style={{
                        width: 50,
                        color: gexColor(gex),
                        fontWeight: Math.abs(gex) > 1e7 ? 700 : 400,
                      }}>
                        {gex > 0 ? "+" : ""}{fmt(gex)}
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        )}

        {/* King Nodes Table */}
        {kingNodes.length > 0 && (
          <div style={{ padding: "0 16px 16px" }}>
            <div className="card" style={{ padding: 0 }}>
              <div style={{ padding: "12px 16px", borderBottom: "1px solid var(--border-c)" }}>
                <span className="display text-[13px] font-semibold" style={{ color: "var(--text-primary)" }}>
                  King Nodes
                </span>
                <span className="text-[11px]" style={{ color: "var(--text-tertiary)", marginLeft: 8 }}>
                  Top 10 strikes by absolute net GEX
                </span>
              </div>
              <table style={{ width: "100%", fontSize: 12, borderCollapse: "collapse" }}>
                <thead>
                  <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                    {["Strike", "Dist", "Net GEX", "Role"].map(h => (
                      <th key={h} className="text-left text-[10px] uppercase tracking-widest font-normal px-3 py-2" style={{ color: "var(--text-quaternary)" }}>
                        {h}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {kingNodes.map((n, i) => (
                    <tr key={i} style={{ borderBottom: "1px solid var(--border-c)" }} className="bar-row">
                      <td className="px-3 py-1.5 mono" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                        {fmt(n.strike, 0)}
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: n.dist > 0 ? "var(--emerald)" : "var(--red)" }}>
                        {n.dist > 0 ? "+" : ""}{n.dist.toFixed(0)}
                      </td>
                      <td className="px-3 py-1.5 mono" style={{ color: gexColor(n.gex) }}>
                        {n.gex > 0 ? "+" : ""}{fmt(n.gex)}
                      </td>
                      <td className="px-3 py-1.5">
                        <span className="text-[10px] uppercase tracking-wider font-semibold" style={{ color: roleColor(n.role) }}>
                          {n.role}
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
            Source: Polygon · I:SPX option snapshot · Sign convention: dealers short calls / long puts (UW Periscope)
          </span>
        </div>
      </div>
    </div>
  );
}
