import React, { useEffect, useState, useMemo } from "react";
import axios from "axios";
import { fmt, fmtAbs, TRINITY } from "../lib/helpers";

const API = process.env.REACT_APP_BACKEND_URL
  ? `${process.env.REACT_APP_BACKEND_URL}/api`
  : "/api";

/**
 * Trinity 3-Panel View — Skylit reference layout
 *
 * View modes:
 * - "grid": 2D heatmap grid (strike × [call_gex, gex, put_gex, vex, charm])
 * - "bars": horizontal bar chart per strike showing GEX magnitude
 * - "list": price ladder with % badges (original view)
 *
 * King node (brightest cell) gets gold glow + large star + pulse
 */

// ── Color scale for cell backgrounds ─────────────────────────────────
function gridCellColor(v, maxAbs) {
  if (v === null || v === undefined || isNaN(v) || v === 0) {
    return { bg: "rgba(11, 17, 33, 0.95)", text: "#3a4560", star: false };
  }
  const norm = Math.min(1, Math.abs(v) / maxAbs);
  const isNeg = v < 0;

  // Extreme (top 15%) — bright yellow + star
  if (norm > 0.85) {
    return isNeg
      ? { bg: `rgba(168, 55, 230, ${0.5 + 0.35 * norm})`, text: "#fce7fe", star: true }
      : { bg: `rgba(251, 191, 36, ${0.7 + 0.2 * norm})`, text: "#0b1121", star: true };
  }
  if (norm > 0.50) {
    return isNeg
      ? { bg: `rgba(168, 85, 247, ${0.40 + 0.25 * norm})`, text: "#e9d5ff", star: false }
      : { bg: `rgba(45, 212, 191, ${0.40 + 0.25 * norm})`, text: "#0b1121", star: false };
  }
  if (norm > 0.20) {
    return isNeg
      ? { bg: `rgba(168, 85, 247, ${0.15 + 0.15 * norm})`, text: "#c4b5fd", star: false }
      : { bg: `rgba(45, 212, 191, ${0.15 + 0.15 * norm})`, text: "#6ee7b7", star: false };
  }
  return isNeg
    ? { bg: "rgba(88, 28, 135, 0.08)", text: "#8b7fd4", star: false }
    : { bg: "rgba(22, 78, 99, 0.08)", text: "#5ebfb0", star: false };
}

function rowColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "transparent";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  const isNeg = gexVal < 0;

  if (norm > 0.80) return "rgba(253, 224, 71, 0.65)";
  if (norm > 0.50) return isNeg ? "rgba(168, 85, 247, 0.40)" : "rgba(45, 212, 191, 0.45)";
  if (norm > 0.20) return isNeg ? "rgba(168, 85, 247, 0.22)" : "rgba(45, 212, 191, 0.25)";
  return isNeg ? "rgba(88, 28, 135, 0.10)" : "rgba(22, 78, 99, 0.10)";
}

function textColor(gexVal, maxAbs) {
  if (!gexVal || !maxAbs) return "#4a5568";
  const norm = Math.min(1, Math.abs(gexVal) / maxAbs);
  if (norm > 0.80) return "#0a0e1a";
  if (norm > 0.50) return isNeg(gexVal) ? "#e9d5ff" : "#0a0e1a";
  return isNeg(gexVal) ? "#c4b5fd" : "#6ee7b7";
}

function isNeg(v) { return v < 0; }

function fmtGex(v) {
  if (v === null || v === undefined || isNaN(v)) return "—";
  const abs = Math.abs(v);
  const sign = v < 0 ? "-" : "";
  if (abs >= 1e6) return `${sign}$${(abs / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sign}${(abs / 1e3).toFixed(1)}K`;
  return `${sign}${abs.toFixed(0)}`;
}

// ── View mode options ────────────────────────────────────────────────
const VIEW_MODES = [
  { id: "grid", label: "2D Grid", icon: "⊞" },
  { id: "bars", label: "Bars", icon: "▤" },
  { id: "list", label: "List", icon: "☰" },
];

// ── Main Trinity View ──────────────────────────────────────────────
export default function TrinityView({ onFocusTicker }) {
  const [allData, setAllData] = useState({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [viewMode, setViewMode] = useState("grid");

  useEffect(() => {
    let mounted = true;
    const fetchAll = async () => {
      setLoading(true);
      try {
        const results = await Promise.allSettled(
          TRINITY.map(t =>
            axios.get(`${API}/heatmap/${t}?expiries=3&mode=day`, { timeout: 15000 })
              .then(r => ({ ticker: t, data: r.data }))
          )
        );
        const newData = {};
        results.forEach(r => {
          if (r.status === "fulfilled") newData[r.value.ticker] = r.value.data;
        });
        if (mounted) { setAllData(newData); setLoading(false); }
      } catch (e) {
        if (mounted) { setError(e.message); setLoading(false); }
      }
    };
    fetchAll();
    const id = setInterval(fetchAll, 30000);
    return () => { mounted = false; clearInterval(id); };
  }, []);

  if (loading && Object.keys(allData).length === 0) {
    return <div className="p-4 text-slate-500 text-sm">Loading Trinity…</div>;
  }
  if (error) {
    return <div className="p-4 text-rose-400 text-sm">Error: {error}</div>;
  }

  return (
    <div className="trinity-layout" data-testid="trinity-view">
      {/* Confluence summary bar with view toggle */}
      <ConfluenceBar data={allData} viewMode={viewMode} onViewModeChange={setViewMode} />

      {/* Three panels */}
      <div className="trinity-panels">
        {TRINITY.map(t => (
          <TrinityPanel
            key={t}
            ticker={t}
            data={allData[t]}
            viewMode={viewMode}
            onFocus={() => onFocusTicker && onFocusTicker(t)}
          />
        ))}
      </div>
    </div>
  );
}

// ── Confluence Summary Bar ─────────────────────────────────────────
function ConfluenceBar({ data, viewMode, onViewModeChange }) {
  const tickers = TRINITY.map(t => data[t]).filter(d => d && !d.error);
  if (tickers.length === 0) return null;

  const regimes = tickers.map(d => d.nodes?.regime).filter(Boolean);
  const allSame = regimes.length > 0 && regimes.every(r => r === regimes[0]);
  const confluence = regimes.length > 0
    ? regimes.filter(r => r === regimes[0]).length / regimes.length
    : 0;

  const verdict = confluence === 1 ? "full" : confluence >= 0.66 ? "partial" : "diverge";
  const verdictColor = verdict === "full" ? "trinity-verdict-pos" : verdict === "partial" ? "trinity-verdict-warn" : "trinity-verdict-neg";
  const verdictText = verdict === "full" ? "All three agree. Highest conviction." : verdict === "partial" ? "Two-of-three. Reduced size." : "Disagreement. Wait.";

  return (
    <div className="trinity-summary">
      <div className="trinity-summary-left">
        <div className="trinity-stat">
          <span className="trinity-stat-label">Confluence</span>
          <span className={`trinity-stat-value ${confluence === 1 ? "text-emerald-400" : confluence >= 0.66 ? "text-amber-400" : "text-rose-400"}`}>
            {(confluence * 100).toFixed(0)}%
          </span>
        </div>
        <div className="trinity-divider" />
        <div className="trinity-stat">
          <span className="trinity-stat-label">Regime</span>
          <span className={`trinity-stat-value ${regimes[0] === "positive" ? "text-emerald-400" : regimes[0] === "negative" ? "text-rose-400" : "text-slate-400"}`}>
            {regimes[0] || "—"}
          </span>
        </div>
      </div>
      <div className="trinity-summary-right">
        <span className={`trinity-verdict ${verdictColor}`}>{verdictText}</span>
        <div className="trinity-view-toggle">
          {VIEW_MODES.map(vm => (
            <button
              key={vm.id}
              className={`trinity-view-btn ${viewMode === vm.id ? "trinity-view-active" : ""}`}
              onClick={() => onViewModeChange(vm.id)}
              title={vm.label}
            >
              <span className="trinity-view-icon">{vm.icon}</span>
              <span className="trinity-view-label">{vm.label}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

// ── Single Trinity Panel ───────────────────────────────────────────
function TrinityPanel({ ticker, data, viewMode, onFocus }) {
  const spot = data?.spot;
  const nodes = data?.nodes;

  // Build sorted strike rows
  const rows = useMemo(() => {
    if (!data?.strikes) return [];
    return data.strikes
      .filter(s => s.strike != null && s.gex != null)
      .sort((a, b) => b.strike - a.strike);
  }, [data]);

  // Max abs GEX for color scaling within this panel
  const maxAbs = useMemo(() => {
    if (!rows.length) return 1;
    return Math.max(...rows.map(s => Math.abs(s.gex || 0)), 1);
  }, [rows]);

  // Max abs across ALL 5 grid columns for consistent grid coloring
  const gridMaxAbs = useMemo(() => {
    if (!rows.length) return 1;
    let m = 1;
    for (const row of rows) {
      for (const key of ["call_gex", "gex", "put_gex", "vex", "charm"]) {
        const v = Math.abs(row[key] || 0);
        if (v > m) m = v;
      }
    }
    return m;
  }, [rows]);

  // Current price row index (closest strike to spot)
  const spotIdx = useMemo(() => {
    if (!spot || !rows.length) return -1;
    let best = 0;
    let bestDist = Math.abs(rows[0].strike - spot);
    for (let i = 1; i < rows.length; i++) {
      const d = Math.abs(rows[i].strike - spot);
      if (d < bestDist) { bestDist = d; best = i; }
    }
    return best;
  }, [rows, spot]);

  // King node (strike with highest abs GEX) — find from rows directly
  const kingRowIdx = useMemo(() => {
    if (!rows.length) return -1;
    let maxVal = 0;
    let kingI = -1;
    for (let i = 0; i < rows.length; i++) {
      const v = Math.abs(rows[i].gex || 0);
      if (v > maxVal) { maxVal = v; kingI = i; }
    }
    return kingI;
  }, [rows]);

  // Panel net GEX sum
  const netGex = useMemo(() => {
    if (!rows.length) return 0;
    return rows.reduce((sum, s) => sum + (s.gex || 0), 0);
  }, [rows]);

  // Min/max for footer gradient
  const [minGex, maxGex] = useMemo(() => {
    if (!rows.length) return [0, 0];
    const gexs = rows.map(s => s.gex || 0);
    return [Math.min(...gexs), Math.max(...gexs)];
  }, [rows]);

  const displayName = ticker.replace("^", "");
  const regime = nodes?.regime || "—";
  const regimeColor = regime === "positive" ? "text-emerald-400" : regime === "negative" ? "text-rose-400" : "text-slate-400";
  const regimeLabel = regime === "positive" ? "positive γ" : regime === "negative" ? "negative γ" : "neutral";

  // Render the appropriate view based on viewMode
  const renderView = () => {
    if (rows.length === 0) {
      return <div className="trinity-no-data">No strike data available</div>;
    }
    switch (viewMode) {
      case "bars":
        return <BarsView rows={rows} maxAbs={maxAbs} spotIdx={spotIdx} kingRowIdx={kingRowIdx} />;
      case "list":
        return <ListView rows={rows} maxAbs={maxAbs} spotIdx={spotIdx} kingRowIdx={kingRowIdx} />;
      case "grid":
      default:
        return <GridView rows={rows} gridMaxAbs={gridMaxAbs} spotIdx={spotIdx} kingRowIdx={kingRowIdx} />;
    }
  };

  return (
    <div className="trinity-panel">
      {/* Header */}
      <div className="trinity-panel-header">
        <span className="trinity-panel-ticker">{displayName}</span>
        <span className="trinity-panel-price">${fmt(spot, spot >= 1000 ? 2 : 2)}</span>
        <span className={`trinity-panel-regime ${regimeColor}`}>{regimeLabel}</span>
      </div>

      {/* Sub-header: King */}
      <div className="trinity-panel-subheader">
        <span className="trinity-king-dot" />
        <span className="trinity-king-label">King</span>
        {kingRowIdx >= 0 && <span className="trinity-king-value">{fmt(rows[kingRowIdx].strike, 0)}</span>}
        <span className={`trinity-net-badge ${netGex >= 0 ? "trinity-net-pos" : "trinity-net-neg"}`}>
          {fmtGex(netGex)}
        </span>
      </div>

      {/* Data view */}
      <div className="trinity-grid">
        {renderView()}
      </div>

      {/* Footer gradient bar */}
      <div className="trinity-footer">
        <span className="trinity-footer-min">{fmtGex(minGex)}</span>
        <div className="trinity-gradient-bar">
          <div className="trinity-gradient-fill" />
        </div>
        <span className="trinity-footer-max">{fmtGex(maxGex)}</span>
      </div>

      {/* Focus link */}
      <button className="trinity-focus-btn" onClick={onFocus}>focus →</button>
    </div>
  );
}

// ── 2D Grid View ───────────────────────────────────────────────────
function GridView({ rows, gridMaxAbs, spotIdx, kingRowIdx }) {
  const gridCols = ["call_gex", "gex", "put_gex", "vex", "charm"];
  const colLabels = ["Call", "Net", "Put", "VEX", "Charm"];

  return (
    <div className="trinity-grid-scroll">
      <table className="trinity-grid-table">
        <thead>
          <tr className="trinity-grid-header">
            <th className="trinity-grid-th-price">Strike</th>
            {colLabels.map((label, i) => (
              <th key={i} className="trinity-grid-th">{label}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const isCurrent = i === spotIdx;
            const isKing = i === kingRowIdx;
            return (
              <tr
                key={row.strike}
                className={`trinity-grid-row ${isCurrent ? "trinity-row-current" : ""} ${isKing ? "trinity-row-king-grid" : ""}`}
              >
                <td className={`trinity-grid-price ${isCurrent ? "trinity-price-current" : ""}`}>
                  {isCurrent && <span className="trinity-price-triangle" />}
                  {isKing && <span className="trinity-king-star-grid">★</span>}
                  {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
                </td>
                {gridCols.map((key, ci) => {
                  const val = row[key] || 0;
                  const cc = gridCellColor(val, gridMaxAbs);
                  const isMaxInCol = isKing && key === "gex";
                  return (
                    <td
                      key={ci}
                      className={`trinity-grid-cell ${cc.star ? "trinity-grid-star" : ""} ${isMaxInCol ? "trinity-grid-poc" : ""}`}
                      style={{ background: cc.bg, color: cc.text }}
                      title={`${fmt(row.strike, 0)} ${colLabels[ci]}: ${fmtGex(val)}`}
                    >
                      {cc.star ? <span className="trinity-grid-star-icon">★</span> : ""}{fmtGex(val)}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

// ── Bars View ──────────────────────────────────────────────────────
function BarsView({ rows, maxAbs, spotIdx, kingRowIdx }) {
  return (
    <div className="trinity-bars-scroll">
      {rows.map((row, i) => {
        const isCurrent = i === spotIdx;
        const isKing = i === kingRowIdx;
        const gex = row.gex || 0;
        const absGex = Math.abs(gex);
        const pct = maxAbs > 0 ? (absGex / maxAbs) * 100 : 0;
        const isNeg = gex < 0;
        const barColor = isKing
          ? "linear-gradient(90deg, rgba(251,191,36,0.9), rgba(253,224,71,0.95))"
          : isNeg
            ? "linear-gradient(90deg, rgba(168,85,247,0.6), rgba(168,85,247,0.3))"
            : "linear-gradient(90deg, rgba(45,212,191,0.6), rgba(45,212,191,0.3))";

        return (
          <div
            key={row.strike}
            className={`trinity-bar-row ${isCurrent ? "trinity-row-current" : ""} ${isKing ? "trinity-row-king-bar" : ""}`}
          >
            <span className={`trinity-bar-price ${isCurrent ? "trinity-price-current" : ""}`}>
              {isCurrent && <span className="trinity-price-triangle" />}
              {isKing && <span className="trinity-king-star-bar">★</span>}
              {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
            </span>
            <div className="trinity-bar-track">
              <div
                className={`trinity-bar-fill ${isKing ? "trinity-bar-king" : ""}`}
                style={{
                  width: `${Math.min(100, pct)}%`,
                  background: barColor,
                }}
              />
            </div>
            <span className="trinity-bar-value" style={{ color: isKing ? "#fbbf24" : isNeg ? "#c4b5fd" : "#6ee7b7" }}>
              {fmtGex(gex)}
            </span>
          </div>
        );
      })}
    </div>
  );
}

// ── List View (original price ladder) ──────────────────────────────
function ListView({ rows, maxAbs, spotIdx, kingRowIdx }) {
  return (
    <>
      {rows.map((row, i) => {
        const isCurrent = i === spotIdx;
        const isKing = i === kingRowIdx;
        const gex = row.gex || 0;
        const bg = rowColor(gex, maxAbs);
        const tc = textColor(gex, maxAbs);
        const pctVal = maxAbs > 0 ? Math.abs(gex / maxAbs) * 100 : 0;

        return (
          <div
            key={row.strike}
            className={`trinity-row ${isCurrent ? "trinity-row-current" : ""} ${isKing ? "trinity-row-king" : ""}`}
            style={{ background: bg }}
          >
            <span className={`trinity-row-price ${isCurrent ? "trinity-price-current" : ""}`}>
              {isCurrent && <span className="trinity-price-triangle" />}
              {isKing && <span className="trinity-king-star">★</span>}
              {fmt(row.strike, row.strike >= 1000 ? 0 : 1)}
            </span>
            <span className="trinity-row-pct">
              {pctVal > 15 && (
                <span className={`trinity-pct-badge ${gex >= 0 ? "trinity-pct-pos" : "trinity-pct-neg"}`}>
                  {gex >= 0 ? "+" : ""}{pctVal.toFixed(0)}%
                </span>
              )}
            </span>
            <span className="trinity-row-value" style={{ color: tc }}>
              {fmtGex(gex)}
            </span>
          </div>
        );
      })}
    </>
  );
}
