import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "http://localhost:8000";
const API = `${BACKEND_URL}/api`;

function fmt(n, d = 0) {
  if (n == null || isNaN(n)) return "—";
  return n.toFixed(d);
}

function fmtAbs(n) {
  if (n == null || isNaN(n)) return "—";
  const abs = Math.abs(n);
  if (abs >= 1e9) return (abs / 1e9).toFixed(1) + "B";
  if (abs >= 1e6) return (abs / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (abs / 1e3).toFixed(0) + "K";
  return abs.toFixed(0);
}

export default function SpxGexPage() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState(null);
  const [dteFilter, setDteFilter] = useState(null);

  useEffect(() => {
    let mounted = true;
    const fetchData = async () => {
      try {
        const res = await axios.get(`${API}/gex/spx`, { timeout: 30000 });
        if (mounted) setData(res.data);
      } catch (e) {
        if (mounted) setErr(e.message);
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
  const asof = data?.asof ? new Date(data.asof) : null;

  const filteredStrikes = useMemo(() => {
    return byStrike.filter(s => Math.abs(s.strike - spot) <= 150);
  }, [byStrike, spot]);

  const kingNodes = useMemo(() => {
    return [...byStrike]
      .sort((a, b) => Math.abs(b.gex || 0) - Math.abs(a.gex || 0))
      .slice(0, 10)
      .map(n => ({
        ...n,
        dist: n.strike ? Math.round(n.strike - spot) : 0,
        role: (n.gex || 0) > 0 ? "Resist" : "Support",
      }));
  }, [byStrike, spot]);

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

  const maxAbsGex = useMemo(() => {
    return Math.max(...filteredStrikes.map(s => Math.abs(s.gex || 0)), 1);
  }, [filteredStrikes]);

  return (
    <div style={{ flex: 1, display: "flex", flexDirection: "column", minHeight: 0 }}>
      {/* Page header — AlphaPod style */}
      <div style={{
        background: "rgba(10,10,11,0.85)", backdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border-c)",
        padding: "12px 16px", minHeight: 48,
        display: "flex", alignItems: "center", justifyContent: "space-between",
        flexWrap: "wrap", gap: 8,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 8, minWidth: 0 }}>
          {/* Breadcrumb */}
          <span className="text-[13px]" style={{ color: "var(--text-tertiary)" }}>SPX</span>
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: "var(--text-quaternary)", flexShrink: 0 }}>
            <path d="M9 18l6-6-6-6"/>
          </svg>
          <span className="display text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>SPX GEX</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          {asof && (
            <div className="inline-flex items-center gap-2 rounded-md px-2.5 py-1.5"
              style={{ background: "var(--surface-1)", border: "1px solid var(--border-c)" }}>
              <span className="h-1.5 w-1.5 rounded-full" style={{ background: "var(--green)" }} />
              <span className="mono text-[10px] font-bold uppercase tracking-wide" style={{ color: "var(--text-secondary)" }}>
                {asof.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", second: "2-digit" })} ET
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Description + Source */}
      <div style={{ padding: "8px 16px 0" }}>
        <h1 className="display text-[22px] font-bold" style={{ color: "var(--text-primary)", margin: "0 0 4px" }}>
          SPX Gamma Exposure
        </h1>
        <p className="text-[13px]" style={{ color: "var(--text-tertiary)", margin: 0 }}>
          Daily GEX levels by strike. Above spot: positive = call wall (resistance).
          Below spot: negative = put wall (support). Mirrors the chart posted to Discord.
        </p>
      </div>

      {/* DTE filter tabs */}
      <div style={{ padding: "8px 16px", display: "flex", gap: 4, flexWrap: "wrap" }}>
        {[{ l: "0 DTE", v: 0 }, { l: "1 DTE", v: 1 }, { l: "2 DTE", v: 2 }, { l: "4 DTE", v: 4 }].map(({ l, v }) => (
          <button
            type="button"
            key={l}
            className="mono px-3 py-1.5 text-[11px] font-bold uppercase tracking-wider transition-all"
            style={{
              borderRadius: 4,
              border: dteFilter === v ? "1px solid var(--gold-border)" : "1px solid var(--border-c)",
              background: dteFilter === v ? "var(--gold-dim)" : "var(--surface-2)",
              color: dteFilter === v ? "var(--gold)" : "var(--text-tertiary)",
            }}
            onClick={() => setDteFilter(dteFilter === v ? null : v)}
          >
            {l}
          </button>
        ))}
        <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 8 }}>
          <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider" style={{ color: "var(--green)" }}>
            <span className="h-2 w-2 rounded-sm" style={{ background: "var(--green)" }} />
            Positive
          </span>
          <span className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider" style={{ color: "var(--red)" }}>
            <span className="h-2 w-2 rounded-sm" style={{ background: "var(--red)" }} />
            Negative
          </span>
        </div>
      </div>

      {loading && !data && (
        <div className="panel-2 p-6 m-3" style={{ textAlign: "center", color: "var(--text-quaternary)", fontSize: 13 }}>
          Loading SPX GEX data…
        </div>
      )}

      {err && (
        <div className="panel-2 p-4 m-3" style={{ color: "var(--amber)", fontSize: 12 }}>
          Error: {err}. Showing cached data.
        </div>
      )}

      {/* GEX Bar Chart — card */}
      {filteredStrikes.length > 0 && (
        <div className="spx-gex-chart-card" style={{ margin: "0 16px 16px", padding: 0 }}>
          <div style={{ padding: "8px 18px 4px" }}>
            <div className="display text-[14px] font-bold" style={{ color: "var(--text-primary)", marginBottom: 2 }}>
              Net GEX by Strike
            </div>
            <div className="text-[11px]" style={{ color: "var(--text-tertiary)", marginBottom: 8 }}>
              Strikes within ±150 of spot · {data?.asof ? new Date(data.asof).toLocaleDateString("en-US", { month: "numeric", day: "numeric", year: "numeric" }) : "—"}
            </div>

            {/* Spot/Flip markers */}
            <div style={{ display: "flex", alignItems: "center", gap: 16, marginBottom: 4, padding: "0 60px" }}>
              <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: "var(--gold)" }}>◀ SPOT {fmt(spot, 0)}</span>
              {flipPoint && (
                <span className="text-[10px] uppercase tracking-wider font-bold" style={{ color: "var(--amber)" }}>◀ FLIP {fmt(flipPoint, 0)}</span>
              )}
            </div>

            {/* Strike rows */}
            <div style={{ maxHeight: 400, overflowY: "auto", marginTop: 4 }}>
              {filteredStrikes.map((s, i) => {
                const gex = s.gex || 0;
                const barPct = Math.min(Math.abs(gex) / maxAbsGex * 50, 50);
                const isSpot = s.strike && Math.abs(s.strike - spot) < 2.5;
                return (
                  <div key={i} style={{ display: "flex", alignItems: "center", gap: 6, height: 18, position: "relative" }}>
                    <span className="mono text-[10px]" style={{
                      width: 55, textAlign: "right", flexShrink: 0,
                      color: isSpot ? "var(--gold)" : "var(--text-tertiary)",
                      fontWeight: isSpot ? 700 : 400,
                    }}>
                      {s.strike ? fmt(s.strike, 0) : "—"}
                    </span>
                    <div style={{ flex: 1, display: "flex", alignItems: "center", height: 14, position: "relative" }}>
                      {/* Center line */}
                      <div style={{ position: "absolute", left: "50%", width: 1, height: 10, background: "var(--border-c)", top: 2 }} />
                      {/* Bar */}
                      {barPct > 0 && (
                        <div style={{
                          position: "absolute",
                          left: gex > 0 ? "50%" : `${50 - barPct}%`,
                          width: `${Math.max(barPct, 0.3)}%`,
                          height: 10,
                          background: gex > 0
                            ? "rgba(34,197,94,0.45)"
                            : "rgba(239,68,68,0.45)",
                          borderRadius: 1,
                        }} />
                      )}
                    </div>
                    <span className="mono text-[10px]" style={{
                      width: 55, flexShrink: 0, textAlign: "left",
                      color: gex > 0 ? "var(--green)" : gex < 0 ? "var(--red)" : "var(--text-tertiary)",
                      fontWeight: Math.abs(gex) > 10000000 ? 700 : 400,
                    }}>
                      {gex > 0 ? "+" : ""}{fmtAbs(gex)}
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
        <div className="card" style={{ margin: "0 16px 16px", padding: 0 }}>
          <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--border-c)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <div>
              <span className="display text-[14px] font-bold" style={{ color: "var(--text-primary)" }}>King Nodes</span>
              <span className="text-[11px]" style={{ color: "var(--text-tertiary)", marginLeft: 8 }}>
                Top 10 strikes by absolute net GEX
              </span>
            </div>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead>
                <tr style={{ borderBottom: "1px solid var(--border-c)" }}>
                  {["Strike", "Dist", "Net GEX", "Role"].map(h => (
                    <th key={h} style={{
                      color: "var(--text-tertiary)", padding: "8px 10px", textAlign: "left",
                      fontSize: 10, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.08em",
                      whiteSpace: "nowrap",
                    }}>
                      {h}
                    </th>
                  ))}
                  <th style={{ width: "100%" }}></th>
                </tr>
              </thead>
              <tbody>
                {kingNodes.map((n, i) => (
                  <tr key={i} style={{ borderBottom: "1px solid var(--border-c)", height: 34 }}>
                    <td style={{ padding: "0 10px" }}>
                      <span className="mono text-[12px]" style={{ color: "var(--text-primary)", fontWeight: 600 }}>
                        {n.strike ? fmt(n.strike, 0) : "—"}
                      </span>
                    </td>
                    <td style={{ padding: "0 10px" }}>
                      <span className="mono text-[12px]" style={{ color: n.dist > 0 ? "var(--green)" : "var(--red)" }}>
                        {n.dist > 0 ? "+" : ""}{n.dist}
                      </span>
                    </td>
                    <td style={{ padding: "0 10px" }}>
                      <span className="mono text-[12px]" style={{ color: (n.gex || 0) > 0 ? "var(--green)" : "var(--red)", textAlign: "right", display: "block" }}>
                        {(n.gex || 0) > 0 ? "+" : ""}{fmtAbs(n.gex)}
                      </span>
                    </td>
                    <td style={{ padding: "0 10px", textAlign: "right" }}>
                      {n.role === "Resist" ? (
                        <span style={{ padding: "3px 8px", borderRadius: 4, background: "var(--green-dim)", color: "var(--green)", fontSize: 11, fontWeight: 600 }}>
                          {n.role}
                        </span>
                      ) : (
                        <span style={{ padding: "3px 8px", borderRadius: 4, background: "var(--red-dim)", color: "var(--red)", fontSize: 11, fontWeight: 600 }}>
                          {n.role}
                        </span>
                      )}
                    </td>
                    <td style={{ width: "100%" }}></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Source footer */}
      <div style={{ padding: "8px 16px", borderTop: "1px solid var(--border-c)", marginTop: "auto" }}>
        <span className="text-[10px]" style={{ color: "var(--text-quaternary)" }}>
          Source: Polygon · I:SPX option snapshot · Sign convention: dealers short calls / long puts (UW Periscope)
        </span>
      </div>
    </div>
  );
}
